"""Private receipt versions, independent review and one canonical posted expense."""
import base64
import binascii
from datetime import date
from decimal import Decimal
import hashlib
from io import BytesIO
import json
import secrets
import time
import threading

from fastapi import Depends, HTTPException, Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from workspace_finances import FinancialInput, VoidInput, money
from workspace_receipt_reader import read_receipt, parse_receipt, ReceiptReadError

READER_LOCK = threading.BoundedSemaphore(1)


class ExtractionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    receipt_base64: str = Field(min_length=8, max_length=2800000)


class ExpenseInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    vendor: str = Field(min_length=2, max_length=120)
    purpose: str = Field(min_length=3, max_length=500)
    category: str = Field(min_length=2, max_length=60)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    occurred_on: date
    receipt_base64: str = Field(min_length=8, max_length=2800000)
    idempotency_key: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    extraction_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')

    @field_validator('occurred_on')
    @classmethod
    def past_date(cls, value):
        return FinancialInput.posted_date(value)


class ReviewInput(VoidInput):
    decision: str = Field(pattern=r'^(approved|rejected|needs_clarification)$')
    revision: int = Field(strict=True, ge=1)


class PostInput(VoidInput):
    record_id: str | None = None
    confirm_new: bool = False


def receipt_bytes(encoded):
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(422, 'Choose a valid JPEG, PNG or PDF receipt')
    if not data or len(data) > 2 * 1024 * 1024:
        raise HTTPException(422, 'Receipt must be no larger than 2 MB')
    if data.startswith(b'%PDF-') and b'%%EOF' in data[-2048:]:
        return data, 'application/pdf', 'pdf'
    try:
        with Image.open(BytesIO(data)) as picture:
            if picture.format not in {'JPEG', 'PNG'} or picture.width * picture.height > 20_000_000:
                raise ValueError('Image format or dimensions')
            picture.verify()
            return data, 'image/jpeg' if picture.format == 'JPEG' else 'image/png', 'jpg' if picture.format == 'JPEG' else 'png'
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(422, 'Receipt must be a valid JPEG, PNG or PDF')


