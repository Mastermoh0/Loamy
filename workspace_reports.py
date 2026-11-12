"""Evidence-based owner insights and bounded, scoped history/evidence exports."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import csv
import hashlib
from io import BytesIO, StringIO
import json
import secrets
import threading
import time
import unicodedata
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from workspace_finances import VoidInput, money
from workspace_payments import payment_totals

EXPORT_LOCK = threading.BoundedSemaphore(1)


def lagos_today():
    return datetime.now(timezone(timedelta(hours=1))).date()


class InsightInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    location_id: str | None = None
    days: int = Field(default=90, strict=True, ge=30, le=366)
    available_cash: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    confirm_complete_history: bool = False


class CommitmentInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    location_id: str = Field(min_length=1, max_length=64)
    vendor: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=3, max_length=240)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    cadence: str = Field(pattern=r'^(weekly|monthly|quarterly|yearly)$')
    next_due: date
    idempotency_key: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')


class ExportInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    location_id: str | None = None
    start: date
    end: date
    include_evidence: bool = True


def safe_csv(headers, rows):
    def cell(value):
        text = '' if value is None else str(value)
        # Quoting alone does not stop spreadsheet formula execution.
        if text.startswith(('\t', '\r', '\n')):
            return "'" + text
        if unicodedata.normalize('NFKC', text).lstrip().startswith(('=', '+', '-', '@')):
            return '\t' + text
        return text
    out = StringIO(newline=''); writer = csv.writer(out, quoting=csv.QUOTE_ALL)
    writer.writerow(headers)
    writer.writerows([[cell(row.get(key)) for key in headers] for row in rows])
    return out.getvalue().encode('utf-8-sig')


def install_reports(app, db, verified_user, membership, audit):
    with db() as conn:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS recurring_commitments (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            actor_id TEXT NOT NULL REFERENCES users(id),vendor TEXT NOT NULL,description TEXT NOT NULL,amount_minor INTEGER NOT NULL CHECK(amount_minor>0),
            cadence TEXT NOT NULL,next_due TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('active','cancelled')),
            created_at REAL NOT NULL,cancelled_at REAL,cancel_reason TEXT,idempotency_key TEXT NOT NULL,request_hash TEXT NOT NULL,
            UNIQUE(business_id,idempotency_key)
          );
        ''')
    base = '/enterprise-api/businesses/{business_id}'

    def scope(conn, bid, actor, lid=None, owner=False):
        member = membership(conn, bid, actor, owner=owner)
        if member['role'] not in {'owner', 'manager', 'finance'}:
            raise HTTPException(403, 'Financial reports are available to the owner, manager and finance team')
        if member['role'] != 'owner':
            if lid and lid != member['location_id']:
                raise HTTPException(404, 'Location not found')
            lid = member['location_id']
        if lid and not conn.execute('SELECT id FROM locations WHERE id=? AND business_id=?', (lid, bid)).fetchone():
            raise HTTPException(404, 'Location not found')
        return lid

    def commitments(conn, bid, lid):
        return [{**{k: r[k] for k in ['id', 'location_id', 'vendor', 'description', 'cadence', 'next_due', 'status', 'cancel_reason']}, 'amount': money(r['amount_minor'])} for r in conn.execute('SELECT * FROM recurring_commitments WHERE business_id=? AND (? IS NULL OR location_id=?) ORDER BY next_due,id', (bid, lid, lid))]

    @app.post(base + '/financial-insights')
    def insights(business_id: str, data: InsightInput, actor=Depends(verified_user)):
        today = lagos_today(); end = today - timedelta(days=1); start = today - timedelta(days=data.days)
        with db() as conn:
            lid = scope(conn, business_id, actor, data.location_id, owner=True)
            records = conn.execute("SELECT id,location_id,direction,amount_minor,occurred_on,description,category FROM financial_records WHERE business_id=? AND (? IS NULL OR location_id=?) AND status='posted' AND occurred_on>=? AND occurred_on<=? ORDER BY occurred_on,id LIMIT 10001", (business_id, lid, lid, start.isoformat(), end.isoformat())).fetchall()
            if len(records) > 10000:
                raise HTTPException(413, 'Use a shorter insight period or one location; this view supports 10,000 records')
            inflow = sum(r['amount_minor'] for r in records if r['direction'] == 'income')
            outflow = sum(r['amount_minor'] for r in records if r['direction'] == 'expense'); burn = max(0, outflow - inflow)
            runway = int(data.available_cash * 100) * data.days // burn if burn and data.available_cash is not None and data.confirm_complete_history else None
            groups = defaultdict(list)
            for r in records:
                if r['direction'] == 'expense':
                    groups[(r['location_id'], r['description'].strip().casefold(), r['category'].casefold(), r['amount_minor'])].append(r)
            recurring = []
            for rows in groups.values():
                dates = sorted({date.fromisoformat(r['occurred_on']) for r in rows})
                gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
                cadence = 'weekly' if gaps and all(5 <= g <= 9 for g in gaps) else 'monthly' if gaps and all(25 <= g <= 35 for g in gaps) else None
                if len(dates) >= 3 and cadence:
                    recurring.append({'description': rows[0]['description'], 'location_id': rows[0]['location_id'], 'amount': money(rows[0]['amount_minor']), 'cadence_candidate': cadence, 'occurrences': len(rows), 'record_ids': [r['id'] for r in rows], 'dates': [d.isoformat() for d in dates]})
            debtors = []
            for invoice in conn.execute("SELECT i.id,i.number,i.status,i.due_on,o.location_id,o.total_minor,o.customer_name,o.customer_contact,coalesce((SELECT sum(a.amount_minor) FROM payment_allocations a JOIN financial_records r ON r.id=a.record_id WHERE a.invoice_id=i.id AND a.reversed_at IS NULL AND r.status='posted'),0) paid FROM invoices i JOIN orders o ON o.id=i.order_id WHERE o.business_id=? AND (? IS NULL OR o.location_id=?) AND i.status='issued' ORDER BY i.issued_at", (business_id, lid, lid)):
                payments = payment_totals(invoice['total_minor'], invoice['paid'], invoice['status'])
                if payments['outstanding'] != '0.00':
                    debtors.append({'invoice_id': invoice['id'], 'number': invoice['number'], 'location_id': invoice['location_id'], 'customer': invoice['customer_name'], 'contact': invoice['customer_contact'], 'outstanding': payments['outstanding'], 'due_on': invoice['due_on'], 'overdue': bool(invoice['due_on'] and invoice['due_on'] < today.isoformat())})
            plans = commitments(conn, business_id, lid)
            factors = {'weekly': Decimal(52) / 12, 'monthly': Decimal(1), 'quarterly': Decimal(1) / 3, 'yearly': Decimal(1) / 12}
            monthly = sum((Decimal(p['amount']) * factors[p['cadence']] for p in plans if p['status'] == 'active'), Decimal(0)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            return {'period': {'start': start.isoformat(), 'end': end.isoformat(), 'days': data.days, 'timezone': 'Africa/Lagos'},
                'inflow': money(inflow), 'outflow': money(outflow), 'net_burn': money(burn), 'daily_net_burn': money(int((Decimal(burn) / data.days).quantize(Decimal(1), rounding=ROUND_HALF_UP))),
                'record_count': len(records), 'first_record_date': records[0]['occurred_on'] if records else None,
                'entered_cash': format(data.available_cash, '.2f') if data.available_cash is not None else None, 'runway_days': runway,
                'runway_reason': 'Estimate from entered cash and recorded positive net burn' if runway is not None else 'Enter available cash and confirm complete history; positive net burn is required',
                'debtors': debtors, 'recurring_candidates': recurring, 'commitments': plans, 'declared_monthly_commitments': format(monthly, '.2f'),
                'limitations': ['Runway uses completed calendar days and recorded movements, not bank balances or a guarantee of future cash.', 'Current debtors include all issued invoices regardless of the observation period.', 'Recurring candidates require matching location, description, category and amount on at least three regularly spaced dates; they are unconfirmed.', 'Declared subscriptions are estimates of commitments; they do not create expenses or get added again to historical burn.', 'Unrecorded transactions and unclassified internal transfers can change these results.']}

    app.state.recorded_insights = insights

    @app.post(base + '/recurring-commitments', status_code=201)
    def add_commitment(business_id: str, data: CommitmentInput, actor=Depends(verified_user)):
        signature = hashlib.sha256(json.dumps(data.model_dump(mode='json', exclude={'idempotency_key'}), sort_keys=True).encode()).hexdigest()
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE'); scope(conn, business_id, actor, data.location_id, owner=True)
            previous = conn.execute('SELECT id,request_hash FROM recurring_commitments WHERE business_id=? AND idempotency_key=?', (business_id, data.idempotency_key)).fetchone()
            if previous:
                if previous['request_hash'] != signature:
                    raise HTTPException(409, 'This subscription reference identifies another commitment')
                return {'id': previous['id'], 'duplicate': True}
            if conn.execute("SELECT id FROM recurring_commitments WHERE business_id=? AND location_id=? AND lower(vendor)=lower(?) AND lower(description)=lower(?) AND status='active'", (business_id, data.location_id, data.vendor, data.description)).fetchone():
                raise HTTPException(409, 'An active commitment already uses this vendor and description; cancel it before replacing it')
            rid = secrets.token_hex(16)
            conn.execute('INSERT INTO recurring_commitments VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,?,?)', (rid, business_id, data.location_id, actor['id'], data.vendor, data.description, int(data.amount * 100), data.cadence, data.next_due.isoformat(), 'active', time.time(), data.idempotency_key, signature))
            audit(conn, business_id, actor['id'], f'Recorded recurring commitment {rid}; no expense posted')
        return {'id': rid, 'duplicate': False}

    @app.post(base + '/recurring-commitments/{commitment_id}/cancel')
    def cancel_commitment(business_id: str, commitment_id: str, data: VoidInput, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, actor, owner=True)
            row = conn.execute('SELECT id FROM recurring_commitments WHERE id=? AND business_id=?', (commitment_id, business_id)).fetchone()
            if not row:
                raise HTTPException(404, 'Recurring commitment not found')
            conn.execute("UPDATE recurring_commitments SET status='cancelled',cancelled_at=?,cancel_reason=? WHERE id=? AND status='active'", (time.time(), data.reason, commitment_id))
            audit(conn, business_id, actor['id'], f'Cancelled recurring commitment {commitment_id}: {data.reason}')
        return {'success': True}

    @app.post(base + '/financial-history/export')
    def export_history(business_id: str, data: ExportInput, actor=Depends(verified_user)):
        if data.start > data.end or data.end > lagos_today() or (data.end - data.start).days > 365:
            raise HTTPException(422, 'Choose an ordered date range of up to 366 days, ending today or earlier')
        if not EXPORT_LOCK.acquire(blocking=False):
            raise HTTPException(429, 'A report is being built. Try again shortly.')
        try:
            with db() as conn:
                lid = scope(conn, business_id, actor, data.location_id)
                params = (business_id, lid, lid, data.start.isoformat(), data.end.isoformat())
                records = [dict(r) for r in conn.execute('SELECT r.*,l.name location FROM financial_records r JOIN locations l ON l.id=r.location_id WHERE r.business_id=? AND (? IS NULL OR r.location_id=?) AND r.occurred_on>=? AND r.occurred_on<=? ORDER BY r.occurred_on,r.id LIMIT 5001', params)]
                if len(records) > 5000:
                    raise HTTPException(413, 'Export supports 5,000 ledger records. Select fewer dates or one location.')
                invoice_rows = conn.execute("SELECT i.id,i.order_id,i.number,i.status,i.due_on,i.issued_at,i.snapshot,o.total_minor,coalesce((SELECT sum(a.amount_minor) FROM payment_allocations a JOIN financial_records r ON r.id=a.record_id WHERE a.invoice_id=i.id AND a.reversed_at IS NULL AND r.status='posted'),0) paid,length(i.pdf) bytes FROM invoices i JOIN orders o ON o.id=i.order_id WHERE o.business_id=? AND (? IS NULL OR o.location_id=?) ORDER BY i.id LIMIT 5001", (business_id, lid, lid)).fetchall()
                if len(invoice_rows) > 5000:
                    raise HTTPException(413, 'Select one location; the current invoice balance report supports 5,000 invoices')
                files = []; invoices = []
                related_invoices = {r['invoice_id'] for r in conn.execute('SELECT DISTINCT a.invoice_id FROM payment_allocations a JOIN financial_records r ON r.id=a.record_id WHERE r.business_id=? AND (? IS NULL OR r.location_id=?) AND r.occurred_on>=? AND r.occurred_on<=?', params)}
                for r in invoice_rows:
                    payments = payment_totals(r['total_minor'], r['paid'], r['status'])
                    if r['status'] == 'cancelled':
                        payments['outstanding'] = '0.00'
                    snapshot = json.loads(r['snapshot'])
                    invoices.append({'id': r['id'], 'number': r['number'], 'customer': snapshot['customer_name'], 'contact': snapshot['customer_contact'], 'due_on': r['due_on'], **(snapshot.get('pricing') or {'subtotal': payments['total'], 'discount': '0.00', 'tax': '0.00', 'tax_label': 'Tax', 'tax_rate': '0.00', 'discount_type': 'none', 'discount_value': '0.00', 'discount_reason': ''}), **{k: payments[k] for k in ['status', 'total', 'allocated', 'outstanding', 'overpayment']}})
                    issued = datetime.fromtimestamp(r['issued_at'], timezone(timedelta(hours=1))).date()
                    if data.include_evidence and (data.start <= issued <= data.end or r['id'] in related_invoices):
                        files.append(('invoices/' + r['id'] + '.pdf', 'invoices', 'pdf', 'id', r['id'], r['bytes'], None))
                allocations = [dict(r) for r in conn.execute('SELECT a.id,a.record_id,a.invoice_id,a.amount_minor,a.created_at,a.reversed_at,a.reversal_reason,a.note FROM payment_allocations a JOIN financial_records r ON r.id=a.record_id WHERE r.business_id=? AND (? IS NULL OR r.location_id=?) AND r.occurred_on>=? AND r.occurred_on<=? LIMIT 20001', params)]
                supplier_allocations = [dict(r) for r in conn.execute('SELECT a.id,a.bill_id,a.record_id,a.amount_minor,a.reason,a.reversed_at,a.reverse_reason FROM supplier_payments a JOIN financial_records r ON r.id=a.record_id WHERE r.business_id=? AND (? IS NULL OR r.location_id=?) AND r.occurred_on>=? AND r.occurred_on<=? LIMIT 20001', params)]
                expense_versions = conn.execute('SELECT e.id,e.record_id,e.submitter_id,v.revision,v.vendor,v.purpose,v.category,v.amount_minor,v.occurred_on,v.extension,v.receipt_hash,length(v.receipt) bytes FROM expense_submissions e JOIN expense_versions v ON v.expense_id=e.id JOIN financial_records r ON r.id=e.record_id WHERE r.business_id=? AND (? IS NULL OR r.location_id=?) AND r.occurred_on>=? AND r.occurred_on<=? ORDER BY e.id,v.revision LIMIT 20001', params).fetchall()
                expenses = []
                for r in expense_versions:
                    expenses.append({k: r[k] for k in ['id', 'record_id', 'submitter_id', 'revision', 'vendor', 'purpose', 'category', 'amount_minor', 'occurred_on', 'receipt_hash']})
                    if data.include_evidence:
                        files.append((f'receipts/{r["id"]}-v{r["revision"]}.{r["extension"]}', 'expense_versions', 'receipt', 'expense_id', r['id'], r['bytes'], r['revision']))
                bills = []
                for r in conn.execute('SELECT b.id,b.vendor,b.reference,b.description,b.amount_minor,b.issued_on,b.due_on,b.status,b.void_reason,b.extension,b.receipt_hash,length(b.receipt) bytes FROM supplier_bills b WHERE b.business_id=? AND (? IS NULL OR b.location_id=?) AND ((b.issued_on>=? AND b.issued_on<=?) OR EXISTS (SELECT 1 FROM supplier_payments p JOIN financial_records r ON r.id=p.record_id WHERE p.bill_id=b.id AND r.occurred_on>=? AND r.occurred_on<=?)) ORDER BY b.id LIMIT 20001', (*params, data.start.isoformat(), data.end.isoformat())):
                    bills.append({k: r[k] for k in ['id', 'vendor', 'reference', 'description', 'amount_minor', 'issued_on', 'due_on', 'status', 'void_reason', 'receipt_hash']})
                    if data.include_evidence:
                        files.append((f'suppliers/{r["id"]}.{r["extension"]}', 'supplier_bills', 'receipt', 'id', r['id'], r['bytes'], None))
                if len(files) > 1000 or sum(int(f[5]) for f in files) > 25 * 1024 * 1024 or sum(map(len, [allocations, supplier_allocations, expenses, bills])) > 20000:
                    raise HTTPException(413, 'Report exceeds the evidence/data limit. Reduce the dates or export without original files.')
                if any('..' in f[0].split('/') or '\\' in f[0] for f in files):
                    raise HTTPException(409, 'An evidence identifier cannot be exported safely; ask the operator to review it')
                tables = {'ledger.csv': (['id', 'location_id', 'location', 'direction', 'amount', 'currency', 'occurred_on', 'description', 'category', 'source', 'status', 'void_reason', 'actor_id'], records),
                          'current-invoice-balances.csv': (['id', 'number', 'customer', 'contact', 'due_on', 'subtotal', 'discount_type', 'discount_value', 'discount_reason', 'discount', 'tax_label', 'tax_rate', 'tax', 'status', 'total', 'allocated', 'outstanding', 'overpayment'], invoices),
                          'payment-allocations.csv': (['id', 'record_id', 'invoice_id', 'amount', 'created_at', 'reversed_at', 'reversal_reason', 'note'], allocations),
                          'supplier-payment-allocations.csv': (['id', 'bill_id', 'record_id', 'amount', 'reason', 'reversed_at', 'reverse_reason'], supplier_allocations),
                          'expense-evidence.csv': (['id', 'record_id', 'submitter_id', 'revision', 'vendor', 'purpose', 'category', 'amount', 'occurred_on', 'receipt_hash'], expenses),
                          'supplier-bills.csv': (['id', 'vendor', 'reference', 'description', 'amount', 'issued_on', 'due_on', 'status', 'void_reason', 'receipt_hash'], bills)}
                out = BytesIO(); manifest = {'business_id': business_id, 'location_id': lid, 'period': {'start': data.start.isoformat(), 'end': data.end.isoformat(), 'timezone': 'Africa/Lagos'}, 'generated_at': time.time(), 'currency': 'NGN', 'ledger_count': len(records), 'include_evidence': data.include_evidence,
                    'notes': ['Cash movement uses ledger occurred_on; voids remain visible.', 'Invoice balances are CURRENT across all scoped invoices, not a historical balance at period end.', 'Supporting originals include invoices issued/allocated in the period, supplier invoices issued or allocated in the period, and all receipt versions linked to period ledger records. Original files retain their issued form; consult CSV status before using a cancelled/voided document. Evidence versions are not additional cash entries.', 'Unposted staff receipts, unrelated private messages, bank emails, credentials and identity/session tables are excluded.', 'CSV is quoted and spreadsheet formula markers are prefixed with a tab; leading control characters are escaped. Preserve these guards when re-importing. No universal CSV defense covers every spreadsheet re-save behavior.'], 'evidence': []}
                income = sum(r['amount_minor'] for r in records if r['status'] == 'posted' and r['direction'] == 'income'); expense = sum(r['amount_minor'] for r in records if r['status'] == 'posted' and r['direction'] == 'expense')
                manifest['posted_totals'] = {'income': money(income), 'expenses': money(expense), 'net': money(income - expense)}
                with ZipFile(out, 'w', ZIP_DEFLATED) as archive:
                    summary = [{'metric': 'Period start', 'value': data.start.isoformat()}, {'metric': 'Period end', 'value': data.end.isoformat()}, {'metric': 'Timezone', 'value': 'Africa/Lagos'}, {'metric': 'Posted income (NGN)', 'value': money(income)}, {'metric': 'Posted expenses (NGN)', 'value': money(expense)}, {'metric': 'Posted net movement (NGN)', 'value': money(income - expense)}, {'metric': 'Ledger records including voids', 'value': len(records)}, {'metric': 'Invoice balance scope', 'value': 'Current; not a historical period-end balance'}]
                    archive.writestr('summary.csv', safe_csv(['metric', 'value'], summary))
                    archive.writestr('README.txt', 'Loamy financial history report\n\nOpen summary.csv for totals, ledger.csv for period movements, and current-invoice-balances.csv for current balances.\n\n' + '\n'.join(manifest['notes']))
                    for filename, (headers, rows) in tables.items():
                        for row in rows:
                            if 'amount_minor' in row:
                                row['amount'] = money(row['amount_minor'])
                        archive.writestr(filename, safe_csv(headers, rows))
                    for path, table, column, key, identifier, size, revision in files:
                        query = f'SELECT {column} FROM {table} WHERE {key}=?' + (' AND revision=?' if revision is not None else '')
                        values = (identifier, revision) if revision is not None else (identifier,)
                        content = conn.execute(query, values).fetchone()[0]
                        archive.writestr(path, content); manifest['evidence'].append({'path': path, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
                    archive.writestr('manifest.json', json.dumps(manifest, indent=2))
                audit(conn, business_id, actor['id'], f'Exported financial history {data.start} to {data.end}; {len(records)} ledger records and {len(files)} original files')
            return Response(content=out.getvalue(), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="loamy-financial-history.zip"'})
        finally:
            EXPORT_LOCK.release()
