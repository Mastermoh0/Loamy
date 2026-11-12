"""Explicit customer delivery and bounded opt-in reminder plans; never blind retries."""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import json
import os
import re
import secrets
import smtplib
import time
from typing import Literal
import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from workspace_contacts import contacts_for, email_address
from workspace_email import send_smtp
from workspace_payments import payment_summary
from workspace_notifications import balance_fingerprint
from workspace_whatsapp import WhatsAppSettings


class DeliveryChoice(BaseModel):
    model_config=ConfigDict(extra='forbid')
    channel: Literal['email','whatsapp']
    email: str = Field(default='',max_length=254)
    confirm: bool
    idempotency_key: str = Field(min_length=16,max_length=80,pattern=r'^[a-zA-Z0-9_-]+$')


class ReminderChoice(DeliveryChoice):
    first_run_at: float = Field(allow_inf_nan=False)
    interval_days: int = Field(default=7,strict=True,ge=1,le=90)
    max_sends: int = Field(default=3,strict=True,ge=1,le=10)


def outbound_settings():
    raw=os.getenv('LOAMY_WHATSAPP_OUTBOUND','')
    if not raw: return {},None
    settings=WhatsAppSettings.from_env()
    try:
        routes=json.loads(raw)
        if not isinstance(routes,dict) or not routes: raise ValueError()
        for bid,r in routes.items():
            if set(r)!={'phone_id','invoice_template','reminder_template','language'} or (settings.routes or {}).get(r['phone_id'])!=bid:
                raise ValueError()
            if not all(isinstance(r[k],str) and re.fullmatch(r'[A-Za-z0-9_]{2,100}',r[k]) for k in ['invoice_template','reminder_template','language']): raise ValueError()
        return routes,settings
    except (ValueError,TypeError,KeyError):
        raise RuntimeError('Outbound WhatsApp must map approved businesses to routed phone IDs, templates and language')


def send_whatsapp(settings,route,recipient,invoice,values,reminder):
    headers={'Authorization':'Bearer '+settings.access_token}
    with httpx.Client(timeout=20,follow_redirects=False) as client:
        response=client.post(f'https://graph.facebook.com/{settings.version}/{route["phone_id"]}/media',headers=headers,
            data={'messaging_product':'whatsapp'},files={'file':(invoice['number']+'.pdf',invoice['pdf'],'application/pdf')})
        response.raise_for_status();media_id=response.json()['id']
        payload={'messaging_product':'whatsapp','to':recipient.removeprefix('+'),'type':'template','template':{
            'name':route['reminder_template' if reminder else 'invoice_template'],'language':{'code':route['language']},
            'components':[{'type':'header','parameters':[{'type':'document','document':{'id':media_id,'filename':invoice['number']+'.pdf'}}]},
                          {'type':'body','parameters':[{'type':'text','text':str(v)} for v in values]}]}}
        response=client.post(f'https://graph.facebook.com/{settings.version}/{route["phone_id"]}/messages',headers=headers,json=payload)
        response.raise_for_status()
        return response.json()['messages'][0]['id']


