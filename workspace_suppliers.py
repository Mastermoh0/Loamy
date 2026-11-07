"""Supplier liabilities and allocations to existing paid debits, never a second ledger."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import secrets
import time

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from workspace_expenses import receipt_bytes
from workspace_finances import FinancialInput, VoidInput, money


class BillInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    vendor: str = Field(min_length=2, max_length=120)
    reference: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=3, max_length=240)
    category: str = Field(min_length=2, max_length=60)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    issued_on: date
    due_on: date
    receipt_base64: str = Field(min_length=8, max_length=2800000)
    idempotency_key: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    extraction_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')

    @field_validator('issued_on')
    @classmethod
    def past(cls, value):
        return FinancialInput.posted_date(value)

    @model_validator(mode='after')
    def ordered_dates(self):
        if self.due_on < self.issued_on:
            raise ValueError('Due date cannot precede the invoice date')
        return self


class BillPaymentInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    record_id: str = Field(min_length=1, max_length=64)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    reason: str = Field(min_length=3, max_length=240)
    idempotency_key: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')


def install_suppliers(app, db, verified_user, membership, audit):
    with db() as conn:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS supplier_bills (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            actor_id TEXT NOT NULL REFERENCES users(id),vendor TEXT NOT NULL,vendor_key TEXT NOT NULL,reference TEXT NOT NULL,reference_key TEXT NOT NULL,
            description TEXT NOT NULL,category TEXT NOT NULL,amount_minor INTEGER NOT NULL CHECK(amount_minor>0),issued_on TEXT NOT NULL,due_on TEXT NOT NULL,
            receipt BLOB NOT NULL,mime TEXT NOT NULL,extension TEXT NOT NULL,receipt_hash TEXT NOT NULL,extraction_id TEXT REFERENCES receipt_extractions(id),
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','voided')),void_reason TEXT,voided_at REAL,
            created_at REAL NOT NULL,idempotency_key TEXT NOT NULL,request_hash TEXT NOT NULL,
            UNIQUE(business_id,idempotency_key)
          );
          CREATE UNIQUE INDEX IF NOT EXISTS supplier_bill_active_reference ON supplier_bills(business_id,vendor_key,reference_key) WHERE status='open';
          CREATE UNIQUE INDEX IF NOT EXISTS supplier_bill_active_receipt ON supplier_bills(business_id,receipt_hash) WHERE status='open';
          CREATE INDEX IF NOT EXISTS supplier_bill_location ON supplier_bills(business_id,location_id,due_on);
          CREATE TABLE IF NOT EXISTS supplier_payments (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            bill_id TEXT NOT NULL REFERENCES supplier_bills(id),record_id TEXT NOT NULL REFERENCES financial_records(id),
            amount_minor INTEGER NOT NULL CHECK(amount_minor>0),actor_id TEXT NOT NULL REFERENCES users(id),reason TEXT NOT NULL,
            created_at REAL NOT NULL,idempotency_key TEXT NOT NULL,request_hash TEXT NOT NULL,reversed_at REAL,reversed_by TEXT REFERENCES users(id),reverse_reason TEXT,
            UNIQUE(business_id,idempotency_key)
          );
          CREATE INDEX IF NOT EXISTS supplier_payment_record ON supplier_payments(record_id,reversed_at);
        ''')
    base = '/enterprise-api/businesses/{business_id}/locations/{location_id}/supplier-bills'

    def scope(conn, bid, lid, actor):
        member = membership(conn, bid, actor)
        if member['role'] not in {'owner', 'manager', 'finance'}:
            raise HTTPException(403, 'Supplier bills are available to the owner, manager and finance team')
        if member['role'] != 'owner' and member['location_id'] != lid:
            raise HTTPException(404, 'Location not found')
        if not conn.execute('SELECT id FROM locations WHERE id=? AND business_id=?', (lid, bid)).fetchone():
            raise HTTPException(404, 'Location not found')

    def load(conn, bid, lid, bill_id, actor):
        scope(conn, bid, lid, actor)
        bill = conn.execute('SELECT * FROM supplier_bills WHERE id=? AND business_id=? AND location_id=?', (bill_id, bid, lid)).fetchone()
        if not bill:
            raise HTTPException(404, 'Supplier bill not found')
        return bill

    def public(conn, bill):
        payments = conn.execute('SELECT p.*,r.status ledger_status FROM supplier_payments p JOIN financial_records r ON r.id=p.record_id WHERE bill_id=? ORDER BY p.created_at', (bill['id'],)).fetchall()
        paid = sum(p['amount_minor'] for p in payments if p['reversed_at'] is None and p['ledger_status'] == 'posted')
        result = {k: bill[k] for k in ['id', 'vendor', 'reference', 'description', 'category', 'issued_on', 'due_on', 'status', 'void_reason', 'created_at']}
        outstanding = max(0, bill['amount_minor'] - paid) if bill['status'] == 'open' else 0
        result.update(amount=money(bill['amount_minor']), paid=money(paid), outstanding=money(outstanding),
            payment_status='voided' if bill['status'] == 'voided' else 'paid' if not outstanding else 'part_paid' if paid else 'unpaid',
            overdue=bool(outstanding and bill['due_on'] < datetime.now(timezone(timedelta(hours=1))).date().isoformat()),
            payments=[{'id': p['id'], 'record_id': p['record_id'], 'amount': money(p['amount_minor']), 'reason': p['reason'], 'reversed_at': p['reversed_at'], 'reverse_reason': p['reverse_reason']} for p in payments])
        extracted = conn.execute('SELECT result FROM receipt_extractions WHERE id=?', (bill['extraction_id'],)).fetchone() if bill['extraction_id'] else None
        result['suggestions'] = json.loads(extracted['result'])['suggested'] if extracted else None
        return result

    @app.get(base)
    def list_bills(business_id: str, location_id: str, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, location_id, actor)
            rows = conn.execute('SELECT * FROM supplier_bills WHERE business_id=? AND location_id=? ORDER BY created_at DESC LIMIT 100', (business_id, location_id)).fetchall()
            bills = [public(conn, row) for row in rows]
            # Aggregate all liabilities; list is bounded but totals must not silently truncate.
            totals = conn.execute("SELECT b.amount_minor,coalesce(p.paid,0) paid,b.due_on FROM supplier_bills b LEFT JOIN (SELECT bill_id,sum(amount_minor) paid FROM supplier_payments WHERE reversed_at IS NULL GROUP BY bill_id) p ON p.bill_id=b.id WHERE b.business_id=? AND b.location_id=? AND b.status='open'", (business_id, location_id)).fetchall()
            today = datetime.now(timezone(timedelta(hours=1))).date().isoformat()
            debits = conn.execute("SELECT r.id,r.description,r.occurred_on,r.amount_minor-coalesce(p.used,0) available FROM financial_records r LEFT JOIN (SELECT record_id,sum(amount_minor) used FROM supplier_payments WHERE reversed_at IS NULL GROUP BY record_id) p ON p.record_id=r.id WHERE r.business_id=? AND r.location_id=? AND r.direction='expense' AND r.status='posted' ORDER BY r.occurred_on DESC LIMIT 100", (business_id, location_id)).fetchall()
            return {'bills': bills, 'count': conn.execute('SELECT count(*) FROM supplier_bills WHERE business_id=? AND location_id=?', (business_id, location_id)).fetchone()[0],
                'outstanding': money(sum(max(0, r['amount_minor'] - int(r['paid'])) for r in totals)),
                'overdue': money(sum(max(0, r['amount_minor'] - int(r['paid'])) for r in totals if r['due_on'] < today)),
                'debits': [{'id': r['id'], 'description': r['description'], 'occurred_on': r['occurred_on'], 'available': money(int(r['available']))} for r in debits if r['available'] > 0]}

    @app.post(base, status_code=201)
    def import_bill(business_id: str, location_id: str, data: BillInput, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, location_id, actor)
        raw, mime, extension = receipt_bytes(data.receipt_base64)
        digest = hashlib.sha256(raw).hexdigest()
        signature = hashlib.sha256(json.dumps([location_id, data.model_dump(mode='json', exclude={'receipt_base64', 'idempotency_key'}), digest], sort_keys=True).encode()).hexdigest()
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE'); scope(conn, business_id, location_id, actor)
            previous = conn.execute('SELECT id,request_hash FROM supplier_bills WHERE business_id=? AND idempotency_key=?', (business_id, data.idempotency_key)).fetchone()
            if previous:
                if previous['request_hash'] != signature:
                    raise HTTPException(409, 'This import reference already identifies another bill')
                return {'id': previous['id'], 'duplicate': True}
            if conn.execute("SELECT id FROM supplier_bills WHERE business_id=? AND status='open' AND ((vendor_key=? AND reference_key=?) OR receipt_hash=?)", (business_id, data.vendor.casefold(), data.reference.casefold(), digest)).fetchone():
                raise HTTPException(409, 'This supplier reference or invoice file is already imported')
            if data.extraction_id:
                extraction = conn.execute("SELECT * FROM receipt_extractions WHERE id=? AND status='success'", (data.extraction_id,)).fetchone()
                if not extraction or (extraction['business_id'], extraction['location_id'], extraction['actor_id'], extraction['receipt_hash']) != (business_id, location_id, actor['id'], digest):
                    raise HTTPException(422, 'Suggestions must belong to you and this exact invoice at this location')
            bid = secrets.token_hex(16)
            conn.execute('INSERT INTO supplier_bills (id,business_id,location_id,actor_id,vendor,vendor_key,reference,reference_key,description,category,amount_minor,issued_on,due_on,receipt,mime,extension,receipt_hash,extraction_id,created_at,idempotency_key,request_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (bid, business_id, location_id, actor['id'], data.vendor, data.vendor.casefold(), data.reference, data.reference.casefold(), data.description, data.category, int(data.amount * 100), data.issued_on.isoformat(), data.due_on.isoformat(), raw, mime, extension, digest, data.extraction_id, time.time(), data.idempotency_key, signature))
            audit(conn, business_id, actor['id'], f'Imported supplier bill {bid}; no expense posted')
        return {'id': bid, 'duplicate': False}

    @app.get(base + '/{bill_id}/invoice')
    def original_invoice(business_id: str, location_id: str, bill_id: str, actor=Depends(verified_user)):
        with db() as conn:
            row = load(conn, business_id, location_id, bill_id, actor)
            return Response(content=row['receipt'], media_type='application/octet-stream', headers={'Content-Disposition': f'attachment; filename="supplier-invoice-{bill_id}.{row["extension"]}"', 'Content-Security-Policy': "default-src 'none'; sandbox"})

    @app.post(base + '/{bill_id}/payments', status_code=201)
    def allocate(business_id: str, location_id: str, bill_id: str, data: BillPaymentInput, actor=Depends(verified_user)):
        signature = hashlib.sha256(json.dumps([bill_id, data.record_id, str(data.amount), data.reason]).encode()).hexdigest()
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE'); bill = load(conn, business_id, location_id, bill_id, actor)
            previous = conn.execute('SELECT id,request_hash FROM supplier_payments WHERE business_id=? AND idempotency_key=?', (business_id, data.idempotency_key)).fetchone()
            if previous:
                if previous['request_hash'] != signature:
                    raise HTTPException(409, 'Payment reference already used for another allocation')
                return {'id': previous['id'], 'duplicate': True}
            if bill['status'] != 'open':
                raise HTTPException(409, 'Voided bills cannot receive payment allocations')
            record = conn.execute("SELECT * FROM financial_records WHERE id=? AND business_id=? AND location_id=? AND direction='expense' AND status='posted'", (data.record_id, business_id, location_id)).fetchone()
            if not record:
                raise HTTPException(404, 'Posted expense debit not found at this location')
            if record['occurred_on'] < bill['issued_on']:
                raise HTTPException(422, 'This debit predates the invoice; advance payments require separate review')
            used = conn.execute('SELECT coalesce(sum(amount_minor),0) FROM supplier_payments WHERE record_id=? AND reversed_at IS NULL', (data.record_id,)).fetchone()[0]
            paid = conn.execute('SELECT coalesce(sum(amount_minor),0) FROM supplier_payments WHERE bill_id=? AND reversed_at IS NULL', (bill_id,)).fetchone()[0]
            amount = int(data.amount * 100)
            if amount > record['amount_minor'] - int(used) or amount > bill['amount_minor'] - int(paid):
                raise HTTPException(409, 'Allocation exceeds the available debit or outstanding bill amount')
            pid = secrets.token_hex(16)
            conn.execute('INSERT INTO supplier_payments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (pid, business_id, location_id, bill_id, data.record_id, amount, actor['id'], data.reason, time.time(), data.idempotency_key, signature, None, None, None))
            audit(conn, business_id, actor['id'], f'Linked existing debit to supplier bill {bill_id}; allocation {pid}')
        return {'id': pid, 'duplicate': False}

    @app.post(base + '/{bill_id}/payments/{payment_id}/reverse')
    def reverse(business_id: str, location_id: str, bill_id: str, payment_id: str, data: VoidInput, actor=Depends(verified_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE'); load(conn, business_id, location_id, bill_id, actor)
            row = conn.execute('SELECT * FROM supplier_payments WHERE id=? AND bill_id=?', (payment_id, bill_id)).fetchone()
            if not row:
                raise HTTPException(404, 'Bill payment allocation not found')
            if row['reversed_at'] is None:
                conn.execute('UPDATE supplier_payments SET reversed_at=?,reversed_by=?,reverse_reason=? WHERE id=?', (time.time(), actor['id'], data.reason, payment_id))
                audit(conn, business_id, actor['id'], f'Reversed supplier allocation {payment_id}: {data.reason}')
        return {'success': True}

    @app.post(base + '/{bill_id}/void')
    def void(business_id: str, location_id: str, bill_id: str, data: VoidInput, actor=Depends(verified_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE'); row = load(conn, business_id, location_id, bill_id, actor)
            if row['status'] == 'open':
                if conn.execute('SELECT id FROM supplier_payments WHERE bill_id=? AND reversed_at IS NULL', (bill_id,)).fetchone():
                    raise HTTPException(409, 'Reverse the payment allocations before voiding this bill')
                conn.execute("UPDATE supplier_bills SET status='voided',void_reason=?,voided_at=? WHERE id=?", (data.reason, time.time(), bill_id))
                audit(conn, business_id, actor['id'], f'Voided supplier bill {bill_id}: {data.reason}')
        return {'success': True}
