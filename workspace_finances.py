"""Location-scoped local ledger: exact minor-unit money, immutable entries and voids."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import secrets
import time

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator


class FinancialInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    location_id: str = Field(min_length=1, max_length=64)
    direction: str = Field(pattern=r'^(income|expense)$')
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(default='NGN', pattern=r'^NGN$')
    occurred_on: date
    description: str = Field(min_length=2, max_length=240)
    category: str = Field(min_length=2, max_length=60)
    idempotency_key: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')

    @field_validator('occurred_on')
    @classmethod
    def posted_date(cls, value):
        if value > datetime.now(timezone(timedelta(hours=1))).date():
            raise ValueError('Use today or an earlier date for recorded money')
        return value


class VoidInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    reason: str = Field(min_length=3, max_length=240)


def money(minor):
    return format(Decimal(minor) / 100, '.2f')


def install_finances(app, db, verified_user, membership, audit):
    with db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS financial_records (
              id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id),
              location_id TEXT NOT NULL REFERENCES locations(id), actor_id TEXT NOT NULL REFERENCES users(id),
              direction TEXT NOT NULL CHECK(direction IN ('income','expense')),
              amount_minor INTEGER NOT NULL CHECK(amount_minor>0), currency TEXT NOT NULL CHECK(currency='NGN'),
              occurred_on TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
              source TEXT NOT NULL DEFAULT 'manual', status TEXT NOT NULL DEFAULT 'posted' CHECK(status IN ('posted','voided')),
              created_at REAL NOT NULL, idempotency_key TEXT NOT NULL, void_reason TEXT, voided_at REAL,
              UNIQUE(business_id,idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS financial_location_date ON financial_records(business_id,location_id,occurred_on);
        ''')

    def scope(conn, business_id, actor, location_id=None):
        member = membership(conn, business_id, actor)
        if member['role'] not in {'owner', 'manager', 'finance'}:
            raise HTTPException(403, 'Financial records are available to the owner, manager and finance team')
        if member['role'] != 'owner':
            if location_id and location_id != member['location_id']:
                raise HTTPException(404, 'Location not found')
            location_id = member['location_id']
        if location_id and not conn.execute('SELECT id FROM locations WHERE id=? AND business_id=?', (location_id, business_id)).fetchone():
            raise HTTPException(404, 'Location not found')
        return location_id

    @app.get('/enterprise-api/businesses/{business_id}/financial-records')
    def list_records(business_id: str, location_id: str | None = None, actor=Depends(verified_user)):
        with db() as conn:
            lid = scope(conn, business_id, actor, location_id)
            params = (business_id, lid, lid)
            rows = conn.execute('SELECT r.*,l.name location_name,u.name recorded_by FROM financial_records r JOIN locations l ON l.id=r.location_id '
                                'JOIN users u ON u.id=r.actor_id WHERE r.business_id=? AND (? IS NULL OR r.location_id=?) ORDER BY r.occurred_on DESC,r.created_at DESC LIMIT 100', params).fetchall()
            totals = conn.execute("SELECT direction,sum(amount_minor) amount FROM financial_records WHERE business_id=? AND (? IS NULL OR location_id=?) AND status='posted' GROUP BY direction", params).fetchall()
            count = conn.execute('SELECT count(*) FROM financial_records WHERE business_id=? AND (? IS NULL OR location_id=?)', params).fetchone()[0]
        amounts = {r['direction']: r['amount'] for r in totals}
        records = []
        for row in rows:
            record = dict(row)
            record['amount'] = money(record.pop('amount_minor'))
            record.pop('idempotency_key')
            records.append(record)
        return {'records': records, 'count': count, 'location_id': lid, 'currency': 'NGN',
                'totals': {'income': money(amounts.get('income', 0)), 'expenses': money(amounts.get('expense', 0)),
                           'net': money(amounts.get('income', 0) - amounts.get('expense', 0))}}

    @app.post('/enterprise-api/businesses/{business_id}/financial-records', status_code=201)
    def add_record(business_id: str, data: FinancialInput, actor=Depends(verified_user)):
        minor = int(data.amount * 100)
        values = (data.location_id, data.direction, minor, data.currency, data.occurred_on.isoformat(), data.description, data.category)
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            scope(conn, business_id, actor, data.location_id)
            previous = conn.execute('SELECT * FROM financial_records WHERE business_id=? AND idempotency_key=?', (business_id, data.idempotency_key)).fetchone()
            if previous:
                prior = tuple(previous[k] for k in ['location_id', 'direction', 'amount_minor', 'currency', 'occurred_on', 'description', 'category'])
                if previous['actor_id'] != actor['id'] or prior != values:
                    raise HTTPException(409, 'This save reference has already been used for a different record')
                return {'id': previous['id'], 'duplicate': True}
            rid = secrets.token_hex(16)
            conn.execute('INSERT INTO financial_records (id,business_id,actor_id,location_id,direction,amount_minor,currency,occurred_on,description,category,created_at,idempotency_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                         (rid, business_id, actor['id'], *values, time.time(), data.idempotency_key))
            audit(conn, business_id, actor['id'], f'Recorded {data.direction}: NGN {money(minor)} — {data.description}')
        return {'id': rid, 'duplicate': False}

    @app.post('/enterprise-api/businesses/{business_id}/financial-records/{record_id}/void')
    def void_record(business_id: str, record_id: str, data: VoidInput, actor=Depends(verified_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            scope(conn, business_id, actor)
            record = conn.execute('SELECT * FROM financial_records WHERE id=? AND business_id=?', (record_id, business_id)).fetchone()
            if not record:
                raise HTTPException(404, 'Record not found')
            scope(conn, business_id, actor, record['location_id'])
            if record['status'] == 'posted':
                if conn.execute('SELECT id FROM payment_allocations WHERE record_id=? AND reversed_at IS NULL', (record_id,)).fetchone():
                    raise HTTPException(409, 'Reverse payment allocations before voiding this income record')
                conn.execute("UPDATE financial_records SET status='voided',void_reason=?,voided_at=? WHERE id=?", (data.reason, time.time(), record_id))
                audit(conn, business_id, actor['id'], f'Voided record {record_id}: {data.reason}')
        return {'success': True}
