"""Owner drill-down, recorded-data chat and a factual cash-history PDF."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from html import escape
from io import BytesIO
import time
from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import ParagraphStyle
from workspace_finances import money
from workspace_reports import InsightInput, lagos_today
from workspace_payments import payment_totals


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    location_id: str | None = None
    start: date
    end: date


class OwnerQuestion(InsightInput):
    question: str = Field(min_length=2, max_length=500)
    collection_scenario: Decimal = Field(default=Decimal('0'), ge=0, max_digits=14, decimal_places=2)


def render_history(business, period, rows, debtors, coverage):
    out = BytesIO()
    style = ParagraphStyle('Review', fontName='InvoiceSans', fontSize=9, leading=13, spaceAfter=8, wordWrap='CJK')
    title = ParagraphStyle('ReviewTitle', parent=style, fontName='InvoiceBold', fontSize=16, leading=22)
    def p(value, s=style):
        return Paragraph(escape(str(value)), s)
    def table(headers, data):
        t = Table([[p(v) for v in row] for row in [headers, *data]], repeatRows=1, hAlign='LEFT', colWidths=[150,110,110,110])
        t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),'#e9edde'),('LINEBELOW',(0,0),(-1,-1),.3,'#d5d9cc')]))
        return t
    income = sum(r['amount_minor'] for r in rows if r['direction']=='income')
    expense = sum(r['amount_minor'] for r in rows if r['direction']=='expense')
    story = [p('Recorded financial history',title),p(business),p(f'{period.start} to {period.end} inclusive. Currency: NGN. Calendar: Africa/Lagos.'),
             p(f'Posted income {money(income)}; posted expenses {money(expense)}; net cash movement {money(income-expense)}.'),
             p(coverage), p('This report describes recorded cash movements, not audited revenue, profit, bank balances, creditworthiness or a lending recommendation. Unrecorded movements and internal transfers may change the picture. No owner commitment score is inferred.')]
    for label, key in [('Monthly',lambda d:d.strftime('%Y-%m')),('Weekly (Monday start)',lambda d:(d-timedelta(days=d.weekday())).isoformat()),('Daily',lambda d:d.isoformat())]:
        grouped=defaultdict(lambda:[0,0])
        for r in rows:
            grouped[key(date.fromisoformat(r['occurred_on']))][r['direction']=='expense']+=r['amount_minor']
        story += [Spacer(1,12),p(label,title),table(['Period','Money in (NGN)','Money out (NGN)','Net (NGN)'], [[k,money(v[0]),money(v[1]),money(v[0]-v[1])] for k,v in sorted(grouped.items())] if grouped else [['No posted records','0.00','0.00','0.00']])]
    story += [Spacer(1,12),p('Current receivables',title),p('Balances are current at generation, across all invoice dates. Due dates are agreed dates, not predictions or guarantees of collection.')]
    for d in debtors:
        story.append(p(f'{d["number"]} | {d["customer"]} | Owed NGN {d["outstanding"]} | Due {d["due_on"] or "not specified"}'))
    if not debtors: story.append(p('No outstanding issued invoices in this scope.'))
    story += [p('Supporting records: download the financial-history ZIP for the same location/dates, including original invoices and linked receipts. This PDF does not replace those originals.'),p(f'Generated at Unix timestamp {time.time():.0f}.')]
    SimpleDocTemplate(out,leftMargin=42,rightMargin=42,topMargin=42,bottomMargin=42,title='Recorded financial history').build(story)
    return out.getvalue()


def install_owner_tools(app, db, verified_user, membership, audit):
    base='/enterprise-api/businesses/{business_id}'
    def scope(conn,bid,actor,lid):
        membership(conn,bid,actor,owner=True)
        if lid and not conn.execute('SELECT id FROM locations WHERE id=? AND business_id=?',(lid,bid)).fetchone():
            raise HTTPException(404,'Location not found')
    def period(start,end):
        if start>end or end>lagos_today() or (end-start).days>365:
            raise HTTPException(422,'Choose up to 366 days, ending today or earlier')
    def receivables(conn,bid,lid):
        result=[]
        for index,r in enumerate(conn.execute("SELECT i.id,i.number,i.status,i.due_on,o.customer_name,o.total_minor,coalesce((SELECT sum(a.amount_minor) FROM payment_allocations a JOIN financial_records f ON f.id=a.record_id WHERE a.invoice_id=i.id AND a.reversed_at IS NULL AND f.status='posted'),0) paid FROM invoices i JOIN orders o ON o.id=i.order_id WHERE o.business_id=? AND (? IS NULL OR o.location_id=?) AND i.status='issued' ORDER BY i.number LIMIT 5001",(bid,lid,lid))):
            if index>=5000: raise HTTPException(413,'Select a location to reduce the invoice count')
            payments=payment_totals(r['total_minor'],r['paid'],r['status'])
            if payments['outstanding']!='0.00': result.append({'number':r['number'],'customer':r['customer_name'],'due_on':r['due_on'],'outstanding':payments['outstanding']})
        return result

    @app.get(base+'/owner-detail')
    def detail(business_id:str,kind:str,location_id:str|None=None,start:date|None=None,end:date|None=None,actor=Depends(verified_user)):
        end=end or lagos_today();start=start or end-timedelta(days=29);period(start,end)
        with db() as conn:
            scope(conn,business_id,actor,location_id)
            params=(business_id,location_id,location_id,start.isoformat(),end.isoformat())
            if kind=='orders':
                rows=[dict(r) for r in conn.execute('SELECT o.id,o.location_id,l.name location,o.reference,o.customer_name,o.order_date,o.status,o.total_minor,i.id invoice_id,i.number invoice_number,i.status invoice_status FROM orders o JOIN locations l ON l.id=o.location_id LEFT JOIN invoices i ON i.order_id=o.id WHERE o.business_id=? AND (? IS NULL OR o.location_id=?) AND o.order_date>=? AND o.order_date<=? ORDER BY o.created_at DESC LIMIT 251',params)]
                for r in rows:
                    r['amount']=money(r.pop('total_minor'))
                    if r['invoice_id']:
                        inv=conn.execute('SELECT * FROM invoices WHERE id=?',(r['invoice_id'],)).fetchone()
                        from workspace_payments import payment_summary
                        r['payments']=payment_summary(conn,inv)
                        r['pdf_path']=f'/businesses/{business_id}/locations/{r["location_id"]}/orders/{r["id"]}/invoice/pdf'
            elif kind=='expenses':
                rows=[dict(r) for r in conn.execute("SELECT r.id,l.name location,r.description,r.category,r.amount_minor,r.occurred_on,u.name recorded_by,e.id expense_id,e.revision,s.name submitter FROM financial_records r JOIN locations l ON l.id=r.location_id JOIN users u ON u.id=r.actor_id LEFT JOIN expense_submissions e ON e.record_id=r.id LEFT JOIN users s ON s.id=e.submitter_id WHERE r.business_id=? AND (? IS NULL OR r.location_id=?) AND r.occurred_on>=? AND r.occurred_on<=? AND r.direction='expense' AND r.status='posted' ORDER BY r.occurred_on DESC,r.id LIMIT 251",params)]
                for r in rows:
                    r['amount']=money(r.pop('amount_minor'))
                    if r['expense_id']:
                        lid=conn.execute('SELECT location_id FROM expense_submissions WHERE id=?',(r['expense_id'],)).fetchone()[0]
                        r['receipt_path']=f'/businesses/{business_id}/locations/{lid}/expenses/{r["expense_id"]}/receipt/{r["revision"]}'
            else: raise HTTPException(422,'Choose orders or expenses')
        return {'rows':rows[:250],'truncated':len(rows)>250,'period':{'start':start.isoformat(),'end':end.isoformat()},'scope':'Orders and posted expenses follow selected dates. Invoice balances are current.'}

    @app.post(base+'/financial-review/pdf')
    def review(business_id:str,data:ReviewInput,actor=Depends(verified_user)):
        period(data.start,data.end)
        with db() as conn:
            scope(conn,business_id,actor,data.location_id)
            rows=[dict(r) for r in conn.execute("SELECT amount_minor,direction,occurred_on FROM financial_records WHERE business_id=? AND (? IS NULL OR location_id=?) AND occurred_on>=? AND occurred_on<=? AND status='posted' ORDER BY occurred_on,id LIMIT 5001",(business_id,data.location_id,data.location_id,data.start.isoformat(),data.end.isoformat()))]
            if len(rows)>5000: raise HTTPException(413,'Reduce the period or select one location; this PDF supports 5,000 movements')
            debtors=receivables(conn,business_id,data.location_id)
            business=conn.execute('SELECT name FROM businesses WHERE id=?',(business_id,)).fetchone()[0]
            location=conn.execute('SELECT name FROM locations WHERE id=?',(data.location_id,)).fetchone()[0] if data.location_id else 'All locations'
            coverage=f'Scope: {location}. {len(rows)} posted records. First included record: {rows[0]["occurred_on"] if rows else "none"}. Complete history has not been independently verified.'
            audit(conn,business_id,actor['id'],'Downloaded recorded financial-history PDF')
        return Response(render_history(business,data,rows,debtors,coverage),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="loamy-financial-review.pdf"'})

    @app.post(base+'/owner-chat')
    def chat(business_id:str,data:OwnerQuestion,actor=Depends(verified_user)):
        query=data.question.casefold()
        result=app.state.recorded_insights(business_id,InsightInput(**data.model_dump(exclude={'question','collection_scenario'})),actor)
        if any(w in query for w in ['owe','debt','collect','receivable']):
            total=sum((Decimal(d['outstanding']) for d in result['debtors']),Decimal(0))
            amount=min(total,data.collection_scenario)
            answer=f'Current recorded receivables: NGN {total:.2f} across {len(result["debtors"])} invoices. Collection dates are not guaranteed.'
            if amount:
                if data.available_cash is None or not data.confirm_complete_history or result['net_burn']=='0.00':
                    answer+=' Enter available cash and confirm history coverage with positive net burn to model collection runway.'
                else:
                    days=int((data.available_cash+amount)*100)*data.days//int(Decimal(result['net_burn'])*100)
                    answer+=f' If NGN {amount:.2f} were collected immediately, modeled runway would be {days} days. This assumes receipt, not a promised outcome.'
            evidence=result['debtors']
        elif any(w in query for w in ['subscr','recurr','cancel','saving']):
            answer=f'Active tracked commitments have an approximate monthly cost of NGN {result["declared_monthly_commitments"]}. Review usefulness and actual contract terms before cancelling with the supplier. Tracking cancellation does not stop billing.'
            evidence=result['commitments']+result['recurring_candidates']
        elif any(w in query for w in ['cash','runway','burn','losing','money','branch','location']):
            answer=f'Recorded inflow NGN {result["inflow"]}; outflow NGN {result["outflow"]}; net burn NGN {result["net_burn"]} over {data.days} completed days. '+(f'Entered-cash runway: {result["runway_days"]} days.' if result['runway_days'] is not None else result['runway_reason'])
            evidence=[{'period':result['period'],'record_count':result['record_count'],'first_record_date':result['first_record_date']}]
            if any(w in query for w in ['branch','location','losing']):
                with db() as conn:
                    scope(conn,business_id,actor,data.location_id)
                    branches=conn.execute("SELECT l.name,coalesce(sum(CASE WHEN r.direction='income' THEN r.amount_minor ELSE 0 END),0) inflow,coalesce(sum(CASE WHEN r.direction='expense' THEN r.amount_minor ELSE 0 END),0) outflow FROM locations l LEFT JOIN financial_records r ON r.location_id=l.id AND r.business_id=l.business_id AND r.status='posted' AND r.occurred_on>=? AND r.occurred_on<=? WHERE l.business_id=? AND (? IS NULL OR l.id=?) GROUP BY l.id,l.name ORDER BY l.name LIMIT 1001",(result['period']['start'],result['period']['end'],business_id,data.location_id,data.location_id)).fetchall()
                    if len(branches)>1000:raise HTTPException(413,'Choose a location; the branch comparison supports 1,000 locations')
                    evidence=[{'location':r['name'],'inflow':money(r['inflow']),'outflow':money(r['outflow']),'net_movement':money(r['inflow']-r['outflow'])} for r in branches]
                negatives=[r for r in evidence if Decimal(r['net_movement'])<0]
                answer+=' Locations with recorded outflow above inflow: '+(', '.join(r['location']+' (NGN '+r['net_movement']+')' for r in negatives) if negatives else 'none in this observation period')+'. This is net cash movement, not profit.'
        else:
            answer='I can answer recorded-data questions about cash flow/runway, debtors/collection scenarios, and subscriptions. Choose a topic or rephrase using those terms.';evidence=[]
        return {'answer':answer,'evidence':evidence,'limitations':result['limitations'],'engine':'Recorded-data assistant; no generative model or live bank access'}
