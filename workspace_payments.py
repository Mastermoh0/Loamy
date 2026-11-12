"""Reviewed invoice allocations over the existing ledger; recording is not bank verification."""
from datetime import date
from decimal import Decimal
import re
import secrets
import time

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from workspace_finances import FinancialInput, VoidInput, money


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class AccountInput(Input):
    name: str = Field(min_length=2, max_length=100)
    account_reference: str = Field(min_length=2, max_length=100)


class CreditInput(Input):
    account_id: str | None = None
    source_id: str = Field(min_length=3, max_length=200)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    occurred_on: date
    payer: str = Field(min_length=2, max_length=120)
    narration: str = Field(min_length=2, max_length=1000)

    @field_validator('occurred_on')
    @classmethod
    def posted_date(cls, value):
        return FinancialInput.posted_date(value)


class AllocationInput(Input):
    record_id: str = Field(min_length=1, max_length=64)
    invoice_id: str = Field(min_length=1, max_length=64)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    note: str = Field(min_length=3, max_length=240)
    idempotency_key: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')


class InvoiceAccountInput(Input):
    invoice_id: str
    account_id: str


def payment_totals(total, paid, invoice_status):
    total, paid = int(total), int(paid)
    status = 'cancelled' if invoice_status == 'cancelled' else 'overpaid' if paid > total else 'paid' if paid == total else 'part_paid' if paid else 'unpaid'
    return {'status': status, 'total': money(total), 'allocated': money(paid), 'outstanding': money(max(total - paid, 0)), 'overpayment': money(max(paid - total, 0))}


def payment_summary(conn, invoice):
    total = conn.execute('SELECT total_minor FROM orders WHERE id=?', (invoice['order_id'],)).fetchone()[0]
    paid = conn.execute("SELECT coalesce(sum(a.amount_minor),0) FROM payment_allocations a JOIN financial_records r ON r.id=a.record_id WHERE a.invoice_id=? AND a.reversed_at IS NULL AND r.status='posted'", (invoice['id'],)).fetchone()[0]
    rows = conn.execute('SELECT a.id,a.amount_minor,a.created_at,a.reversed_at,a.reversal_reason,a.note,u.name actor FROM payment_allocations a JOIN users u ON u.id=a.actor_id WHERE a.invoice_id=? ORDER BY a.created_at DESC', (invoice['id'],)).fetchall()
    history = [{**dict(row), 'amount': money(row['amount_minor'])} for row in rows]
    for row in history:
        row.pop('amount_minor')
    return {**payment_totals(total, paid, invoice['status']), 'allocations': history}


def guard_balance_notice(conn, invoice_id):
    if conn.execute("SELECT id FROM invoice_deliveries WHERE invoice_id=? AND status='sending' AND updated_at>?", (invoice_id,time.time()-120)).fetchone():
        raise HTTPException(409,'An invoice message is being sent. Wait for its result before changing allocations.')
    if conn.execute("SELECT id FROM customer_notices WHERE invoice_id=? AND status='sending' AND updated_at>?", (invoice_id, time.time() - 120)).fetchone():
        raise HTTPException(409, 'A customer balance message is being sent. Wait for its result before changing allocations.')