def install_followups(app,db,verified_user,membership,audit,transport,local_preview):
    routes,settings=outbound_settings()
    with db() as conn:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS reminder_plans (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            invoice_id TEXT NOT NULL REFERENCES invoices(id),actor_id TEXT NOT NULL REFERENCES users(id),channel TEXT NOT NULL CHECK(channel IN ('email','whatsapp')),
            recipient TEXT NOT NULL,next_run REAL NOT NULL,interval_days INTEGER NOT NULL CHECK(interval_days BETWEEN 1 AND 90),max_sends INTEGER NOT NULL CHECK(max_sends BETWEEN 1 AND 10),
            sent_count INTEGER NOT NULL DEFAULT 0 CHECK(sent_count>=0 AND sent_count<=max_sends),status TEXT NOT NULL CHECK(status IN ('active','running','paused','completed','stopped','cancelled')),created_at REAL NOT NULL,last_result TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,request_hash TEXT NOT NULL,UNIQUE(business_id,idempotency_key)
          );
          CREATE INDEX IF NOT EXISTS reminder_due ON reminder_plans(status,next_run);
          CREATE TABLE IF NOT EXISTS message_receipts (
            attempt_id TEXT PRIMARY KEY,invoice_id TEXT NOT NULL REFERENCES invoices(id),purpose TEXT NOT NULL,
            phone_id TEXT NOT NULL,provider_id TEXT NOT NULL UNIQUE,status TEXT NOT NULL,updated_at REAL NOT NULL
          );
        ''')
    base='/enterprise-api/businesses/{business_id}/locations/{location_id}'
    def scope(conn,bid,lid,actor,finance=False):
        member=membership(conn,bid,actor)
        allowed={'owner','manager','finance'} if finance else {'owner','manager','finance','front_desk'}
        if member['role'] not in allowed: raise HTTPException(403,'Your role cannot manage this communication')
        if member['role']!='owner' and member['location_id']!=lid: raise HTTPException(404,'Location not found')
        if not conn.execute('SELECT id FROM locations WHERE id=? AND business_id=?',(lid,bid)).fetchone(): raise HTTPException(404,'Location not found')
    def load(conn,bid,lid,iid):
        row=conn.execute('SELECT i.*,o.status order_status,o.customer_name,o.customer_contact FROM invoices i JOIN orders o ON o.id=i.order_id WHERE i.id=? AND o.business_id=? AND o.location_id=?',(iid,bid,lid)).fetchone()
        if not row: raise HTTPException(404,'Invoice not found')
        return row
    def recipient(conn,invoice,channel,email):
        contacts=contacts_for(conn,invoice['order_id'],invoice['customer_contact'])
        if channel=='email':
            value=email or contacts['customer_email']
            if not value or value not in [contacts['customer_email'],*contacts['additional_emails']]: raise HTTPException(422,'Choose a saved customer email')
            try: email_address(value)
            except ValueError: raise HTTPException(422,'The legacy customer contact is not a valid delivery email')
            return value
        if not contacts['customer_whatsapp'] or not contacts['whatsapp_consent']: raise HTTPException(409,'Record a customer WhatsApp number and permission before delivery')
        return contacts['customer_whatsapp']

    def deliver(bid,lid,iid,actor,choice,reminder=False,plan_id=None):
        if not choice.confirm: raise HTTPException(422,'Explicit confirmation is required')
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE');scope(conn,bid,lid,actor,finance=reminder)
            if plan_id and not conn.execute("SELECT id FROM reminder_plans WHERE id=? AND invoice_id=? AND status='running'",(plan_id,iid)).fetchone():
                raise HTTPException(409,'Plan was cancelled before delivery')
            invoice=load(conn,bid,lid,iid)
            address=recipient(conn,invoice,choice.channel,choice.email)
            table='customer_notices' if reminder else 'invoice_deliveries'
            previous=conn.execute(f'SELECT * FROM {table} WHERE invoice_id=? AND idempotency_key=?',(iid,choice.idempotency_key)).fetchone()
            actual_transport=('whatsapp_capture' if local_preview else 'whatsapp') if choice.channel=='whatsapp' else transport
            if previous:
                if previous['actor_id']!=actor['id'] or previous['recipient']!=address or previous['transport']!=actual_transport: raise HTTPException(409,'Save reference belongs to another delivery')
                if previous['status']=='sending' and previous['updated_at']<time.time()-120:
                    conn.execute(f"UPDATE {table} SET status='unknown',updated_at=? WHERE id=?",(time.time(),previous['id']))
                    return {'id':previous['id'],'status':'unknown','duplicate':True}
                return {'id':previous['id'],'status':previous['status'],'duplicate':True}
            if invoice['status']!='issued' or invoice['order_status']!='open': raise HTTPException(409,'Cancelled invoices cannot be delivered')
            payments=payment_summary(conn,invoice)
            today=datetime.now(timezone(timedelta(hours=1))).date().isoformat()
            if reminder and (payments['outstanding']=='0.00' or not invoice['due_on'] or invoice['due_on']>=today): raise HTTPException(409,'Reminder stopped: invoice is paid, cancelled or not overdue')
            if choice.channel=='whatsapp' and not local_preview and bid not in routes: raise HTTPException(503,'Outbound WhatsApp templates are not configured for this business')
            if conn.execute(f"SELECT id FROM {table} WHERE invoice_id=? AND status IN ('sending','accepted','captured','unknown','delivered','read') AND updated_at>?",(iid,time.time()-(86400 if reminder else 60))).fetchone():
                raise HTTPException(429,'Recent delivery exists. Review history before another attempt')
            if conn.execute(f'SELECT count(*) FROM {table} WHERE actor_id=? AND created_at>?',(actor['id'],time.time()-3600)).fetchone()[0]>=30: raise HTTPException(429,'Hourly delivery limit reached')
            values=[invoice['customer_name'],invoice['number'],payments['total'],payments['allocated'],payments['outstanding'],invoice['due_on'] or 'Not specified']
            body='\n'.join(f'{k}: {v}' for k,v in zip(['Customer','Invoice','Total NGN','Allocated NGN','Outstanding NGN','Due'],values))+'\nCheck with the business if recent payments are missing. This is not a payment receipt.'
            did=secrets.token_hex(16);now=time.time();status='captured' if local_preview else 'sending';subject=('Overdue reminder - ' if reminder else 'Invoice - ')+invoice['number']
            if reminder:
                conn.execute('INSERT INTO customer_notices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(did,bid,lid,iid,actor['id'],'overdue',address,balance_fingerprint(conn,invoice),subject,body,status,actual_transport,now,now,choice.idempotency_key,'scheduled-'+did))
            else:
                conn.execute('INSERT INTO invoice_deliveries VALUES (?,?,?,?,?,?,?,?,?,?,?)',(did,iid,actor['id'],address,actual_transport,status,now,now,choice.idempotency_key,subject,body if local_preview else ''))
            audit(conn,bid,actor['id'],f'Confirmed {choice.channel} customer delivery {did}: {status}')
        provider=None
        if not local_preview:
            try:
                if choice.channel=='whatsapp': provider=send_whatsapp(settings,routes[bid],address,invoice,values,reminder)
                else:
                    message=EmailMessage();message['From']=os.environ['LOAMY_SMTP_FROM'];message['To']=address;message['Subject']=subject;message['Message-ID']=f'<loamy-followup-{did}@localhost>';message.set_content(body)
                    message.add_attachment(invoice['pdf'],maintype='application',subtype='pdf',filename=invoice['number']+'.pdf');send_smtp(message)
                status='accepted'
            except (smtplib.SMTPRecipientsRefused,smtplib.SMTPAuthenticationError,KeyError,ValueError): status='failed'
            except httpx.HTTPStatusError as error: status='failed' if 400<=error.response.status_code<500 else 'unknown'
            except (httpx.HTTPError,OSError,smtplib.SMTPException): status='unknown'
            with db() as conn:
                conn.execute(f'UPDATE {table} SET status=?,updated_at=? WHERE id=?',(status,time.time(),did))
                if provider: conn.execute('INSERT INTO message_receipts VALUES (?,?,?,?,?,?,?)',(did,iid,'notice' if reminder else 'invoice',routes[bid]['phone_id'],provider,status,time.time()))
        return {'id':did,'status':status,'duplicate':False}

    @app.get(base+'/invoices/{invoice_id}/communications')
    def history(business_id:str,location_id:str,invoice_id:str,actor=Depends(verified_user)):
        with db() as conn:
            scope(conn,business_id,location_id,actor);invoice=load(conn,business_id,location_id,invoice_id)
            for table in ['invoice_deliveries','customer_notices']:
                conn.execute(f"UPDATE {table} SET status='unknown',updated_at=? WHERE invoice_id=? AND status='sending' AND updated_at<?",(time.time(),invoice_id,time.time()-120))
            return {'contacts':contacts_for(conn,invoice['order_id'],invoice['customer_contact']),'local_preview':local_preview,'whatsapp_configured':business_id in routes,
                    'deliveries':[dict(r) for r in conn.execute('SELECT id,recipient,transport,status,created_at FROM invoice_deliveries WHERE invoice_id=? ORDER BY created_at DESC LIMIT 30',(invoice_id,))],
                    'plans':[dict(r) for r in conn.execute('SELECT id,channel,recipient,next_run,interval_days,max_sends,sent_count,status,last_result FROM reminder_plans WHERE invoice_id=? ORDER BY created_at DESC LIMIT 20',(invoice_id,))]}

    @app.post(base+'/invoices/{invoice_id}/deliver')
    def send_invoice(business_id:str,location_id:str,invoice_id:str,data:DeliveryChoice,actor=Depends(verified_user)):
        with db() as conn:
            member=membership(conn,business_id,actor)
            if member['role']=='finance': raise HTTPException(403,'Finance cannot send original invoices')
        return deliver(business_id,location_id,invoice_id,actor,data)

    @app.post(base+'/invoices/{invoice_id}/reminder-plans',status_code=201)
    def plan(business_id:str,location_id:str,invoice_id:str,data:ReminderChoice,actor=Depends(verified_user)):
        signature=hashlib.sha256(json.dumps(data.model_dump(mode='json'),sort_keys=True).encode()).hexdigest()
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE');scope(conn,business_id,location_id,actor,finance=True)
            old=conn.execute('SELECT id,request_hash FROM reminder_plans WHERE business_id=? AND idempotency_key=?',(business_id,data.idempotency_key)).fetchone()
            if old:
                if old['request_hash']!=signature: raise HTTPException(409,'Save reference belongs to another reminder plan')
                return {'id':old['id'],'duplicate':True}
            inv=load(conn,business_id,location_id,invoice_id);address=recipient(conn,inv,data.channel,data.email)
            if not data.confirm or not inv['due_on'] or inv['status']!='issued' or payment_summary(conn,inv)['outstanding']=='0.00': raise HTTPException(422,'Confirm automation for an issued unpaid invoice with a due date')
            if data.first_run_at<time.time()-60 or data.first_run_at>time.time()+30*86400: raise HTTPException(422,'First run must be now or within 30 days')
            if conn.execute("SELECT id FROM reminder_plans WHERE invoice_id=? AND status='active'",(invoice_id,)).fetchone(): raise HTTPException(409,'Cancel the existing plan before enabling a replacement')
            if data.channel=='whatsapp' and not local_preview and business_id not in routes: raise HTTPException(503,'Configure approved WhatsApp templates first')
            pid=secrets.token_hex(16)
            conn.execute('INSERT INTO reminder_plans VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?)',(pid,business_id,location_id,invoice_id,actor['id'],data.channel,address,data.first_run_at,data.interval_days,data.max_sends,'active',time.time(),'Awaiting due date/worker',data.idempotency_key,signature))
            audit(conn,business_id,actor['id'],f'Enabled bounded {data.channel} overdue reminder plan {pid}')
        return {'id':pid,'duplicate':False}

    @app.post(base+'/invoices/{invoice_id}/reminder-plans/{plan_id}/cancel')
    def cancel(business_id:str,location_id:str,invoice_id:str,plan_id:str,actor=Depends(verified_user)):
        with db() as conn:
            scope(conn,business_id,location_id,actor,finance=True);load(conn,business_id,location_id,invoice_id)
            conn.execute("UPDATE reminder_plans SET status='cancelled',last_result='Cancelled by operator' WHERE id=? AND invoice_id=?",(plan_id,invoice_id));audit(conn,business_id,actor['id'],f'Cancelled reminder plan {plan_id}')
        return {'success':True}

    @app.post(base+'/invoices/{invoice_id}/whatsapp-permission/revoke')
    def revoke(business_id:str,location_id:str,invoice_id:str,actor=Depends(verified_user)):
        with db() as conn:
            scope(conn,business_id,location_id,actor);inv=load(conn,business_id,location_id,invoice_id)
            conn.execute('UPDATE order_contacts SET whatsapp_consent=0 WHERE order_id=?',(inv['order_id'],))
            conn.execute("UPDATE reminder_plans SET status='cancelled',last_result='WhatsApp permission withdrawn' WHERE invoice_id=? AND channel='whatsapp' AND status IN ('active','running','paused')",(invoice_id,))
            audit(conn,business_id,actor['id'],f'Recorded withdrawn WhatsApp permission for invoice {invoice_id}')
        return {'success':True}

    def run_due(bid=None,lid=None):
        # Claim before network; crash after claim pauses instead of sending a second copy.
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute("UPDATE reminder_plans SET status='paused',last_result='Worker interrupted; review history before replacing plan' WHERE status='running' AND next_run<?",(time.time()-180,))
            row=conn.execute("SELECT * FROM reminder_plans WHERE status='active' AND next_run<=? AND (? IS NULL OR business_id=?) AND (? IS NULL OR location_id=?) ORDER BY next_run,id LIMIT 1",(time.time(),bid,bid,lid,lid)).fetchone()
            if not row:return {'processed':False}
            actor=conn.execute('SELECT * FROM users WHERE id=?',(row['actor_id'],)).fetchone()
            try:
                if not actor or not actor['email_verified_at'] or (not local_preview and actor['verification_method']!='smtp'): raise HTTPException(403,'Creator is no longer verified')
                scope(conn,row['business_id'],row['location_id'],actor,finance=True)
                inv=load(conn,row['business_id'],row['location_id'],row['invoice_id'])
                if inv['status']!='issued' or payment_summary(conn,inv)['outstanding']=='0.00': raise HTTPException(409,'Stopped: paid or cancelled')
                if inv['due_on']>=datetime.now(timezone(timedelta(hours=1))).date().isoformat():
                    conn.execute('UPDATE reminder_plans SET next_run=?,last_result=? WHERE id=?',(time.time()+86400,'Waiting until overdue',row['id']))
                    return {'processed':True,'status':'waiting'}
                recipient(conn,inv,row['channel'],row['recipient'] if row['channel']=='email' else '')
            except HTTPException as error:
                conn.execute("UPDATE reminder_plans SET status='stopped',last_result=? WHERE id=?",(str(error.detail),row['id']))
                return {'processed':True,'status':'stopped'}
            conn.execute("UPDATE reminder_plans SET status='running',next_run=? WHERE id=?",(time.time(),row['id']))
        choice=DeliveryChoice(channel=row['channel'],email=row['recipient'] if row['channel']=='email' else '',confirm=True,idempotency_key=f'plan-{row["id"]}-{row["sent_count"]}')
        try:
            result=deliver(row['business_id'],row['location_id'],row['invoice_id'],actor,choice,reminder=True,plan_id=row['id'])
            success=result['status'] in {'accepted','captured','delivered','read'}
            status='completed' if success and row['sent_count']+1>=row['max_sends'] else 'active' if success else 'paused'
            reason=result['status']
        except HTTPException as error:
            success=False;status='paused';reason=str(error.detail)
        with db() as conn:
            # A concurrent cancellation/opt-out must never reactivate a running plan.
            conn.execute("UPDATE reminder_plans SET status=?,sent_count=?,next_run=?,last_result=? WHERE id=? AND status='running'",(status,row['sent_count']+int(success),time.time()+row['interval_days']*86400,reason,row['id']))
        return {'processed':True,'status':status,'result':reason}
    app.state.run_due_followup=run_due

    @app.post(base+'/followups/run-local')
    def simulate_due(business_id:str,location_id:str,actor=Depends(verified_user)):
        with db() as conn:scope(conn,business_id,location_id,actor,finance=True)
        if not local_preview:raise HTTPException(404,'Not found')
        return run_due(business_id,location_id)

    @app.get(base+'/front-desk-alerts')
    def alerts(business_id:str,location_id:str,actor=Depends(verified_user)):
        with db() as conn:
            scope(conn,business_id,location_id,actor)
            rows=conn.execute("SELECT i.id,i.number,i.status,i.due_on,o.id order_id,o.customer_name,o.total_minor,coalesce((SELECT sum(a.amount_minor) FROM payment_allocations a JOIN financial_records r ON r.id=a.record_id WHERE a.invoice_id=i.id AND a.reversed_at IS NULL AND r.status='posted'),0) paid FROM invoices i JOIN orders o ON o.id=i.order_id WHERE o.business_id=? AND o.location_id=? AND i.status='issued' ORDER BY i.issued_at DESC LIMIT 1001",(business_id,location_id)).fetchall()
            result=[]
            today=datetime.now(timezone(timedelta(hours=1))).date().isoformat()
            for r in rows[:1000]:
                from workspace_payments import payment_totals
                p=payment_totals(r['total_minor'],r['paid'],r['status'])
                if p['outstanding']!='0.00' and (p['status']=='part_paid' or (r['due_on'] and r['due_on']<today)):
                    result.append({'invoice_id':r['id'],'order_id':r['order_id'],'number':r['number'],'customer':r['customer_name'],'remaining':p['outstanding'],'status':p['status'],'overdue':bool(r['due_on'] and r['due_on']<today)})
        return {'alerts':result,'truncated':len(rows)>1000,'as_of':time.time(),'note':'Current alerts update on refresh; no desktop push permission is used.'}

    def provider_status(conn,phone_id,statuses):
            for item in statuses[:100]:
                if not isinstance(item,dict) or item.get('status') not in {'sent','delivered','read','failed'}:continue
                receipt=conn.execute('SELECT * FROM message_receipts WHERE phone_id=? AND provider_id=?',(phone_id,item.get('id',''))).fetchone()
                if not receipt:continue
                status='accepted' if item['status']=='sent' else item['status']
                rank={'accepted':0,'delivered':1,'read':2,'failed':3}
                if rank.get(status,0)<=rank.get(receipt['status'],0):continue
                # A later contradictory failure must not undo a confirmed read/delivery.
                if status=='failed' and receipt['status'] in {'delivered','read'}:continue
                conn.execute('UPDATE message_receipts SET status=?,updated_at=? WHERE attempt_id=?',(status,time.time(),receipt['attempt_id']))
                table='customer_notices' if receipt['purpose']=='notice' else 'invoice_deliveries'
                conn.execute(f'UPDATE {table} SET status=?,updated_at=? WHERE id=?',(status,time.time(),receipt['attempt_id']))
                if status=='failed':conn.execute("UPDATE reminder_plans SET status='paused',last_result='Provider reported failure; review before replacing plan' WHERE invoice_id=? AND channel='whatsapp' AND status='active'",(receipt['invoice_id'],))
    app.state.whatsapp_delivery_status=provider_status
