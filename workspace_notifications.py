"""Reviewed balance notices and revocable customer invoice links; no automatic sends."""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import time

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from workspace_email import send_smtp
from workspace_invoices import DeliveryInput
from workspace_payments import payment_summary, payment_totals


class NoticeInput(DeliveryInput):
    invoice_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(pattern=r'^(partial_payment|overdue)$')


class SendNotice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirm_retry: bool = False


class ShareInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expires_days: int = Field(default=7, strict=True, ge=1, le=30)


class CustomerToken(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=40, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')


def balance_fingerprint(conn, invoice):
    values = [(r['id'], r['amount_minor']) for r in conn.execute("SELECT a.id,a.amount_minor FROM payment_allocations a JOIN financial_records r ON r.id=a.record_id WHERE a.invoice_id=? AND a.reversed_at IS NULL AND r.status='posted' ORDER BY a.id", (invoice['id'],))]
    return hashlib.sha256(json.dumps([invoice['status'], invoice['due_on'], values]).encode()).hexdigest()


def install_notifications(app, db, verified_user, membership, audit, transport, web_origin):
    with db() as conn:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS customer_notices (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            invoice_id TEXT NOT NULL REFERENCES invoices(id),actor_id TEXT NOT NULL REFERENCES users(id),kind TEXT NOT NULL,
            recipient TEXT NOT NULL,balance_hash TEXT NOT NULL,subject TEXT NOT NULL,body TEXT NOT NULL,
            status TEXT NOT NULL,transport TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL,
            idempotency_key TEXT NOT NULL,dedupe_key TEXT NOT NULL,UNIQUE(business_id,idempotency_key),UNIQUE(invoice_id,dedupe_key)
          );
          CREATE INDEX IF NOT EXISTS customer_notice_invoice_time ON customer_notices(invoice_id,updated_at);
          CREATE TABLE IF NOT EXISTS invoice_shares (
            id TEXT PRIMARY KEY,token_hash TEXT NOT NULL UNIQUE,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            invoice_id TEXT NOT NULL REFERENCES invoices(id),actor_id TEXT NOT NULL REFERENCES users(id),created_at REAL NOT NULL,expires_at REAL NOT NULL,revoked_at REAL
          );
        ''')
    base = '/enterprise-api/businesses/{business_id}/locations/{location_id}'

    def scope(conn, bid, lid, actor, sharing=False):
        member = membership(conn, bid, actor)
        allowed = {'owner', 'manager', 'front_desk'} if sharing else {'owner', 'manager', 'finance'}
        if member['role'] not in allowed:
            raise HTTPException(403, 'Your role does not allow this customer communication')
        if member['role'] != 'owner' and member['location_id'] != lid:
            raise HTTPException(404, 'Location not found')
        if not conn.execute('SELECT id FROM locations WHERE id=? AND business_id=?', (lid, bid)).fetchone():
            raise HTTPException(404, 'Location not found')

    def invoice_at(conn, bid, lid, iid):
        row = conn.execute('SELECT i.*,o.customer_name,o.customer_contact,o.status order_status FROM invoices i JOIN orders o ON o.id=i.order_id WHERE i.id=? AND o.business_id=? AND o.location_id=?', (iid, bid, lid)).fetchone()
        if not row:
            raise HTTPException(404, 'Invoice not found')
        return row

    def eligible(conn, invoice, kind):
        payments = payment_summary(conn, invoice)
        if invoice['status'] != 'issued' or invoice['order_status'] != 'open' or payments['outstanding'] == '0.00':
            raise HTTPException(409, 'Only an issued invoice with an outstanding balance can receive this notice')
        today = datetime.now(timezone(timedelta(hours=1))).date().isoformat()
        if kind == 'partial_payment' and payments['status'] != 'part_paid':
            raise HTTPException(409, 'This invoice does not currently have a partial payment')
        if kind == 'overdue' and (not invoice['due_on'] or invoice['due_on'] >= today):
            raise HTTPException(409, 'This invoice is not overdue')
        return payments

    @app.get(base + '/customer-notifications')
    def list_notices(business_id: str, location_id: str, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, location_id, actor)
            conn.execute("UPDATE customer_notices SET status='unknown',updated_at=? WHERE business_id=? AND location_id=? AND status='sending' AND updated_at<?", (time.time(), business_id, location_id, time.time() - 120))
            candidates = []
            rows = conn.execute("SELECT i.id,i.number,i.status,i.due_on,o.customer_name,o.customer_contact,o.total_minor,coalesce((SELECT sum(a.amount_minor) FROM payment_allocations a JOIN financial_records r ON r.id=a.record_id WHERE a.invoice_id=i.id AND a.reversed_at IS NULL AND r.status='posted'),0) paid FROM invoices i JOIN orders o ON o.id=i.order_id WHERE o.business_id=? AND o.location_id=? AND i.status='issued' ORDER BY i.issued_at DESC LIMIT 5001", (business_id, location_id)).fetchall()
            if len(rows) > 5000:
                raise HTTPException(413, 'This message view supports 5,000 issued invoices per location; ask the operator for an archive/reporting plan')
            for row in rows:
                payments = payment_totals(row['total_minor'], row['paid'], row['status'])
                if payments['outstanding'] == '0.00':
                    continue
                kinds = ['partial_payment'] if payments['status'] == 'part_paid' else []
                if row['due_on'] and row['due_on'] < datetime.now(timezone(timedelta(hours=1))).date().isoformat():
                    kinds.append('overdue')
                if kinds:
                    candidates.append({'id': row['id'], 'number': row['number'], 'customer': row['customer_name'], 'contact': row['customer_contact'], 'due_on': row['due_on'], 'payments': payments, 'kinds': kinds})
            history = [dict(r) for r in conn.execute('SELECT id,invoice_id,kind,recipient,subject,body,status,transport,created_at,updated_at FROM customer_notices WHERE business_id=? AND location_id=? ORDER BY created_at DESC LIMIT 100', (business_id, location_id))]
            return {'candidates': candidates, 'history': history, 'transport': transport}

    @app.post(base + '/customer-notifications', status_code=201)
    def prepare(business_id: str, location_id: str, data: NoticeInput, actor=Depends(verified_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE'); scope(conn, business_id, location_id, actor)
            existing = conn.execute('SELECT * FROM customer_notices WHERE business_id=? AND idempotency_key=?', (business_id, data.idempotency_key)).fetchone()
            if existing:
                if (existing['location_id'], existing['invoice_id'], existing['kind'], existing['recipient'], existing['actor_id']) != (location_id, data.invoice_id, data.kind, data.recipient, actor['id']):
                    raise HTTPException(409, 'This notice reference was already used for another request')
                return {'id': existing['id'], 'duplicate': True}
            invoice = invoice_at(conn, business_id, location_id, data.invoice_id); payments = eligible(conn, invoice, data.kind)
            fingerprint = balance_fingerprint(conn, invoice)
            day = datetime.now(timezone(timedelta(hours=1))).date().isoformat()
            dedupe = hashlib.sha256(json.dumps([day, data.kind, data.recipient.casefold(), fingerprint]).encode()).hexdigest()
            existing = conn.execute('SELECT id FROM customer_notices WHERE invoice_id=? AND dedupe_key=?', (invoice['id'], dedupe)).fetchone()
            if existing:
                return {'id': existing['id'], 'duplicate': True}
            if conn.execute('SELECT count(*) FROM customer_notices WHERE actor_id=? AND created_at>?', (actor['id'], time.time() - 3600)).fetchone()[0] >= 30:
                raise HTTPException(429, 'Hourly customer message limit reached')
            snapshot = json.loads(invoice['snapshot']); label = 'Payment update' if data.kind == 'partial_payment' else 'Overdue payment reminder'
            subject = label + ' - ' + invoice['number']
            body = f'Hello {invoice["customer_name"]},\n\n{label} for {snapshot["profile"]["invoice_name"]}.\nInvoice: {invoice["number"]}\nInvoice total: NGN {payments["total"]}\nConfirmed allocations: NGN {payments["allocated"]}\nRemaining balance: NGN {payments["outstanding"]}\nDue: {invoice["due_on"] or "Not specified"}\n\nPlease contact the business if a recent payment is not reflected.\n{snapshot["profile"]["payment_instructions"]}\n\nBalance recorded at {datetime.now(timezone.utc).isoformat()}. This is not a bank settlement confirmation.'
            nid, now = secrets.token_hex(16), time.time()
            conn.execute('INSERT INTO customer_notices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (nid, business_id, location_id, invoice['id'], actor['id'], data.kind, data.recipient, fingerprint, subject, body, 'draft', transport, now, now, data.idempotency_key, dedupe))
            audit(conn, business_id, actor['id'], f'Prepared customer notice {nid}; not sent')
        return {'id': nid, 'duplicate': False}

    @app.post(base + '/customer-notifications/{notice_id}/send')
    def send(business_id: str, location_id: str, notice_id: str, data: SendNotice, actor=Depends(verified_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE'); scope(conn, business_id, location_id, actor)
            notice = conn.execute('SELECT * FROM customer_notices WHERE id=? AND business_id=? AND location_id=?', (notice_id, business_id, location_id)).fetchone()
            if not notice:
                raise HTTPException(404, 'Notice not found')
            if notice['status'] in {'captured', 'accepted', 'sending', 'unknown'}:
                return {'id': notice_id, 'status': notice['status'], 'duplicate': True}
            if notice['status'] == 'failed' and not data.confirm_retry:
                raise HTTPException(409, 'Explicitly confirm retrying this failed delivery')
            if notice['status'] == 'failed' and notice['updated_at'] > time.time() - 60:
                raise HTTPException(429, 'Wait one minute before retrying a failed customer delivery')
            invoice = invoice_at(conn, business_id, location_id, notice['invoice_id']); eligible(conn, invoice, notice['kind'])
            if not hmac.compare_digest(notice['balance_hash'], balance_fingerprint(conn, invoice)):
                raise HTTPException(409, 'Invoice balance changed. Prepare and review a fresh notice.')
            if conn.execute("SELECT id FROM customer_notices WHERE invoice_id=? AND status IN ('sending','accepted','captured','unknown') AND updated_at>?", (invoice['id'], time.time() - 86400)).fetchone():
                raise HTTPException(429, 'This invoice already has a recent customer notice. Wait 24 hours and check delivery history.')
            status = 'captured' if transport == 'capture' else 'sending'
            conn.execute('UPDATE customer_notices SET status=?,updated_at=? WHERE id=?', (status, time.time(), notice_id))
            audit(conn, business_id, actor['id'], f'Confirmed customer notice {notice_id}: {status}')
        if transport == 'smtp':
            try:
                message = EmailMessage(); message['From'] = os.environ['LOAMY_SMTP_FROM']; message['To'] = notice['recipient']; message['Subject'] = notice['subject']
                message['Message-ID'] = f'<loamy-notice-{notice_id}@localhost>'; message.set_content(notice['body'])
                send_smtp(message); status = 'accepted'
            except (KeyError, ValueError, smtplib.SMTPRecipientsRefused, smtplib.SMTPAuthenticationError):
                status = 'failed'
            except (OSError, smtplib.SMTPException):
                status = 'unknown'
            with db() as conn:
                conn.execute('UPDATE customer_notices SET status=?,updated_at=? WHERE id=?', (status, time.time(), notice_id))
        return {'id': notice_id, 'status': status, 'duplicate': False}

    @app.get(base + '/invoices/{invoice_id}/shares')
    def shares(business_id: str, location_id: str, invoice_id: str, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, location_id, actor, sharing=True); invoice_at(conn, business_id, location_id, invoice_id)
            return {'shares': [{**dict(r), 'expired': r['expires_at'] <= time.time()} for r in conn.execute('SELECT id,created_at,expires_at,revoked_at FROM invoice_shares WHERE invoice_id=? ORDER BY created_at DESC LIMIT 100', (invoice_id,))]}

    @app.post(base + '/invoices/{invoice_id}/shares', status_code=201)
    def create_share(business_id: str, location_id: str, invoice_id: str, data: ShareInput, actor=Depends(verified_user)):
        token = secrets.token_urlsafe(32); sid = secrets.token_hex(16); now = time.time()
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE'); scope(conn, business_id, location_id, actor, sharing=True)
            invoice = invoice_at(conn, business_id, location_id, invoice_id)
            if invoice['status'] != 'issued' or invoice['order_status'] != 'open':
                raise HTTPException(409, 'Cancelled invoices cannot be shared')
            if conn.execute('SELECT count(*) FROM invoice_shares WHERE actor_id=? AND created_at>?', (actor['id'], now - 3600)).fetchone()[0] >= 20:
                raise HTTPException(429, 'Hourly invoice link limit reached')
            conn.execute('INSERT INTO invoice_shares VALUES (?,?,?,?,?,?,?,?,NULL)', (sid, hashlib.sha256(token.encode()).hexdigest(), business_id, location_id, invoice_id, actor['id'], now, now + data.expires_days * 86400))
            audit(conn, business_id, actor['id'], f'Created revocable customer invoice link {sid}')
        return {'id': sid, 'url': web_origin + '/customer-invoice#token=' + token, 'expires_at': now + data.expires_days * 86400}

    @app.post(base + '/invoices/{invoice_id}/shares/{share_id}/revoke')
    def revoke_share(business_id: str, location_id: str, invoice_id: str, share_id: str, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, location_id, actor, sharing=True); invoice_at(conn, business_id, location_id, invoice_id)
            row = conn.execute('SELECT id FROM invoice_shares WHERE id=? AND invoice_id=?', (share_id, invoice_id)).fetchone()
            if not row:
                raise HTTPException(404, 'Invoice link not found')
            conn.execute('UPDATE invoice_shares SET revoked_at=? WHERE id=? AND revoked_at IS NULL', (time.time(), share_id))
            audit(conn, business_id, actor['id'], f'Revoked customer invoice link {share_id}')
        return {'success': True}

    def customer_invoice(conn, data):
        share = conn.execute('SELECT * FROM invoice_shares WHERE token_hash=? AND revoked_at IS NULL AND expires_at>?', (hashlib.sha256(data.token.encode()).hexdigest(), time.time())).fetchone()
        if not share:
            raise HTTPException(404, 'This invoice link is invalid, expired or revoked')
        invoice = invoice_at(conn, share['business_id'], share['location_id'], share['invoice_id'])
        if invoice['status'] != 'issued' or invoice['order_status'] != 'open':
            raise HTTPException(410, 'This invoice is cancelled; contact the business')
        return invoice

    @app.post('/enterprise-api/customer-invoice')
    def view_customer(data: CustomerToken):
        with db() as conn:
            invoice = customer_invoice(conn, data); payments = payment_summary(conn, invoice)
            # Public bearer access exposes no internal allocation notes, staff IDs or receipt evidence.
            return {'snapshot': json.loads(invoice['snapshot']), 'payments': {k: payments[k] for k in ['status', 'total', 'allocated', 'outstanding', 'overpayment']}, 'updated_at': time.time()}

    @app.post('/enterprise-api/customer-invoice/pdf')
    def customer_pdf(data: CustomerToken):
        with db() as conn:
            row = customer_invoice(conn, data)
            return Response(content=row['pdf'], media_type='application/pdf', headers={'Content-Disposition': 'attachment; filename="customer-invoice.pdf"'})