def install_payments(app, db, verified_user, membership, audit):
    with db() as conn:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS payment_accounts (
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id), location_id TEXT NOT NULL REFERENCES locations(id),
            name TEXT NOT NULL, account_reference TEXT NOT NULL, UNIQUE(business_id,location_id,account_reference)
          );
          CREATE TABLE IF NOT EXISTS payment_evidence (
            record_id TEXT PRIMARY KEY REFERENCES financial_records(id), business_id TEXT NOT NULL REFERENCES businesses(id),
            account_id TEXT REFERENCES payment_accounts(id), account_key TEXT NOT NULL, source_id TEXT NOT NULL,
            payer TEXT NOT NULL,narration TEXT NOT NULL, UNIQUE(business_id,account_key,source_id)
          );
          CREATE TABLE IF NOT EXISTS invoice_accounts (
            invoice_id TEXT PRIMARY KEY REFERENCES invoices(id), account_id TEXT NOT NULL REFERENCES payment_accounts(id)
          );
          CREATE TABLE IF NOT EXISTS payment_allocations (
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id), location_id TEXT NOT NULL REFERENCES locations(id),
            record_id TEXT NOT NULL REFERENCES financial_records(id), invoice_id TEXT NOT NULL REFERENCES invoices(id),
            amount_minor INTEGER NOT NULL CHECK(amount_minor>0), actor_id TEXT NOT NULL REFERENCES users(id), note TEXT NOT NULL,
            created_at REAL NOT NULL, idempotency_key TEXT NOT NULL, reversed_at REAL, reversed_by TEXT REFERENCES users(id), reversal_reason TEXT,
            UNIQUE(business_id,idempotency_key)
          );
        ''')

    base = '/enterprise-api/businesses/{business_id}/locations/{location_id}/payments'

    def scope(conn, bid, lid, actor):
        member = membership(conn, bid, actor)
        if member['role'] not in {'owner', 'manager', 'finance'}:
            raise HTTPException(403, 'Only the owner, manager or finance team can review payments')
        if member['role'] != 'owner' and member['location_id'] != lid:
            raise HTTPException(404, 'Location not found')
        if not conn.execute('SELECT id FROM locations WHERE id=? AND business_id=?', (lid, bid)).fetchone():
            raise HTTPException(404, 'Location not found')

    def account(conn, bid, lid, aid):
        row = conn.execute('SELECT * FROM payment_accounts WHERE id=? AND business_id=? AND location_id=?', (aid, bid, lid)).fetchone()
        if not row:
            raise HTTPException(404, 'Receiving account not found')
        return row

    def invoice_row(conn, bid, lid, iid):
        row = conn.execute('SELECT i.* FROM invoices i JOIN orders o ON o.id=i.order_id WHERE i.id=? AND o.business_id=? AND o.location_id=?', (iid, bid, lid)).fetchone()
        if not row:
            raise HTTPException(404, 'Invoice not found')
        return row

    @app.get(base)
    def review(business_id: str, location_id: str, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, location_id, actor)
            accounts = [dict(row) for row in conn.execute('SELECT * FROM payment_accounts WHERE business_id=? AND location_id=? ORDER BY name', (business_id, location_id))]
            invoices = []
            for row in conn.execute('SELECT i.*,o.reference,o.customer_name,ia.account_id FROM invoices i JOIN orders o ON o.id=i.order_id LEFT JOIN invoice_accounts ia ON ia.invoice_id=i.id WHERE o.business_id=? AND o.location_id=? ORDER BY i.issued_at DESC', (business_id, location_id)):
                invoices.append({'id': row['id'], 'number': row['number'], 'order_id': row['order_id'], 'reference': row['reference'], 'customer': row['customer_name'], 'account_id': row['account_id'], **payment_summary(conn, row)})
            records = []
            for row in conn.execute("SELECT r.*,e.account_id,e.source_id,e.payer,e.narration FROM financial_records r LEFT JOIN payment_evidence e ON e.record_id=r.id WHERE r.business_id=? AND r.location_id=? AND r.direction='income' AND r.status='posted' ORDER BY r.created_at DESC LIMIT 100", (business_id, location_id)):
                used = conn.execute('SELECT coalesce(sum(amount_minor),0) FROM payment_allocations WHERE record_id=? AND reversed_at IS NULL', (row['id'],)).fetchone()[0]
                available = row['amount_minor'] - used
                candidates = []
                for invoice in invoices:
                    if invoice['status'] not in {'unpaid', 'part_paid'} or available <= 0:
                        continue
                    if row['account_id'] and invoice['account_id'] != row['account_id']:
                        continue
                    narration = (row['narration'] or '')
                    reference = any(re.search(r'(?<![A-Z0-9])' + re.escape(value.upper()) + r'(?![A-Z0-9])', narration.upper()) for value in [invoice['reference'], invoice['number']])
                    name = row['payer'] and row['payer'].casefold() == invoice['customer'].casefold()
                    if reference or (name and Decimal(invoice['outstanding']) * 100 == available):
                        candidates.append({'invoice_id': invoice['id'], 'reason': 'Reference and receiving account match — review evidence' if reference and row['account_id'] else 'Supporting name/amount or reference only — manual review required'})
                records.append({'id': row['id'], 'description': row['description'], 'amount': money(row['amount_minor']), 'available': money(available), 'occurred_on': row['occurred_on'], 'source': row['source'],
                                'account_id': row['account_id'], 'source_id': row['source_id'], 'payer': row['payer'], 'narration': row['narration'], 'candidates': candidates})
        return {'accounts': accounts, 'invoices': invoices, 'credits': records, 'credit_limit': 100}

    @app.post(base + '/accounts', status_code=201)
    def create_account(business_id: str, location_id: str, data: AccountInput, actor=Depends(verified_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            scope(conn, business_id, location_id, actor)
            existing = conn.execute('SELECT id,name FROM payment_accounts WHERE business_id=? AND location_id=? AND account_reference=?', (business_id, location_id, data.account_reference)).fetchone()
            if existing:
                if existing['name'] != data.name:
                    raise HTTPException(409, 'That account reference already exists with a different name')
                return {'id': existing['id']}
            aid = secrets.token_hex(16)
            conn.execute('INSERT INTO payment_accounts VALUES (?,?,?,?,?)', (aid, business_id, location_id, data.name, data.account_reference))
            audit(conn, business_id, actor['id'], f'Added receiving account: {data.name}')
        return {'id': aid}

    @app.put(base + '/invoice-account')
    def bind_account(business_id: str, location_id: str, data: InvoiceAccountInput, actor=Depends(verified_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            scope(conn, business_id, location_id, actor)
            invoice = invoice_row(conn, business_id, location_id, data.invoice_id)
            account(conn, business_id, location_id, data.account_id)
            if invoice['status'] != 'issued':
                raise HTTPException(409, 'Cancelled invoices cannot change receiving accounts')
            if conn.execute('SELECT id FROM payment_allocations WHERE invoice_id=? AND reversed_at IS NULL', (data.invoice_id,)).fetchone():
                raise HTTPException(409, 'Reverse allocations before changing the receiving account')
            conn.execute('INSERT INTO invoice_accounts VALUES (?,?) ON CONFLICT(invoice_id) DO UPDATE SET account_id=excluded.account_id', (data.invoice_id, data.account_id))
            audit(conn, business_id, actor['id'], f'Set receiving account for invoice {invoice["number"]}')
        return {'success': True}

    @app.post(base + '/credits', status_code=201)
    def create_credit(business_id: str, location_id: str, data: CreditInput, actor=Depends(verified_user)):
        minor = int(data.amount * 100)
        key = data.account_id or f'cash-{location_id}'
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            scope(conn, business_id, location_id, actor)
            if data.account_id:
                account(conn, business_id, location_id, data.account_id)
            previous = conn.execute('SELECT e.*,r.amount_minor,r.occurred_on,r.location_id FROM payment_evidence e JOIN financial_records r ON r.id=e.record_id WHERE e.business_id=? AND e.account_key=? AND e.source_id=?', (business_id, key, data.source_id)).fetchone()
            if previous:
                if (previous['amount_minor'], previous['occurred_on'], previous['location_id'], previous['payer'], previous['narration']) != (minor, data.occurred_on.isoformat(), location_id, data.payer, data.narration):
                    raise HTTPException(409, 'That source reference already identifies a different credit')
                return {'id': previous['record_id'], 'duplicate': True}
            rid = secrets.token_hex(16)
            conn.execute('INSERT INTO financial_records (id,business_id,location_id,actor_id,direction,amount_minor,currency,occurred_on,description,category,source,created_at,idempotency_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (rid, business_id, location_id, actor['id'], 'income', minor, 'NGN', data.occurred_on.isoformat(), data.narration[:240], 'Customer payment', 'bank_credit_preview' if data.account_id else 'payment_cash', time.time(), 'payment-' + rid))
            conn.execute('INSERT INTO payment_evidence VALUES (?,?,?,?,?,?,?)', (rid, business_id, data.account_id, key, data.source_id, data.payer, data.narration))
            audit(conn, business_id, actor['id'], f'Recorded payment evidence {data.source_id}: NGN {money(minor)}')
        return {'id': rid, 'duplicate': False}

    @app.post(base + '/allocations', status_code=201)
    def allocate(business_id: str, location_id: str, data: AllocationInput, actor=Depends(verified_user)):
        minor = int(data.amount * 100)
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            scope(conn, business_id, location_id, actor)
            previous = conn.execute('SELECT * FROM payment_allocations WHERE business_id=? AND idempotency_key=?', (business_id, data.idempotency_key)).fetchone()
            if previous:
                if (previous['record_id'], previous['invoice_id'], previous['amount_minor'], previous['actor_id'], previous['note'], previous['location_id']) != (data.record_id, data.invoice_id, minor, actor['id'], data.note, location_id):
                    raise HTTPException(409, 'This allocation reference was already used for another request')
                return {'id': previous['id'], 'duplicate': True}
            invoice = invoice_row(conn, business_id, location_id, data.invoice_id)
            if invoice['status'] != 'issued':
                raise HTTPException(409, 'Cancelled invoices cannot receive allocations')
            guard_balance_notice(conn, invoice['id'])
            record = conn.execute("SELECT r.*,e.account_id FROM financial_records r LEFT JOIN payment_evidence e ON e.record_id=r.id WHERE r.id=? AND r.business_id=? AND r.location_id=? AND r.direction='income' AND r.currency='NGN' AND r.status='posted'", (data.record_id, business_id, location_id)).fetchone()
            if not record:
                raise HTTPException(404, 'Posted income record not found')
            if record['account_id']:
                bound = conn.execute('SELECT account_id FROM invoice_accounts WHERE invoice_id=?', (data.invoice_id,)).fetchone()
                if not bound or bound[0] != record['account_id']:
                    raise HTTPException(409, 'Credit receiving account does not match the invoice receiving account')
            used = conn.execute('SELECT coalesce(sum(amount_minor),0) FROM payment_allocations WHERE record_id=? AND reversed_at IS NULL', (data.record_id,)).fetchone()[0]
            if minor > record['amount_minor'] - used:
                raise HTTPException(409, 'Allocation exceeds the unallocated amount of this income record')
            aid = secrets.token_hex(16)
            conn.execute('INSERT INTO payment_allocations (id,business_id,location_id,record_id,invoice_id,amount_minor,actor_id,note,created_at,idempotency_key) VALUES (?,?,?,?,?,?,?,?,?,?)', (aid, business_id, location_id, data.record_id, data.invoice_id, minor, actor['id'], data.note, time.time(), data.idempotency_key))
            audit(conn, business_id, actor['id'], f'Allocated NGN {money(minor)} to {invoice["number"]}')
        return {'id': aid, 'duplicate': False}

    @app.post(base + '/allocations/{allocation_id}/reverse')
    def reverse(business_id: str, location_id: str, allocation_id: str, data: VoidInput, actor=Depends(verified_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            scope(conn, business_id, location_id, actor)
            row = conn.execute('SELECT * FROM payment_allocations WHERE id=? AND business_id=? AND location_id=?', (allocation_id, business_id, location_id)).fetchone()
            if not row:
                raise HTTPException(404, 'Allocation not found')
            if row['reversed_at'] is None:
                guard_balance_notice(conn, row['invoice_id'])
                conn.execute('UPDATE payment_allocations SET reversed_at=?,reversed_by=?,reversal_reason=? WHERE id=?', (time.time(), actor['id'], data.reason, allocation_id))
                audit(conn, business_id, actor['id'], f'Reversed allocation {allocation_id}: {data.reason}')
        return {'success': True}
