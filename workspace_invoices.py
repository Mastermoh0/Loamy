"""Immutable invoice snapshots/PDFs and explicit, deduplicated local or SMTP delivery."""
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import smtplib
import time

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
import reportlab
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from workspace_email import send_smtp
from workspace_finances import money
from workspace_payments import payment_summary
from workspace_pricing import order_pricing
from workspace_contacts import contacts_for


class IssueInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    due_on: date | None = None

class DeliveryInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    recipient: str = Field(min_length=5, max_length=254)
    idempotency_key: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')

    @field_validator('recipient')
    @classmethod
    def single_address(cls, value):
        if value.count('@') != 1 or any(c.isspace() or c in ',;<>:"()\\' for c in value) or '.' not in value.split('@')[1]:
            raise ValueError('Enter one customer email address')
        return value


FONT_DIR = Path(reportlab.__file__).parent / 'fonts'
pdfmetrics.registerFont(TTFont('InvoiceSans', FONT_DIR / 'Vera.ttf'))
pdfmetrics.registerFont(TTFont('InvoiceBold', FONT_DIR / 'VeraBd.ttf'))


def render_invoice(snapshot, cancelled=False):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(595.28, 841.89), leftMargin=42, rightMargin=42,
                            topMargin=42, bottomMargin=48, title=snapshot['number'], author='Loamy')
    text = ParagraphStyle('InvoiceText', fontName='InvoiceSans', fontSize=9, leading=14, spaceAfter=10, wordWrap='CJK')
    title = ParagraphStyle('InvoiceTitle', parent=text, fontName='InvoiceBold', fontSize=21, leading=27, textColor=colors.HexColor('#174c20'), spaceAfter=18)
    bold = ParagraphStyle('InvoiceLabel', parent=text, fontName='InvoiceBold')
    def p(value, style=text):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)
    story = [p('CANCELLED INVOICE' if cancelled else 'INVOICE', title), p(snapshot['profile']['invoice_name'], bold),
             p(snapshot['location_name'] + '\n' + snapshot['profile']['address']),
             p('Invoice: ' + snapshot['number'] + '\nVersion: 1\nOrder reference: ' + snapshot['order_reference']),
             p('Issued: ' + snapshot['issued_on'] + '\nDue: ' + (snapshot['due_on'] or 'Not specified')),
             p('Bill to', bold), p(snapshot['customer_name'] + '\n' + snapshot['customer_contact']), Spacer(1, 10)]
    rows = [[p('Description', bold), p('Qty', bold), p('Unit (NGN)', bold), p('Total (NGN)', bold)]]
    for line in snapshot['lines']:
        rows.append([p(line['name'] + ('\n' + line['description'] if line['description'] else '')),
                     p(line['quantity']), p(line['unit_price']), p(line['total'])])
    table = Table(rows, colWidths=[263, 40, 100, 108], repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e9edde')),
                              ('LINEBELOW', (0, 0), (-1, -1), .5, colors.HexColor('#d5d9cc')),
                              ('TOPPADDING', (0, 0), (-1, -1), 9), ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
    story.extend([table, Spacer(1, 20)])
    pricing = snapshot.get('pricing')
    if pricing:
        story.extend([p('Subtotal: NGN ' + pricing['subtotal']),
                      p('Discount: NGN ' + pricing['discount'] + (' (' + pricing['discount_reason'] + ')' if pricing['discount_reason'] else '')),
                      p(pricing['tax_label'] + ' (' + pricing['tax_rate'] + '%): NGN ' + pricing['tax'])])
    story.extend([p('TOTAL: NGN ' + snapshot['total'], title),
                  p('Cancelled - do not pay this invoice.' if cancelled else 'Issued invoice - not a receipt. Check Loamy for the current payment balance.', bold)])
    if snapshot['profile']['payment_instructions']:
        story.extend([p('Payment instructions', bold), p(snapshot['profile']['payment_instructions']), p('Include order reference: ' + snapshot['order_reference'])])
    def footer(canvas, document):
        canvas.setFont('InvoiceSans', 7)
        canvas.setFillColor(colors.HexColor('#62685d'))
        canvas.drawString(42, 26, ('Loamy local preview - ' if snapshot.get('local_preview', True) else 'Loamy - ') + snapshot['number'])
        canvas.drawRightString(553, 26, f'Page {document.page}')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def install_invoices(app, db, verified_user, scope, audit, transport, local_preview=True):
    with db() as conn:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS invoices (
            id TEXT PRIMARY KEY, order_id TEXT NOT NULL UNIQUE REFERENCES orders(id), number TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('issued','cancelled')), issued_at REAL NOT NULL,
            issued_by TEXT NOT NULL REFERENCES users(id), due_on TEXT, snapshot TEXT NOT NULL, pdf BLOB NOT NULL
          );
          CREATE TABLE IF NOT EXISTS invoice_deliveries (
            id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES invoices(id), actor_id TEXT NOT NULL REFERENCES users(id),
            recipient TEXT NOT NULL, transport TEXT NOT NULL, status TEXT NOT NULL,
            created_at REAL NOT NULL, updated_at REAL NOT NULL, idempotency_key TEXT NOT NULL,
            subject TEXT NOT NULL, body TEXT NOT NULL, UNIQUE(invoice_id,idempotency_key)
          );
        ''')

    base = '/enterprise-api/businesses/{business_id}/locations/{location_id}/orders/{order_id}/invoice'

    def load_order(conn, bid, lid, oid, actor, write=False):
        scope(conn, bid, lid, actor, write=write)
        order = conn.execute('SELECT o.*,l.name location_name FROM orders o JOIN locations l ON l.id=o.location_id WHERE o.id=? AND o.business_id=? AND o.location_id=?', (oid, bid, lid)).fetchone()
        if not order:
            raise HTTPException(404, 'Order not found')
        return order

    def invoice_row(conn, oid):
        row = conn.execute('SELECT * FROM invoices WHERE order_id=?', (oid,)).fetchone()
        if not row:
            raise HTTPException(404, 'Generate an invoice for this order first')
        return row

    def public_invoice(conn, row):
        # A process interruption cannot establish whether an SMTP server accepted the message.
        conn.execute("UPDATE invoice_deliveries SET status='unknown',updated_at=? WHERE invoice_id=? AND status='sending' AND created_at<?",
                     (time.time(), row['id'], time.time() - 120))
        deliveries = conn.execute('SELECT id,recipient,transport,status,created_at,updated_at,subject,body FROM invoice_deliveries WHERE invoice_id=? ORDER BY created_at DESC LIMIT 20', (row['id'],)).fetchall()
        payments = payment_summary(conn, row)
        return {'id': row['id'], 'number': row['number'], 'status': row['status'], 'payment_status': payments['status'], 'payments': payments,
                'version': 1, 'issued_at': row['issued_at'], 'due_on': row['due_on'], 'snapshot': json.loads(row['snapshot']),
                'mail_transport': transport, 'deliveries': [dict(item) for item in deliveries]}

    @app.get(base)
    def get_invoice(business_id: str, location_id: str, order_id: str, actor=Depends(verified_user)):
        with db() as conn:
            load_order(conn, business_id, location_id, order_id, actor)
            row = conn.execute('SELECT * FROM invoices WHERE order_id=?', (order_id,)).fetchone()
            return {'invoice': public_invoice(conn, row) if row else None}

    @app.post(base, status_code=201)
    def issue_invoice(business_id: str, location_id: str, order_id: str, data: IssueInput, actor=Depends(verified_user)):
        due = data.due_on.isoformat() if data.due_on else None
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            order = load_order(conn, business_id, location_id, order_id, actor, write=True)
            existing = conn.execute('SELECT * FROM invoices WHERE order_id=?', (order_id,)).fetchone()
            if existing:
                if existing['due_on'] != due:
                    raise HTTPException(409, 'This order already has an invoice. Its issued due date cannot be changed.')
                return {'invoice': public_invoice(conn, existing), 'duplicate': True}
            if order['status'] != 'open':
                raise HTTPException(409, 'Cancelled orders cannot be invoiced')
            if data.due_on and data.due_on < datetime.now(timezone(timedelta(hours=1))).date():
                raise HTTPException(422, 'Choose today or a future due date')
            now = time.time()
            number = 'INV-' + datetime.now(timezone(timedelta(hours=1))).strftime('%Y%m%d') + '-' + order_id.upper()
            snapshot = {'number': number, 'order_reference': order['reference'], 'location_name': order['location_name'], 'local_preview': local_preview,
                        'profile': json.loads(order['profile_snapshot']), 'customer_name': order['customer_name'], 'customer_contact': order['customer_contact'],
                        'total': money(order['total_minor']), 'contacts': contacts_for(conn, order_id, order['customer_contact']), 'pricing': order_pricing(conn, order_id, order['total_minor']), 'currency': 'NGN', 'due_on': due,
                        'issued_on': datetime.fromtimestamp(now, timezone(timedelta(hours=1))).date().isoformat(),
                        'lines': [{'name': line['name'], 'description': line['description'], 'quantity': line['quantity'],
                                   'unit_price': money(line['unit_minor']), 'total': money(line['unit_minor'] * line['quantity'])}
                                  for line in conn.execute('SELECT * FROM order_lines WHERE order_id=? ORDER BY position', (order_id,))]}
            conn.execute('INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?)', (secrets.token_hex(16), order_id, number, 'issued', now, actor['id'], due, json.dumps(snapshot), render_invoice(snapshot)))
            audit(conn, business_id, actor['id'], f'Issued invoice {number} for order {order["reference"]}')
            return {'invoice': public_invoice(conn, invoice_row(conn, order_id)), 'duplicate': False}

    @app.get(base + '/pdf')
    def download_invoice(business_id: str, location_id: str, order_id: str, actor=Depends(verified_user)):
        with db() as conn:
            load_order(conn, business_id, location_id, order_id, actor)
            row = invoice_row(conn, order_id)
            pdf = render_invoice(json.loads(row['snapshot']), cancelled=True) if row['status'] == 'cancelled' else row['pdf']
        return Response(content=pdf, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{row["number"]}.pdf"'})

    @app.get(base + '/email/{delivery_id}/attachment')
    def captured_attachment(business_id: str, location_id: str, order_id: str, delivery_id: str, actor=Depends(verified_user)):
        with db() as conn:
            load_order(conn, business_id, location_id, order_id, actor)
            invoice = invoice_row(conn, order_id)
            delivery = conn.execute("SELECT id FROM invoice_deliveries WHERE id=? AND invoice_id=? AND transport='capture'", (delivery_id, invoice['id'])).fetchone()
            if not delivery:
                raise HTTPException(404, 'Captured email not found')
        return Response(content=invoice['pdf'], media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{invoice["number"]}-as-issued.pdf"'})

    @app.post(base + '/email')
    def email_invoice(business_id: str, location_id: str, order_id: str, data: DeliveryInput, actor=Depends(verified_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            order = load_order(conn, business_id, location_id, order_id, actor, write=True)
            invoice = invoice_row(conn, order_id)
            existing = conn.execute('SELECT * FROM invoice_deliveries WHERE invoice_id=? AND idempotency_key=?', (invoice['id'], data.idempotency_key)).fetchone()
            if existing:
                if existing['recipient'] != data.recipient or existing['actor_id'] != actor['id']:
                    raise HTTPException(409, 'This email reference was already used for a different request')
                return {'delivery_id': existing['id'], 'status': existing['status'], 'duplicate': True}
            if invoice['status'] != 'issued' or order['status'] != 'open':
                raise HTTPException(409, 'Cancelled invoices cannot be emailed')
            if conn.execute("SELECT id FROM invoice_deliveries WHERE invoice_id=? AND created_at>?", (invoice['id'], time.time() - 60)).fetchone():
                raise HTTPException(429, 'Wait one minute before sending another copy of this invoice')
            if conn.execute("SELECT count(*) FROM invoice_deliveries WHERE actor_id=? AND created_at>?", (actor['id'], time.time() - 3600)).fetchone()[0] >= 30:
                raise HTTPException(429, 'Hourly invoice email limit reached. Try again later.')
            snapshot = json.loads(invoice['snapshot'])
            subject = f'Invoice {invoice["number"]} - ' + ' '.join(snapshot['profile']['invoice_name'].split())
            body = f'Hello {snapshot["customer_name"]},\n\nYour invoice from {snapshot["profile"]["invoice_name"]} is attached.\nInvoice: {invoice["number"]}\nOrder reference: {snapshot["order_reference"]}\nTotal: NGN {snapshot["total"]}\nDue: {snapshot["due_on"] or "Not specified"}\n\n{snapshot["profile"]["payment_instructions"]}\n\nThis invoice is not a receipt. Check the current payment balance with the business. This is a Loamy local preview invoice.'
            if not local_preview:
                body = body.removesuffix(' This is a Loamy local preview invoice.')
            did, now = secrets.token_hex(16), time.time()
            conn.execute('INSERT INTO invoice_deliveries VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                         (did, invoice['id'], actor['id'], data.recipient, transport, 'captured' if transport == 'capture' else 'sending', now, now,
                          data.idempotency_key, subject, body if transport == 'capture' else ''))
            audit(conn, business_id, actor['id'], f'Requested invoice email {did} for {invoice["number"]}')
        status = 'captured'
        if transport == 'smtp':
            try:
                message = EmailMessage()
                message['From'] = os.environ['LOAMY_SMTP_FROM']
                message['To'] = data.recipient
                message['Subject'] = subject
                message['Message-ID'] = f'<loamy-invoice-{did}@localhost>'
                message.set_content(body)
                message.add_attachment(invoice['pdf'], maintype='application', subtype='pdf', filename=invoice['number'] + '.pdf')
                send_smtp(message)
                status = 'accepted'
            except (KeyError, ValueError, smtplib.SMTPRecipientsRefused, smtplib.SMTPAuthenticationError):
                status = 'failed'
            except (OSError, smtplib.SMTPException):
                status = 'unknown'
            with db() as conn:
                conn.execute('UPDATE invoice_deliveries SET status=?,updated_at=? WHERE id=?', (status, time.time(), did))
                audit(conn, business_id, actor['id'], f'Invoice email {did}: {status}')
        return {'delivery_id': did, 'status': status, 'duplicate': False}
