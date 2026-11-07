"""Verification with a private local mail capture or configured TLS SMTP delivery."""
import hashlib
import os
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field


def send_smtp(message):
    """Shared TLS transport; callers retain their own delivery histories."""
    mode = os.getenv('LOAMY_SMTP_SECURITY', 'starttls')
    if mode not in {'starttls', 'ssl'}:
        raise ValueError('SMTP must use starttls or ssl')
    client = smtplib.SMTP_SSL if mode == 'ssl' else smtplib.SMTP
    with client(os.environ['LOAMY_SMTP_HOST'], int(os.getenv('LOAMY_SMTP_PORT', '465' if mode == 'ssl' else '587')),
                timeout=15, **({'context': ssl.create_default_context()} if mode == 'ssl' else {})) as smtp:
        if mode == 'starttls':
            smtp.starttls(context=ssl.create_default_context())
        smtp.login(os.environ['LOAMY_SMTP_USERNAME'], os.environ['LOAMY_SMTP_PASSWORD'])
        refused = smtp.send_message(message)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)


class VerificationToken(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=20, max_length=200)


class EmailVerification:
    def __init__(self, db, web_origin='http://127.0.0.1:5173'):
        self.db = db
        self.web_origin = web_origin
        self.transport = os.getenv('LOAMY_MAIL_TRANSPORT', 'capture')
        if self.transport not in {'capture', 'smtp'}:
            raise RuntimeError('LOAMY_MAIL_TRANSPORT must be capture or smtp')
        with db() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS email_verifications (
                  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                  expires_at REAL NOT NULL, consumed_at REAL, created_at REAL NOT NULL, method TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mail_outbox (
                  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), recipient TEXT NOT NULL,
                  subject TEXT NOT NULL, body TEXT NOT NULL, verification_url TEXT NOT NULL,
                  created_at REAL NOT NULL, transport TEXT NOT NULL, status TEXT NOT NULL
                );
            ''')

    def is_verified(self, actor):
        return bool(actor['email_verified_at'] and (self.transport == 'capture' or actor['verification_method'] == 'smtp'))

    def queue(self, conn, actor):
        now = time.time()
        recent = conn.execute('SELECT max(created_at) FROM email_verifications WHERE user_id=?', (actor['id'],)).fetchone()[0]
        if recent and now - recent < 60:
            raise HTTPException(429, 'Wait one minute before requesting another verification email')
        token = secrets.token_urlsafe(32)
        conn.execute('UPDATE email_verifications SET expires_at=0 WHERE user_id=? AND consumed_at IS NULL', (actor['id'],))
        conn.execute('INSERT INTO email_verifications VALUES (?,?,?,NULL,?,?)',
                     (hashlib.sha256(token.encode()).hexdigest(), actor['id'], now + 1800, now, self.transport))
        # A fixed loopback origin avoids trusting a caller-controlled Host header.
        url = f'{self.web_origin}/business#verify={token}'
        body = f"Verify the email for your Loamy business account:\n\n{url}\n\nThis link expires in 30 minutes and works once. Sign in with {actor['email']} to confirm it."
        mid = secrets.token_hex(16)
        conn.execute('INSERT INTO mail_outbox VALUES (?,?,?,?,?,?,?,?,?)',
                     (mid, actor['id'], actor['email'], 'Verify your Loamy email', body if self.transport == 'capture' else '',
                      url if self.transport == 'capture' else '', now, self.transport,
                      'captured' if self.transport == 'capture' else 'pending'))
        return {'id': mid, 'recipient': actor['email'], 'body': body}

    def deliver(self, queued):
        if self.transport == 'capture':
            return 'captured'
        try:
            message = EmailMessage()
            message['From'] = os.environ['LOAMY_SMTP_FROM']
            message['To'] = queued['recipient']
            message['Subject'] = 'Verify your Loamy email'
            message.set_content(queued['body'])
            send_smtp(message)
            status = 'sent'
        except (OSError, smtplib.SMTPException, ValueError, KeyError):
            status = 'failed'
        with self.db() as conn:
            conn.execute('UPDATE mail_outbox SET status=? WHERE id=?', (status, queued['id']))
        return status

    def install(self, app, user, start_session):
        @app.post('/enterprise-api/email/request')
        def request_verification(actor=Depends(user)):
            if self.is_verified(actor):
                return {'status': 'already_verified'}
            with self.db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                queued = self.queue(conn, actor)
            status = self.deliver(queued)
            if status == 'failed':
                raise HTTPException(503, 'Email delivery failed. Check SMTP settings and request a new link.')
            return {'status': status}

        @app.get('/enterprise-api/email/inbox')
        def local_inbox(actor=Depends(user)):
            if self.transport != 'capture':
                raise HTTPException(404, 'Local inbox is disabled for delivered email')
            with self.db() as conn:
                rows = conn.execute('SELECT id,recipient,subject,body,verification_url,created_at FROM mail_outbox WHERE user_id=? AND transport=? ORDER BY created_at DESC LIMIT 5',
                                    (actor['id'], 'capture')).fetchall()
            return {'messages': [dict(r) for r in rows], 'simulated': True}

        @app.post('/enterprise-api/email/verify')
        def verify_email(data: VerificationToken, response: Response, actor=Depends(user)):
            hashed = hashlib.sha256(data.token.encode()).hexdigest()
            with self.db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                row = conn.execute('SELECT * FROM email_verifications WHERE token_hash=? AND consumed_at IS NULL AND expires_at>?', (hashed, time.time())).fetchone()
                if not row:
                    raise HTTPException(400, 'This verification link has expired or has already been used. Request another email.')
                if row['user_id'] != actor['id']:
                    raise HTTPException(403, 'Sign in with the account this verification email was sent to')
                if row['method'] != self.transport:
                    raise HTTPException(400, 'Delivery settings changed. Request a new verification email.')
                conn.execute('UPDATE email_verifications SET consumed_at=? WHERE token_hash=?', (time.time(), hashed))
                conn.execute('UPDATE users SET email_verified_at=?,verification_method=? WHERE id=?', (time.time(), self.transport, actor['id']))
                # Rotate all pre-verification sessions rather than upgrading them silently.
                conn.execute('DELETE FROM sessions WHERE user_id=?', (actor['id'],))
                start_session(conn, actor['id'], response)
            return {'verified': True, 'method': self.transport, 'simulated': self.transport == 'capture'}
