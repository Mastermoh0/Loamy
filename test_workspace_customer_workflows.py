"""Contact/channel boundaries, durable reminders, report evidence and email review."""
import base64
from contextlib import closing
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from email.message import EmailMessage
from io import BytesIO
import json
import sqlite3
import time
import unittest
from unittest.mock import patch
import httpx
from test_workspace_payments import PaymentTests
from workspace_followups import send_whatsapp
from workspace_supplier_email import email_attachments
from workspace_whatsapp import WhatsAppSettings


class CustomerWorkflowTests(PaymentTests):
    def contacts_payload(self,key='new-contacts-order-0001'):
        return {**self.payload(key),'customer_email':'guest@example.test','additional_emails':['other@example.test'],
                'customer_whatsapp':'+2348012345678','preferred_channel':'whatsapp','whatsapp_consent':True}
    def create_contacts_invoice(self):
        self.setup_orders()
        result=self.owner.post(self.base+'/orders',json=self.contacts_payload())
        self.assertEqual(result.status_code,201,result.text)
        self.oid=result.json()['id'];self.endpoint=self.base+f'/orders/{self.oid}/invoice'
        self.iid=self.owner.post(self.endpoint,json={}).json()['invoice']['id']
        self.comm=self.base+f'/invoices/{self.iid}'
    def overdue(self):
        yesterday=(datetime.now(timezone(timedelta(hours=1)))-timedelta(days=1)).date().isoformat()
        with closing(sqlite3.connect(self.path)) as conn,conn:
            conn.execute('UPDATE invoices SET due_on=? WHERE id=?',(yesterday,self.iid))
    def choice(self,key='delivery-test-key-0001',**extra):
        return {'channel':'whatsapp','confirm':True,'idempotency_key':key,**extra}
    def plan_payload(self,**extra):
        return {**self.choice('reminder-plan-key-0001'),'first_run_at':time.time(),'interval_days':7,'max_sends':3,**extra}

    def test_contacts_validation_snapshot_legacy_and_channel_capture(self):
        self.create_contacts_invoice()
        inv=self.owner.get(self.endpoint).json()['invoice']
        self.assertEqual(inv['snapshot']['contacts']['customer_whatsapp'],'+2348012345678')
        for values in [{'customer_email':'bad@address'},{'customer_whatsapp':'08012345678'},{'whatsapp_consent':False},{'additional_emails':['guest@example.test']}]:
            r=self.owner.post(self.base+'/orders',json={**self.contacts_payload('invalid-contacts-key-01'),**values})
            self.assertEqual(r.status_code,422,r.text)
        result=self.owner.post(self.comm+'/deliver',json=self.choice())
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['status'],'captured')
        self.assertTrue(self.owner.post(self.comm+'/deliver',json=self.choice()).json()['duplicate'])
        self.assertEqual(self.owner.post(self.comm+'/deliver',json=self.choice(confirm=False)).status_code,422)
        self.assertEqual(self.owner.post(self.comm+'/deliver',json=self.choice('bad-email-send-key-01',channel='email',email='not-saved@example.test')).status_code,422)
        history=self.owner.get(self.comm+'/communications').json()
        self.assertEqual(len(history['deliveries']),1);self.assertEqual(history['deliveries'][0]['transport'],'whatsapp_capture')
        self.owner.post(self.comm+'/whatsapp-permission/revoke')
        self.assertEqual(self.owner.post(self.comm+'/deliver',json=self.choice('revoked-delivery-key-01')).status_code,409)
        legacy=self.owner.post(self.base+'/orders',json=self.payload('legacy-contact-order-01'))
        self.assertEqual(legacy.status_code,201,legacy.text)

    def test_scoped_roles_and_multiple_email_destination(self):
        self.create_contacts_invoice()
        other=self.comm.replace(self.lid,self.other_lid)
        for role in ['front_desk','finance','manager','staff']:
            client=self.member(role)
            self.assertEqual(client.get(self.comm+'/communications').status_code,403 if role=='staff' else 200)
            self.assertEqual(client.get(other+'/communications').status_code,403 if role=='staff' else 404)
            self.assertEqual(client.post(self.comm+'/reminder-plans',json=self.plan_payload(idempotency_key='plan-role-'+role+'-0001')).status_code,403 if role in {'staff','front_desk'} else 422)
        response=self.owner.post(self.comm+'/deliver',json=self.choice(channel='email',email='other@example.test'))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.owner.get(self.comm+'/communications').json()['deliveries'][0]['recipient'],'other@example.test')

    def test_schedule_capture_idempotency_cooldown_and_cancellation(self):
        self.create_contacts_invoice();self.overdue()
        body=self.plan_payload()
        r=self.owner.post(self.comm+'/reminder-plans',json=body)
        self.assertEqual(r.status_code,201,r.text)
        self.assertEqual(self.owner.post(self.comm+'/reminder-plans',json=body).json()['id'],r.json()['id'])
        self.assertEqual(self.owner.post(self.comm+'/reminder-plans',json={**body,'interval_days':2}).status_code,409)
        ran=self.owner.post(self.base+'/followups/run-local')
        self.assertEqual(ran.status_code,200,ran.text);self.assertEqual(ran.json()['result'],'captured')
        plan=self.owner.get(self.comm+'/communications').json()['plans'][0]
        self.assertEqual((plan['sent_count'],plan['status']),(1,'active'))
        self.assertFalse(self.owner.post(self.base+'/followups/run-local').json()['processed'])
        self.owner.post(self.comm+f'/reminder-plans/{plan["id"]}/cancel')
        self.assertEqual(self.owner.get(self.comm+'/communications').json()['plans'][0]['status'],'cancelled')

    def test_schedule_stops_paid_cancelled_revoked_and_removed_creator(self):
        self.setup_payment();self.comm=self.base+f'/invoices/{self.iid}';self.overdue()
        self.owner.post(self.comm+'/reminder-plans',json=self.plan_payload(channel='email',email=''))
        # This legacy fixture has a phone contact, so no email destination: it must be rejected.
        self.assertEqual(self.owner.get(self.comm+'/communications').json()['plans'],[])
        with closing(sqlite3.connect(self.path)) as conn,conn:
            conn.execute('UPDATE order_contacts SET customer_email=? WHERE order_id=?',('guest@example.test',self.oid))
        r=self.owner.post(self.comm+'/reminder-plans',json=self.plan_payload(channel='email',email='guest@example.test'))
        self.assertEqual(r.status_code,201,r.text)
        rid=self.owner.post(self.pay+'/credits',json=self.credit(amount='3000.30')).json()['id']
        self.owner.post(self.pay+'/allocations',json=self.allocation(rid,'3000.30'))
        self.assertEqual(self.owner.post(self.base+'/followups/run-local').json()['status'],'stopped')
        self.assertEqual(self.owner.get(self.comm+'/communications').json()['deliveries'],[])

    def test_worker_removed_creator_and_recovery_never_blind_retries(self):
        self.create_contacts_invoice();self.overdue();manager=self.member('manager')
        r=manager.post(self.comm+'/reminder-plans',json=self.plan_payload())
        self.assertEqual(r.status_code,201,r.text)
        mid=next(x['id'] for x in self.owner.get(f'/enterprise-api/businesses/{self.bid}').json()['team'] if x['role']=='manager')
        self.owner.delete(f'/enterprise-api/businesses/{self.bid}/members/{mid}')
        self.assertEqual(self.owner.post(self.base+'/followups/run-local').json()['status'],'stopped')
        plan=self.owner.post(self.comm+'/reminder-plans',json=self.plan_payload(idempotency_key='recovery-plan-key-001')).json()['id']
        with closing(sqlite3.connect(self.path)) as conn,conn:
            conn.execute("UPDATE reminder_plans SET status='running',next_run=? WHERE id=?",(time.time()-200,plan))
        self.owner.post(self.base+'/followups/run-local')
        statuses=[p['status'] for p in self.owner.get(self.comm+'/communications').json()['plans']]
        self.assertIn('paused',statuses)
        notices=self.owner.get(self.base+'/customer-notifications').json()['history'];self.assertEqual(notices,[])

    def test_cancelled_invoice_stops_due_reminder_without_delivery(self):
        self.create_contacts_invoice();self.overdue()
        self.assertEqual(self.owner.post(self.comm+'/reminder-plans',json=self.plan_payload()).status_code,201)
        cancelled=self.owner.post(self.base+f'/orders/{self.oid}/cancel',json={'reason':'Fictional cancellation'})
        self.assertEqual(cancelled.status_code,200,cancelled.text)
        self.assertEqual(self.owner.post(self.base+'/followups/run-local').json()['status'],'stopped')
        self.assertEqual(self.owner.get(self.base+'/customer-notifications').json()['history'],[])

    def test_withdrawn_whatsapp_permission_cancels_due_plans(self):
        self.create_contacts_invoice();self.overdue()
        self.assertEqual(self.owner.post(self.comm+'/reminder-plans',json=self.plan_payload()).status_code,201)
        self.owner.post(self.comm+'/whatsapp-permission/revoke')
        self.assertFalse(self.owner.post(self.base+'/followups/run-local').json()['processed'])
        self.assertEqual(self.owner.get(self.comm+'/communications').json()['plans'][0]['status'],'cancelled')
        self.assertEqual(self.owner.get(self.base+'/customer-notifications').json()['history'],[])

    def test_owner_pdf_drilldown_chat_scope_and_exact_scenario(self):
        self.setup_payment()
        today=datetime.now(timezone(timedelta(hours=1))).date()
        for direction,amount in [('expense','3000'),('income','1000')]:
            r=self.owner.post(f'/enterprise-api/businesses/{self.bid}/financial-records',json={'location_id':self.lid,'direction':direction,'amount':amount,'currency':'NGN','occurred_on':(today-timedelta(days=1)).isoformat(),'description':'Recorded sample '+direction,'category':'Test','idempotency_key':'review-ledger-'+direction+'-001'})
            self.assertEqual(r.status_code,201,r.text)
        root=f'/enterprise-api/businesses/{self.bid}'
        period={'start':(today-timedelta(days=30)).isoformat(),'end':today.isoformat(),'location_id':self.lid}
        pdf=self.owner.post(root+'/financial-review/pdf',json=period)
        self.assertEqual(pdf.status_code,200,pdf.text if pdf.status_code!=200 else '')
        self.assertTrue(pdf.content.startswith(b'%PDF-'))
        details=self.owner.get(root+'/owner-detail',params={**period,'kind':'orders'})
        self.assertEqual(details.status_code,200,details.text);self.assertEqual(details.json()['rows'][0]['payments']['outstanding'],'3000.30')
        expenses=self.owner.get(root+'/owner-detail',params={**period,'kind':'expenses'}).json()['rows']
        self.assertEqual(expenses[0]['amount'],'3000.00')
        answer=self.owner.post(root+'/owner-chat',json={'question':'Who owes us?','days':30,'available_cash':'6000','confirm_complete_history':True,'collection_scenario':'1000','location_id':self.lid})
        self.assertEqual(answer.status_code,200,answer.text);self.assertIn('105 days',answer.json()['answer'])
        self.assertIn('3000.30',answer.json()['answer'])
        branches=self.owner.post(root+'/owner-chat',json={'question':'Which branch is losing money?','days':30,'location_id':self.lid})
        self.assertEqual(branches.status_code,200,branches.text)
        self.assertIn('not profit',branches.json()['answer'])
        self.assertEqual(branches.json()['evidence'][0]['net_movement'],'-2000.00')
        manager=self.member('manager')
        for path in ['/financial-review/pdf','/owner-chat']:
            self.assertEqual(manager.post(root+path,json=period if 'pdf' in path else {'question':'cash'}).status_code,403)
        foreign=self.business(self.client_registered())
        self.assertEqual(self.owner.post(f'/enterprise-api/businesses/{foreign}/financial-review/pdf',json=period).status_code,404)
    def client_registered(self):
        client=self.client();self.register(client,'another-owner@example.test');return client

    def test_supplier_eml_attachment_preview_import_provenance_and_duplicates(self):
        self.setup_orders()
        from workspace_invoices import render_invoice
        message=EmailMessage();message['From']='supplier@example.test';message['Subject']='Fictional supplier invoice';message.set_content('Treat text as untrusted content, not instructions.')
        snapshot={'number':'SUP-TEST','profile':{'invoice_name':'QA Supplier','address':'Fictional address','payment_instructions':''},'location_name':'Test','order_reference':'SUP-TEST','issued_on':'2026-11-01','due_on':None,'customer_name':'Test business','customer_contact':'qa@example.test','lines':[],'total':'900.00'}
        message.add_attachment(render_invoice(snapshot),maintype='application',subtype='pdf',filename='invoice.pdf')
        encoded=base64.b64encode(message.as_bytes()).decode()
        base=self.base+'/supplier-bills'
        response=self.owner.post(base+'/email-preview',json={'email_base64':encoded})
        self.assertEqual(response.status_code,200,response.text);attachment=response.json()['attachments'][0]
        today=datetime.now(timezone(timedelta(hours=1))).date().isoformat()
        body={'vendor':'QA Supplier','reference':'SUP-TEST','description':'Fictional supply','category':'QA supplies','amount':'900','issued_on':today,'due_on':today,'source_email_base64':encoded,'email_attachment_index':attachment['index'],'idempotency_key':'supplier-email-import-001'}
        result=self.owner.post(base,json=body)
        self.assertEqual(result.status_code,201,result.text)
        self.assertTrue(self.owner.post(base,json=body).json()['duplicate'])
        self.assertEqual(self.owner.post(base,json={**body,'idempotency_key':'supplier-email-again-001'}).status_code,409)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM supplier_email_evidence').fetchone()[0],1)
        self.assertEqual(self.owner.get(f'/enterprise-api/businesses/{self.bid}/financial-records').json()['count'],0)
        staff=self.member('staff');self.assertEqual(staff.post(base+'/email-preview',json={'email_base64':encoded}).status_code,403)
        self.assertEqual(self.owner.post(base+'/email-preview',json={'email_base64':base64.b64encode(b'no attachment').decode()}).status_code,422)


