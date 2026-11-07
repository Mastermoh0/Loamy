"""Owner-only consolidation over canonical records, never inferred bank balances."""
from datetime import date, datetime, timedelta, timezone
import time
from fastapi import Depends, HTTPException
from workspace_finances import money


def install_owner_dashboard(app, db, verified_user, membership):
    @app.get('/enterprise-api/businesses/{business_id}/owner-dashboard')
    def dashboard(business_id: str, start: date | None = None, end: date | None = None,
                  location_id: str | None = None, actor=Depends(verified_user)):
        today = datetime.now(timezone(timedelta(hours=1))).date()
        end = end or today
        start = start or end - timedelta(days=29)
        if start > end or end > today or (end - start).days > 365:
            raise HTTPException(422, 'Choose an ordered date range of up to 366 days, ending today or earlier')
        with db() as conn:
            membership(conn, business_id, actor, owner=True)
            locations = conn.execute('SELECT id,name FROM locations WHERE business_id=? ORDER BY created_at,id', (business_id,)).fetchall()
            if location_id and location_id not in {row['id'] for row in locations}:
                raise HTTPException(404, 'Location not found')
            selected = [row for row in locations if not location_id or row['id'] == location_id]
            rows = {row['id']: {'id': row['id'], 'name': row['name'], 'inflow': 0, 'outflow': 0, 'records': 0,
                              'orders': 0, 'open_orders': 0, 'cancelled_orders': 0, 'order_value': 0,
                              'invoice_total': 0, 'allocated': 0, 'outstanding': 0, 'overpayment': 0,
                              'overdue': 0, 'unpaid_invoices': 0, 'pending_review': 0, 'approved_unposted': 0, 'payables': 0, 'overdue_payables': 0} for row in selected}
            sources = {}
            latest = None
            for record in conn.execute("SELECT location_id,direction,amount_minor,source,created_at FROM financial_records WHERE business_id=? AND status='posted' AND occurred_on>=? AND occurred_on<=?", (business_id, start.isoformat(), end.isoformat())):
                if record['location_id'] not in rows:
                    continue
                row = rows[record['location_id']]
                row['inflow' if record['direction'] == 'income' else 'outflow'] += record['amount_minor']
                row['records'] += 1
                sources[record['source']] = sources.get(record['source'], 0) + 1
                latest = max(latest or 0, record['created_at'])
            for order in conn.execute('SELECT location_id,status,total_minor FROM orders WHERE business_id=? AND order_date>=? AND order_date<=?', (business_id, start.isoformat(), end.isoformat())):
                if order['location_id'] in rows:
                    row = rows[order['location_id']]
                    row['orders'] += 1
                    row['open_orders' if order['status'] == 'open' else 'cancelled_orders'] += 1
                    if order['status'] == 'open':
                        row['order_value'] += order['total_minor']
            # Receivables are current, across all issued invoices, independent of the flow date filter.
            for invoice in conn.execute("SELECT i.id,i.due_on,o.location_id,o.total_minor,coalesce(a.paid,0) paid FROM invoices i JOIN orders o ON o.id=i.order_id LEFT JOIN (SELECT p.invoice_id,sum(p.amount_minor) paid FROM payment_allocations p JOIN financial_records r ON r.id=p.record_id WHERE p.reversed_at IS NULL AND r.status='posted' GROUP BY p.invoice_id) a ON a.invoice_id=i.id WHERE o.business_id=? AND i.status='issued'", (business_id,)):
                if invoice['location_id'] not in rows:
                    continue
                row = rows[invoice['location_id']]
                total, paid = invoice['total_minor'], int(invoice['paid'])
                outstanding = max(total - paid, 0)
                row['invoice_total'] += total
                row['allocated'] += paid
                row['outstanding'] += outstanding
                row['overpayment'] += max(paid - total, 0)
                row['unpaid_invoices'] += int(outstanding > 0)
                if invoice['due_on'] and invoice['due_on'] < today.isoformat():
                    row['overdue'] += outstanding
            for expense in conn.execute('SELECT location_id,status,count(*) count FROM expense_submissions WHERE business_id=? GROUP BY location_id,status', (business_id,)):
                if expense['location_id'] in rows and expense['status'] in {'submitted', 'approved'}:
                    key = 'pending_review' if expense['status'] == 'submitted' else 'approved_unposted'
                    rows[expense['location_id']][key] += expense['count']
            accounts = []
            for bill in conn.execute("SELECT b.location_id,b.amount_minor,b.due_on,coalesce(p.paid,0) paid FROM supplier_bills b LEFT JOIN (SELECT bill_id,sum(amount_minor) paid FROM supplier_payments WHERE reversed_at IS NULL GROUP BY bill_id) p ON p.bill_id=b.id WHERE b.business_id=? AND b.status='open'", (business_id,)):
                if bill['location_id'] in rows:
                    owed = max(0, bill['amount_minor'] - int(bill['paid']))
                    rows[bill['location_id']]['payables'] += owed
                    if bill['due_on'] < today.isoformat():
                        rows[bill['location_id']]['overdue_payables'] += owed
            for account in conn.execute('SELECT * FROM payment_accounts WHERE business_id=? ORDER BY location_id,name,id', (business_id,)):
                if account['location_id'] not in rows:
                    continue
                values = conn.execute("SELECT r.amount_minor,coalesce(a.used,0) used FROM payment_evidence e JOIN financial_records r ON r.id=e.record_id LEFT JOIN (SELECT record_id,sum(amount_minor) used FROM payment_allocations WHERE reversed_at IS NULL GROUP BY record_id) a ON a.record_id=r.id WHERE e.account_id=? AND r.business_id=? AND r.status='posted' AND r.occurred_on>=? AND r.occurred_on<=?", (account['id'], business_id, start.isoformat(), end.isoformat())).fetchall()
                credits = sum(row['amount_minor'] for row in values)
                used = sum(int(row['used']) for row in values)
                accounts.append({'id': account['id'], 'location_id': account['location_id'], 'location': rows[account['location_id']]['name'],
                                 'name': account['name'], 'reference': account['account_reference'], 'recorded_credits': money(credits),
                                 'allocated': money(used), 'unallocated': money(credits - used), 'bank_balance': None})
        numeric = ['inflow', 'outflow', 'records', 'orders', 'open_orders', 'cancelled_orders', 'order_value', 'invoice_total',
                   'allocated', 'outstanding', 'overpayment', 'overdue', 'unpaid_invoices', 'pending_review', 'approved_unposted', 'payables', 'overdue_payables']
        totals = {key: sum(row[key] for row in rows.values()) for key in numeric}
        monetary = {'inflow', 'outflow', 'order_value', 'invoice_total', 'allocated', 'outstanding', 'overpayment', 'overdue', 'payables', 'overdue_payables'}
        def serialize(row):
            return {**row, **{key: money(row[key]) for key in monetary}, 'net': money(row['inflow'] - row['outflow'])}
        return {'period': {'start': start.isoformat(), 'end': end.isoformat(), 'timezone': 'Africa/Lagos'}, 'currency': 'NGN',
                'totals': serialize(totals), 'locations': [serialize(row) for row in rows.values()], 'accounts': accounts,
                'coverage': {'sources': sources, 'last_recorded_at': latest, 'generated_at': time.time(), 'bank_feed_connected': False,
                             'receivables_scope': 'Current allocations across all issued invoices, not a historical balance at the period end',
                             'account_scope': 'Recorded credits in the selected dates; their allocations are current. These are not bank balances.',
                             'flow_scope': 'Posted ledger movements, not revenue/profit. Internal transfers are not automatically classified.'}}