def install_expenses(app, db, verified_user, membership, audit):
    with db() as conn:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS expense_submissions (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            submitter_id TEXT NOT NULL REFERENCES users(id),status TEXT NOT NULL,revision INTEGER NOT NULL,
            created_at REAL NOT NULL,record_id TEXT UNIQUE REFERENCES financial_records(id)
          );
          CREATE TABLE IF NOT EXISTS expense_versions (
            expense_id TEXT NOT NULL REFERENCES expense_submissions(id),revision INTEGER NOT NULL,
            vendor TEXT NOT NULL,purpose TEXT NOT NULL,category TEXT NOT NULL,amount_minor INTEGER NOT NULL CHECK(amount_minor>0),
            occurred_on TEXT NOT NULL,receipt BLOB NOT NULL,mime TEXT NOT NULL,extension TEXT NOT NULL,receipt_hash TEXT NOT NULL,
            created_at REAL NOT NULL,idempotency_key TEXT NOT NULL,request_hash TEXT NOT NULL,
            PRIMARY KEY(expense_id,revision),UNIQUE(expense_id,idempotency_key)
          );
          CREATE TABLE IF NOT EXISTS expense_events (
            id TEXT PRIMARY KEY,expense_id TEXT NOT NULL REFERENCES expense_submissions(id),revision INTEGER NOT NULL,
            actor_id TEXT NOT NULL REFERENCES users(id),action TEXT NOT NULL,reason TEXT NOT NULL,created_at REAL NOT NULL
          );
          CREATE TABLE IF NOT EXISTS expense_creation_keys (
            business_id TEXT NOT NULL REFERENCES businesses(id),actor_id TEXT NOT NULL REFERENCES users(id),
            idempotency_key TEXT NOT NULL,expense_id TEXT NOT NULL REFERENCES expense_submissions(id),PRIMARY KEY(business_id,actor_id,idempotency_key)
          );
          CREATE TABLE IF NOT EXISTS receipt_extractions (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            actor_id TEXT NOT NULL REFERENCES users(id),receipt_hash TEXT NOT NULL,created_at REAL NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending','success','failed')),engine TEXT,result TEXT
          );
          CREATE INDEX IF NOT EXISTS receipt_extraction_actor_time ON receipt_extractions(actor_id,created_at);
          CREATE TABLE IF NOT EXISTS expense_extractions (
            expense_id TEXT NOT NULL,revision INTEGER NOT NULL,extraction_id TEXT NOT NULL REFERENCES receipt_extractions(id),
            PRIMARY KEY(expense_id,revision),FOREIGN KEY(expense_id,revision) REFERENCES expense_versions(expense_id,revision)
          );
        ''')

    base = '/enterprise-api/businesses/{business_id}/locations/{location_id}/expenses'

    def scope(conn, bid, lid, actor, review=False):
        member = membership(conn, bid, actor)
        if member['role'] != 'owner' and member['location_id'] != lid:
            raise HTTPException(404, 'Location not found')
        if not conn.execute('SELECT id FROM locations WHERE id=? AND business_id=?', (lid, bid)).fetchone():
            raise HTTPException(404, 'Location not found')
        privileged = member['role'] in {'owner', 'manager', 'finance'}
        if review and not privileged:
            raise HTTPException(403, 'Only the owner, manager or finance team can review expenses')
        return privileged

    def load(conn, bid, lid, eid, actor, review=False):
        privileged = scope(conn, bid, lid, actor, review)
        row = conn.execute('SELECT * FROM expense_submissions WHERE id=? AND business_id=? AND location_id=?', (eid, bid, lid)).fetchone()
        if not row or (not privileged and row['submitter_id'] != actor['id']):
            raise HTTPException(404, 'Expense not found')
        return row

    def event(conn, eid, revision, actor, action, reason):
        conn.execute('INSERT INTO expense_events VALUES (?,?,?,?,?,?,?)', (secrets.token_hex(16), eid, revision, actor['id'], action, reason, time.time()))

    def version_values(data):
        raw, mime, extension = receipt_bytes(data.receipt_base64)
        digest = hashlib.sha256(raw).hexdigest()
        values = (data.vendor, data.purpose, data.category, int(data.amount * 100), data.occurred_on.isoformat())
        signature = hashlib.sha256(json.dumps([*values, digest, *([data.extraction_id] if data.extraction_id else [])]).encode()).hexdigest()
        return values, raw, mime, extension, digest, signature

    def insert_version(conn, eid, revision, data, values):
        fields, raw, mime, extension, digest, signature = values
        if data.extraction_id:
            extraction = conn.execute('SELECT * FROM receipt_extractions WHERE id=?', (data.extraction_id,)).fetchone()
            expense = conn.execute('SELECT business_id,location_id,submitter_id FROM expense_submissions WHERE id=?', (eid,)).fetchone()
            if not extraction or extraction['status'] != 'success' or (extraction['business_id'], extraction['location_id'], extraction['actor_id'], extraction['receipt_hash']) != (expense['business_id'], expense['location_id'], expense['submitter_id'], digest):
                raise HTTPException(422, 'Extraction must belong to you, this location and this exact receipt')
        conn.execute('INSERT INTO expense_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (eid, revision, *fields, raw, mime, extension, digest, time.time(), data.idempotency_key, signature))
        if data.extraction_id:
            conn.execute('INSERT INTO expense_extractions VALUES (?,?,?)', (eid, revision, data.extraction_id))

    def public(conn, row):
        current = conn.execute('SELECT * FROM expense_versions WHERE expense_id=? AND revision=?', (row['id'], row['revision'])).fetchone()
        result = {**dict(row), **{key: current[key] for key in ['vendor', 'purpose', 'category', 'occurred_on', 'mime', 'receipt_hash']}, 'amount': money(current['amount_minor'])}
        result['submitter'] = conn.execute('SELECT name FROM users WHERE id=?', (row['submitter_id'],)).fetchone()[0]
        result['history'] = [dict(item) for item in conn.execute('SELECT e.revision,e.action,e.reason,e.created_at,u.name actor FROM expense_events e JOIN users u ON u.id=e.actor_id WHERE e.expense_id=? ORDER BY e.created_at', (row['id'],))]
        result['versions'] = [{**dict(item), 'amount': money(item['amount_minor'])} for item in conn.execute('SELECT revision,vendor,purpose,category,occurred_on,amount_minor,receipt_hash FROM expense_versions WHERE expense_id=? ORDER BY revision', (row['id'],))]
        for item in result['versions']:
            item.pop('amount_minor')
            extracted = conn.execute('SELECT x.engine,x.result FROM expense_extractions e JOIN receipt_extractions x ON x.id=e.extraction_id WHERE e.expense_id=? AND e.revision=?', (row['id'], item['revision'])).fetchone()
            item['extraction'] = {'engine': extracted['engine'], **json.loads(extracted['result'])} if extracted else None
        if row['record_id']:
            ledger = conn.execute('SELECT status,void_reason FROM financial_records WHERE id=?', (row['record_id'],)).fetchone()
            result['ledger_status'], result['ledger_void_reason'] = ledger['status'], ledger['void_reason']
        return result

    @app.get(base)
    def list_expenses(business_id: str, location_id: str, actor=Depends(verified_user)):
        with db() as conn:
            privileged = int(scope(conn, business_id, location_id, actor))
            rows = conn.execute('SELECT * FROM expense_submissions WHERE business_id=? AND location_id=? AND (?=1 OR submitter_id=?) ORDER BY created_at DESC LIMIT 100', (business_id, location_id, privileged, actor['id'])).fetchall()
            count = conn.execute('SELECT count(*) FROM expense_submissions WHERE business_id=? AND location_id=? AND (?=1 OR submitter_id=?)', (business_id, location_id, privileged, actor['id'])).fetchone()[0]
            # Category totals use the canonical ledger, so linked bank debits are never counted twice.
            categories = [{'category': row['category'], 'amount': money(row['total']), 'count': row['count']} for row in conn.execute("SELECT min(category) category,sum(amount_minor) total,count(*) count FROM financial_records WHERE business_id=? AND location_id=? AND direction='expense' AND status='posted' GROUP BY lower(category) ORDER BY total DESC", (business_id, location_id))] if privileged else []
            expenses = [public(conn, row) for row in rows]
            for item in expenses:
                if privileged and item['status'] == 'approved':
                    item['debit_candidates'] = [dict(record) for record in conn.execute("SELECT r.id,r.description FROM financial_records r LEFT JOIN expense_submissions e ON e.record_id=r.id WHERE r.business_id=? AND r.location_id=? AND r.direction='expense' AND r.status='posted' AND r.amount_minor=? AND r.occurred_on=? AND lower(r.category)=lower(?) AND e.id IS NULL", (business_id, location_id, int(Decimal(item['amount']) * 100), item['occurred_on'], item['category']))]
            return {'expenses': expenses, 'count': count, 'can_review': privileged, 'actor_id': actor['id'], 'categories': categories}

    @app.get(base + '/categories/{category}')
    def category_detail(business_id: str, location_id: str, category: str, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, location_id, actor, review=True)
            rows = conn.execute("SELECT r.id,r.description,r.amount_minor,r.occurred_on,r.source,u.name recorded_by,e.id expense_id,e.revision expense_revision,s.name submitter FROM financial_records r JOIN users u ON u.id=r.actor_id LEFT JOIN expense_submissions e ON e.record_id=r.id LEFT JOIN users s ON s.id=e.submitter_id WHERE r.business_id=? AND r.location_id=? AND r.direction='expense' AND r.status='posted' AND lower(r.category)=lower(?) ORDER BY r.occurred_on DESC", (business_id, location_id, category)).fetchall()
            return {'records': [{**{key: row[key] for key in row.keys() if key != 'amount_minor'}, 'amount': money(row['amount_minor'])} for row in rows]}

    @app.post(base + '/extract')
    def extract_receipt(business_id: str, location_id: str, data: ExtractionInput, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, location_id, actor)
        raw, mime, _ = receipt_bytes(data.receipt_base64)
        digest = hashlib.sha256(raw).hexdigest()
        with db() as conn:
            scope(conn, business_id, location_id, actor)
            cached = conn.execute("SELECT id,result,engine FROM receipt_extractions WHERE business_id=? AND location_id=? AND actor_id=? AND receipt_hash=? AND status='success' ORDER BY created_at DESC LIMIT 1", (business_id, location_id, actor['id'], digest)).fetchone()
            if cached:
                return {'id': cached['id'], 'engine': cached['engine'], **json.loads(cached['result'])}
            attempts = conn.execute('SELECT count(*) FROM receipt_extractions WHERE actor_id=? AND created_at>?', (actor['id'], time.time() - 3600)).fetchone()[0]
            if attempts >= 10:
                raise HTTPException(429, 'Receipt reading limit reached. Try again in an hour or enter details manually.')
        if not READER_LOCK.acquire(blocking=False):
            raise HTTPException(429, 'Receipt reader is busy. Please try again shortly.')
        xid = secrets.token_hex(16)
        try:
            with db() as conn:
                scope(conn, business_id, location_id, actor)
                if conn.execute('SELECT count(*) FROM receipt_extractions WHERE actor_id=? AND created_at>?', (actor['id'], time.time() - 3600)).fetchone()[0] >= 10:
                    raise HTTPException(429, 'Receipt reading limit reached. Enter details manually or try again later.')
                conn.execute('INSERT INTO receipt_extractions VALUES (?,?,?,?,?,?,?,NULL,NULL)', (xid, business_id, location_id, actor['id'], digest, time.time(), 'pending'))
            try:
                text, engine = read_receipt(raw, mime)
                result = parse_receipt(text)
            except ReceiptReadError as error:
                with db() as conn:
                    conn.execute("UPDATE receipt_extractions SET status='failed' WHERE id=?", (xid,))
                raise HTTPException(503, str(error))
            with db() as conn:
                scope(conn, business_id, location_id, actor)
                conn.execute("UPDATE receipt_extractions SET status='success',engine=?,result=? WHERE id=?", (engine, json.dumps(result), xid))
            return {'id': xid, 'engine': engine, **result}
        finally:
            READER_LOCK.release()

    @app.post(base, status_code=201)
    def submit_expense(business_id: str, location_id: str, data: ExpenseInput, actor=Depends(verified_user)):
        values = version_values(data)
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            scope(conn, business_id, location_id, actor)
            previous = conn.execute('SELECT e.id,e.location_id,v.request_hash FROM expense_creation_keys k JOIN expense_submissions e ON e.id=k.expense_id JOIN expense_versions v ON v.expense_id=e.id AND v.revision=1 WHERE k.business_id=? AND k.actor_id=? AND k.idempotency_key=?', (business_id, actor['id'], data.idempotency_key)).fetchone()
            if previous:
                if previous['request_hash'] != values[-1] or previous['location_id'] != location_id:
                    raise HTTPException(409, 'This submission reference already identifies a different expense')
                return {'id': previous['id'], 'duplicate': True}
            if conn.execute('SELECT v.expense_id FROM expense_versions v JOIN expense_submissions e ON e.id=v.expense_id WHERE e.business_id=? AND v.receipt_hash=?', (business_id, values[-2])).fetchone():
                raise HTTPException(409, 'This receipt already has an expense submission. Use its existing history.')
            eid = secrets.token_hex(16)
            conn.execute('INSERT INTO expense_submissions VALUES (?,?,?,?,?,?,?,NULL)', (eid, business_id, location_id, actor['id'], 'submitted', 1, time.time()))
            insert_version(conn, eid, 1, data, values)
            conn.execute('INSERT INTO expense_creation_keys VALUES (?,?,?,?)', (business_id, actor['id'], data.idempotency_key, eid))
            event(conn, eid, 1, actor, 'submitted', data.purpose)
            audit(conn, business_id, actor['id'], f'Submitted expense {eid}')
        return {'id': eid, 'duplicate': False}

    @app.put(base + '/{expense_id}')
    def resubmit(business_id: str, location_id: str, expense_id: str, data: ExpenseInput, actor=Depends(verified_user)):
        values = version_values(data)
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = load(conn, business_id, location_id, expense_id, actor)
            if row['submitter_id'] != actor['id']:
                raise HTTPException(403, 'Only the submitter can revise this expense')
            previous = conn.execute('SELECT request_hash FROM expense_versions WHERE expense_id=? AND idempotency_key=?', (expense_id, data.idempotency_key)).fetchone()
            if previous:
                if previous[0] != values[-1]:
                    raise HTTPException(409, 'This revision reference was already used for another version')
                return {'success': True, 'duplicate': True}
            if row['status'] not in {'rejected', 'needs_clarification'}:
                raise HTTPException(409, 'Only rejected or clarification-needed expenses can be revised')
            if conn.execute('SELECT v.expense_id FROM expense_versions v JOIN expense_submissions e ON e.id=v.expense_id WHERE e.business_id=? AND v.receipt_hash=? AND e.id!=?', (business_id, values[-2], expense_id)).fetchone():
                raise HTTPException(409, 'This receipt belongs to another expense submission')
            revision = row['revision'] + 1
            insert_version(conn, expense_id, revision, data, values)
            conn.execute("UPDATE expense_submissions SET status='submitted',revision=? WHERE id=?", (revision, expense_id))
            event(conn, expense_id, revision, actor, 'resubmitted', data.purpose)
            audit(conn, business_id, actor['id'], f'Resubmitted expense {expense_id}, version {revision}')
        return {'success': True}

    @app.get(base + '/{expense_id}/receipt/{revision}')
    def get_receipt(business_id: str, location_id: str, expense_id: str, revision: int, actor=Depends(verified_user)):
        with db() as conn:
            load(conn, business_id, location_id, expense_id, actor)
            row = conn.execute('SELECT receipt,extension FROM expense_versions WHERE expense_id=? AND revision=?', (expense_id, revision)).fetchone()
            if not row:
                raise HTTPException(404, 'Receipt version not found')
        return Response(content=row['receipt'], media_type='application/octet-stream', headers={'Content-Disposition': f'attachment; filename="receipt-{expense_id}-v{revision}.{row["extension"]}"', 'Content-Security-Policy': "default-src 'none'; sandbox"})

    @app.post(base + '/{expense_id}/review')
    def review_expense(business_id: str, location_id: str, expense_id: str, data: ReviewInput, actor=Depends(verified_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = load(conn, business_id, location_id, expense_id, actor, review=True)
            if row['submitter_id'] == actor['id']:
                raise HTTPException(403, 'A different person must review this expense')
            if row['revision'] != data.revision or row['status'] != 'submitted':
                raise HTTPException(409, 'This expense changed or was already reviewed. Refresh it before deciding.')
            conn.execute('UPDATE expense_submissions SET status=? WHERE id=?', (data.decision, expense_id))
            event(conn, expense_id, row['revision'], actor, data.decision, data.reason)
            audit(conn, business_id, actor['id'], f'Expense {expense_id}: {data.decision} — {data.reason}')
        return {'success': True}

    @app.post(base + '/{expense_id}/post')
    def post_expense(business_id: str, location_id: str, expense_id: str, data: PostInput, actor=Depends(verified_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = load(conn, business_id, location_id, expense_id, actor, review=True)
            if row['status'] == 'posted':
                if data.record_id and data.record_id != row['record_id']:
                    raise HTTPException(409, 'This expense is already linked to another ledger entry')
                return {'record_id': row['record_id'], 'duplicate': True}
            if row['status'] != 'approved':
                raise HTTPException(409, 'Approve the expense before posting')
            current = conn.execute('SELECT * FROM expense_versions WHERE expense_id=? AND revision=?', (expense_id, row['revision'])).fetchone()
            if data.record_id:
                record = conn.execute("SELECT * FROM financial_records WHERE id=? AND business_id=? AND location_id=? AND direction='expense' AND status='posted' AND currency='NGN'", (data.record_id, business_id, location_id)).fetchone()
                if not record:
                    raise HTTPException(404, 'Posted expense record not found')
                if (record['amount_minor'], record['occurred_on'], record['category'].casefold()) != (current['amount_minor'], current['occurred_on'], current['category'].casefold()):
                    raise HTTPException(409, 'Existing debit must match the receipt amount, date and category')
                if conn.execute('SELECT id FROM expense_submissions WHERE record_id=?', (data.record_id,)).fetchone():
                    raise HTTPException(409, 'This debit already has a linked receipt expense')
                rid = data.record_id
            else:
                if not data.confirm_new and conn.execute("SELECT id FROM financial_records WHERE business_id=? AND location_id=? AND direction='expense' AND status='posted' AND amount_minor=? AND occurred_on=? AND lower(category)=lower(?)", (business_id, location_id, current['amount_minor'], current['occurred_on'], current['category'])).fetchone():
                    raise HTTPException(409, 'A similar debit already exists. Link it or explicitly confirm a separate expense after review.')
                rid = secrets.token_hex(16)
                conn.execute('INSERT INTO financial_records (id,business_id,location_id,actor_id,direction,amount_minor,currency,occurred_on,description,category,source,created_at,idempotency_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (rid, business_id, location_id, actor['id'], 'expense', current['amount_minor'], 'NGN', current['occurred_on'], current['vendor'] + ': ' + current['purpose'][:100], current['category'], 'approved_expense', time.time(), 'expense-' + expense_id))
            conn.execute("UPDATE expense_submissions SET status='posted',record_id=? WHERE id=?", (rid, expense_id))
            event(conn, expense_id, row['revision'], actor, 'posted', data.reason)
            audit(conn, business_id, actor['id'], f'Posted expense {expense_id} to ledger record {rid}')
        return {'record_id': rid, 'duplicate': False}