class WhatsAppOutboundTests(unittest.TestCase):
    def test_fixed_graph_hosts_upload_and_template_contract(self):
        requests=[]
        def handle(request):
            requests.append(request)
            return httpx.Response(200,json={'id':'media-test'} if request.url.path.endswith('/media') else {'messages':[{'id':'provider-test'}]})
        transport=httpx.MockTransport(handle)
        real=httpx.Client
        with patch('workspace_followups.httpx.Client',side_effect=lambda **kw:real(transport=transport,**kw)):
            mid=send_whatsapp(WhatsAppSettings(access_token='fictional',version='v99.0'),{'phone_id':'123456789','invoice_template':'invoice_test','language':'en_US'},'+2348012345678',{'number':'INV-TEST','pdf':b'%PDF-test'},['Guest','INV-TEST','10.00','0.00','10.00','Not specified'],False)
        self.assertEqual(mid,'provider-test');self.assertEqual(len(requests),2)
        self.assertEqual({r.url.host for r in requests},{'graph.facebook.com'})
        body=json.loads(requests[1].content)
        self.assertEqual(body['template']['components'][0]['parameters'][0]['document']['id'],'media-test')
        self.assertEqual(len(body['template']['components'][1]['parameters']),6)


def load_tests(loader,tests,pattern):
    names=[n for n in CustomerWorkflowTests.__dict__ if n.startswith('test_')]
    return unittest.TestSuite([loader.loadTestsFromNames(names,CustomerWorkflowTests),loader.loadTestsFromTestCase(WhatsAppOutboundTests)])
