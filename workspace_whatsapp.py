"""Signed WhatsApp intake, verified sender links and durable private receipt inbox."""
import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from workspace_expenses import receipt_bytes
from workspace_finances import VoidInput

WEBHOOK = '/enterprise-api/integrations/whatsapp/webhook'


@dataclass(frozen=True)
class WhatsAppSettings:
    secret: str = ''
    verify_token: str = ''
    access_token: str = ''
    version: str = ''
    routes: dict | None = None

    @classmethod
    def from_env(cls):
        values = [os.getenv('LOAMY_WHATSAPP_' + name, '') for name in ['APP_SECRET', 'VERIFY_TOKEN', 'ACCESS_TOKEN', 'GRAPH_VERSION', 'ROUTES']]
        if not any(values):
            return cls()
        if not all(values) or len(values[0]) < 24 or len(values[1]) < 24 or not re.fullmatch(r'v\d+\.\d+', values[3]):
            raise RuntimeError('WhatsApp requires complete secret/token/version/routes configuration')
        try:
            routes = json.loads(values[4])
            if not isinstance(routes, dict) or not routes or any(not re.fullmatch(r'\d{5,32}', k) or not isinstance(v, str) or not re.fullmatch(r'[a-f0-9]{32}', v) for k, v in routes.items()):
                raise ValueError()
        except (ValueError, TypeError):
            raise RuntimeError('WhatsApp routes must map approved phone-number IDs to business IDs')
        return cls(*values[:4], routes)


def download_media(settings, media_id, phone_id, expected_hash):
    """Fetch only from fixed Graph API and trusted Meta media host, without redirects."""
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            headers = {'Authorization': 'Bearer ' + settings.access_token}
            metadata = client.get(f'https://graph.facebook.com/{settings.version}/{media_id}', params={'phone_number_id': phone_id}, headers=headers)
            metadata.raise_for_status(); info = metadata.json()
            url = info['url']; parsed = urlsplit(url)
            # Never forward a provider token to a webhook-supplied or redirected host.
            if parsed.scheme != 'https' or parsed.hostname != 'lookaside.fbsbx.com' or parsed.port not in {None, 443} or parsed.username or parsed.password:
                raise ValueError('Untrusted media host')
            if int(info.get('file_size', 0)) > 2 * 1024 * 1024:
                raise ValueError('Receipt too large')
            chunks, size, started = [], 0, time.monotonic()
            with client.stream('GET', url, headers=headers) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(65536):
                    size += len(chunk)
                    if size > 2 * 1024 * 1024 or time.monotonic() - started > 60:
                        raise ValueError('Receipt too large')
                    chunks.append(chunk)
            raw = b''.join(chunks)
            actual = base64.b64encode(hashlib.sha256(raw).digest()).decode()
            if not hmac.compare_digest(actual, expected_hash):
                raise ValueError('Media digest mismatch')
            return receipt_bytes(base64.b64encode(raw).decode())
    except (httpx.HTTPError, ValueError, KeyError, TypeError, HTTPException):
        raise ValueError('Receipt retrieval failed. Check provider access, supported file type, size and digest.')


class PreviewMessage(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    receipt_base64: str = Field(min_length=8, max_length=2800000)
    caption: str = Field(default='', max_length=500)
    idempotency_key: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')


def install_whatsapp(app, db, verified_user, membership, audit, *, local_preview):
    settings = WhatsAppSettings.from_env()
    with db() as conn:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS whatsapp_challenges (
            token_hash TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            actor_id TEXT NOT NULL REFERENCES users(id),phone_id TEXT NOT NULL,created_at REAL NOT NULL,expires_at REAL NOT NULL,used_at REAL
          );
          CREATE TABLE IF NOT EXISTS whatsapp_senders (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            actor_id TEXT NOT NULL REFERENCES users(id),phone_id TEXT NOT NULL,sender TEXT NOT NULL,linked_at REAL NOT NULL,revoked_at REAL,
            UNIQUE(phone_id,sender)
          );
          CREATE TABLE IF NOT EXISTS whatsapp_messages (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            actor_id TEXT NOT NULL REFERENCES users(id),sender_link_id TEXT REFERENCES whatsapp_senders(id),phone_id TEXT NOT NULL,
            provider_id TEXT NOT NULL,sender TEXT NOT NULL,media_id TEXT,expected_hash TEXT,caption TEXT NOT NULL,sent_at REAL NOT NULL,received_at REAL NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('queued','ready','failed','submitted','discarded')),
            attempts INTEGER NOT NULL DEFAULT 0,lease_until REAL,receipt BLOB,mime TEXT,extension TEXT,receipt_hash TEXT,error TEXT,
            expense_id TEXT UNIQUE REFERENCES expense_submissions(id),simulated INTEGER NOT NULL DEFAULT 0,discard_reason TEXT,
            UNIQUE(phone_id,provider_id)
          );
          CREATE INDEX IF NOT EXISTS whatsapp_message_queue ON whatsapp_messages(status,lease_until);
          CREATE INDEX IF NOT EXISTS whatsapp_message_actor ON whatsapp_messages(business_id,location_id,actor_id,received_at);
        ''')
    base = '/enterprise-api/businesses/{business_id}/locations/{location_id}/whatsapp'

    def scope(conn, bid, lid, actor):
        member = membership(conn, bid, actor)
        if member['role'] != 'owner' and member['location_id'] != lid:
            raise HTTPException(404, 'Location not found')
        if not conn.execute('SELECT id FROM locations WHERE id=? AND business_id=?', (lid, bid)).fetchone():
            raise HTTPException(404, 'Location not found')

    def current_actor(conn, uid, bid, lid):
        actor = conn.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        if not actor or not actor['email_verified_at'] or (not local_preview and actor['verification_method'] != 'smtp'):
            raise HTTPException(403, 'Verified staff account is required')
        scope(conn, bid, lid, actor)
        return actor

    @app.get(base)
    def inbox(business_id: str, location_id: str, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, location_id, actor)
            messages = [dict(row) for row in conn.execute('SELECT id,caption,status,error,received_at,sent_at,expense_id,simulated FROM whatsapp_messages WHERE business_id=? AND location_id=? AND actor_id=? ORDER BY received_at DESC LIMIT 50', (business_id, location_id, actor['id']))]
            links = [dict(row) for row in conn.execute('SELECT id,phone_id,sender,revoked_at FROM whatsapp_senders WHERE business_id=? AND location_id=? AND actor_id=? ORDER BY linked_at', (business_id, location_id, actor['id']))]
            return {'messages': messages, 'links': links, 'phone_ids': [pid for pid, bid in (settings.routes or {}).items() if bid == business_id], 'live_configured': bool(settings.secret), 'local_preview': local_preview, 'groups_supported': False}

    @app.post(base + '/link-code')
    def link_code(business_id: str, location_id: str, data: dict, actor=Depends(verified_user)):
        pid = data.get('phone_id', '')
        if not isinstance(pid, str) or (settings.routes or {}).get(pid) != business_id:
            raise HTTPException(422, 'Choose the business number configured by the operator')
        token = secrets.token_urlsafe(24); now = time.time()
        with db() as conn:
            scope(conn, business_id, location_id, actor)
            if conn.execute('SELECT count(*) FROM whatsapp_challenges WHERE actor_id=? AND created_at>?', (actor['id'], now - 3600)).fetchone()[0] >= 10:
                raise HTTPException(429, 'Too many linking requests. Try again later.')
            conn.execute('UPDATE whatsapp_challenges SET used_at=? WHERE actor_id=? AND business_id=? AND used_at IS NULL', (now, actor['id'], business_id))
            conn.execute('INSERT INTO whatsapp_challenges VALUES (?,?,?,?,?,?,?,NULL)', (hashlib.sha256(token.encode()).hexdigest(), business_id, location_id, actor['id'], pid, now, now + 600))
        return {'message': 'LINK ' + token, 'expires_in': 600, 'phone_id': pid}

    @app.post(base + '/links/{link_id}/revoke')
    def revoke(business_id: str, location_id: str, link_id: str, data: VoidInput, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, location_id, actor)
            link = conn.execute('SELECT * FROM whatsapp_senders WHERE id=? AND business_id=? AND location_id=?', (link_id, business_id, location_id)).fetchone()
            if not link or (link['actor_id'] != actor['id'] and membership(conn, business_id, actor)['role'] != 'owner'):
                raise HTTPException(404, 'Sender link not found')
            conn.execute('UPDATE whatsapp_senders SET revoked_at=? WHERE id=? AND revoked_at IS NULL', (time.time(), link_id))
            audit(conn, business_id, actor['id'], f'Revoked WhatsApp sender link {link_id}: {data.reason}')
        return {'success': True}

    @app.get(WEBHOOK)
    def handshake(request: Request):
        if not settings.secret:
            raise HTTPException(503, 'WhatsApp integration is not configured')
        params = request.query_params
        challenge = params.get('hub.challenge', '')
        if params.get('hub.mode') != 'subscribe' or not hmac.compare_digest(params.get('hub.verify_token', ''), settings.verify_token) or not re.fullmatch(r'\d{1,100}', challenge):
            raise HTTPException(403, 'Invalid verification request')
        return Response(challenge, media_type='text/plain')

    def accept_message(conn, bid, pid, message):
        # Group context is intentionally refused; never infer identity from a display name.
        sender = message.get('from', ''); mid = message.get('id', '')
        if not isinstance(sender, str) or not re.fullmatch(r'\d{6,20}', sender) or not isinstance(mid, str) or not 1 <= len(mid) <= 200 or message.get('group_id') or message.get('context', {}).get('group_id'):
            return
        if message.get('type') == 'text':
            body = message.get('text', {}).get('body', '')
            match = re.fullmatch(r'LINK ([A-Za-z0-9_-]{32})', body) if isinstance(body, str) else None
            if not match:
                return
            code = conn.execute('SELECT * FROM whatsapp_challenges WHERE token_hash=? AND business_id=? AND phone_id=? AND used_at IS NULL AND expires_at>?', (hashlib.sha256(match[1].encode()).hexdigest(), bid, pid, time.time())).fetchone()
            if not code:
                return
            try:
                current_actor(conn, code['actor_id'], bid, code['location_id'])
            except HTTPException:
                return
            old = conn.execute('SELECT * FROM whatsapp_senders WHERE phone_id=? AND sender=?', (pid, sender)).fetchone()
            if old and old['revoked_at'] is None and old['actor_id'] != code['actor_id']:
                return
            if old:
                conn.execute('UPDATE whatsapp_senders SET actor_id=?,location_id=?,linked_at=?,revoked_at=NULL WHERE id=?', (code['actor_id'], code['location_id'], time.time(), old['id']))
            else:
                conn.execute('INSERT INTO whatsapp_senders VALUES (?,?,?,?,?,?,?,NULL)', (secrets.token_hex(16), bid, code['location_id'], code['actor_id'], pid, sender, time.time()))
            conn.execute('UPDATE whatsapp_challenges SET used_at=? WHERE token_hash=?', (time.time(), code['token_hash']))
            audit(conn, bid, code['actor_id'], 'Linked a WhatsApp sender using a one-time account challenge')
            return
        if message.get('type') not in {'image', 'document'}:
            return
        media = message.get(message['type'], {})
        if not isinstance(media, dict) or media.get('mime_type') not in {'image/jpeg', 'image/png', 'application/pdf'}:
            return
        media_id = media.get('id', ''); expected = media.get('sha256', '')
        if not isinstance(media_id, str) or not re.fullmatch(r'\d{1,100}', media_id) or not isinstance(expected, str) or not re.fullmatch(r'[A-Za-z0-9+/]{43}=', expected):
            return
        linked = conn.execute('SELECT * FROM whatsapp_senders WHERE phone_id=? AND sender=? AND revoked_at IS NULL', (pid, sender)).fetchone()
        if not linked or linked['business_id'] != bid:
            return
        try:
            current_actor(conn, linked['actor_id'], bid, linked['location_id'])
            sent_at = float(message.get('timestamp', 0))
            if not time.time() - 7 * 86400 <= sent_at <= time.time() + 300 or sent_at < linked['linked_at'] - 1:
                return
        except (HTTPException, TypeError, ValueError):
            return
        if conn.execute('SELECT id FROM whatsapp_messages WHERE phone_id=? AND provider_id=?', (pid, mid)).fetchone():
            return
        # Bound storage per staff sender; provider retries are deduplicated before this limit.
        if conn.execute('SELECT count(*) FROM whatsapp_messages WHERE actor_id=? AND received_at>?', (linked['actor_id'], time.time() - 3600)).fetchone()[0] >= 30:
            raise HTTPException(429, 'Staff receipt intake limit reached; retry later')
        caption = media.get('caption', '')
        if not isinstance(caption, str):
            caption = ''
        conn.execute('INSERT INTO whatsapp_messages (id,business_id,location_id,actor_id,sender_link_id,phone_id,provider_id,sender,media_id,expected_hash,caption,sent_at,received_at,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (secrets.token_hex(16), bid, linked['location_id'], linked['actor_id'], linked['id'], pid, mid, sender, media_id, expected, caption[:500], sent_at, time.time(), 'queued'))

    @app.post(WEBHOOK)
    async def webhook(request: Request):
        if not settings.secret:
            raise HTTPException(503, 'WhatsApp integration is not configured')
        raw = await request.body()
        expected = 'sha256=' + hmac.new(settings.secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(request.headers.get('x-hub-signature-256', ''), expected):
            raise HTTPException(401, 'Invalid webhook signature')
        try:
            payload = json.loads(raw)
            if payload.get('object') != 'whatsapp_business_account' or not isinstance(payload.get('entry'), list):
                raise ValueError()
            with db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                for entry in payload['entry']:
                    for change in entry.get('changes', []):
                        value = change.get('value', {})
                        if change.get('field') != 'messages' or value.get('messaging_product') != 'whatsapp' or value.get('group_id'):
                            continue
                        pid = value.get('metadata', {}).get('phone_number_id', '')
                        bid = (settings.routes or {}).get(pid)
                        if bid:
                            if hasattr(app.state,'whatsapp_delivery_status'):
                                app.state.whatsapp_delivery_status(conn,pid,value.get('statuses',[]))
                            for message in value.get('messages', []):
                                accept_message(conn, bid, pid, message)
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(422, 'Invalid WhatsApp event format')
        return {'received': True}

    def process_one():
        if not settings.secret:
            return False
        now = time.time()
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute("UPDATE whatsapp_messages SET status='failed',error='Receipt retrieval was interrupted too often; upload manually.' WHERE status='queued' AND attempts>=5 AND lease_until<?", (now,))
            row = conn.execute("SELECT * FROM whatsapp_messages WHERE status='queued' AND (lease_until IS NULL OR lease_until<?) AND attempts<5 ORDER BY received_at LIMIT 1", (now,)).fetchone()
            if not row:
                return False
            conn.execute('UPDATE whatsapp_messages SET lease_until=?,attempts=attempts+1 WHERE id=?', (now + 180, row['id']))
        try:
            with db() as conn:
                current_actor(conn, row['actor_id'], row['business_id'], row['location_id'])
                link = conn.execute('SELECT * FROM whatsapp_senders WHERE id=? AND revoked_at IS NULL AND actor_id=?', (row['sender_link_id'], row['actor_id'])).fetchone()
                if not link or link['location_id'] != row['location_id'] or (settings.routes or {}).get(row['phone_id']) != row['business_id']:
                    raise HTTPException(403, 'Sender access changed')
            raw, mime, extension = download_media(settings, row['media_id'], row['phone_id'], row['expected_hash'])
            with db() as conn:
                current_actor(conn, row['actor_id'], row['business_id'], row['location_id'])
                link = conn.execute('SELECT id FROM whatsapp_senders WHERE id=? AND actor_id=? AND location_id=? AND revoked_at IS NULL', (row['sender_link_id'], row['actor_id'], row['location_id'])).fetchone()
                if not link:
                    raise HTTPException(403, 'Sender access changed')
                conn.execute("UPDATE whatsapp_messages SET receipt=?,mime=?,extension=?,receipt_hash=?,status='ready',lease_until=NULL,error=NULL WHERE id=? AND status='queued'", (raw, mime, extension, hashlib.sha256(raw).hexdigest(), row['id']))
        except (ValueError, HTTPException):
            with db() as conn:
                conn.execute("UPDATE whatsapp_messages SET status='failed',lease_until=NULL,error=? WHERE id=? AND status='queued'", ('Receipt could not be retrieved or sender access changed. Check your link, then retry or upload manually.', row['id']))
        return True

    app.state.process_whatsapp_message = process_one
    app.state.whatsapp_enabled = bool(settings.secret)

    def own_message(conn, bid, lid, mid, actor):
        scope(conn, bid, lid, actor)
        row = conn.execute('SELECT * FROM whatsapp_messages WHERE id=? AND business_id=? AND location_id=? AND actor_id=?', (mid, bid, lid, actor['id'])).fetchone()
        if not row:
            raise HTTPException(404, 'Receipt message not found')
        return row

    @app.get(base + '/messages/{message_id}/draft')
    def draft(business_id: str, location_id: str, message_id: str, actor=Depends(verified_user)):
        with db() as conn:
            row = own_message(conn, business_id, location_id, message_id, actor)
            if row['status'] != 'ready':
                raise HTTPException(409, 'Receipt is not ready or has already been submitted')
            return {'id': row['id'], 'receipt_base64': base64.b64encode(row['receipt']).decode(), 'caption': row['caption'], 'simulated': bool(row['simulated'])}

    @app.post(base + '/messages/{message_id}/retry')
    def retry(business_id: str, location_id: str, message_id: str, actor=Depends(verified_user)):
        with db() as conn:
            row = own_message(conn, business_id, location_id, message_id, actor)
            if row['status'] != 'failed' or row['attempts'] >= 5:
                raise HTTPException(409, 'This message cannot be retried. Upload the receipt manually instead.')
            conn.execute("UPDATE whatsapp_messages SET status='queued',lease_until=NULL,error=NULL WHERE id=?", (message_id,))
        return {'success': True}

    @app.get(base + '/messages/{message_id}/receipt')
    def original_receipt(business_id: str, location_id: str, message_id: str, actor=Depends(verified_user)):
        with db() as conn:
            row = own_message(conn, business_id, location_id, message_id, actor)
            if not row['receipt']:
                raise HTTPException(409, 'Receipt file has not been retrieved')
            return Response(content=row['receipt'], media_type='application/octet-stream', headers={'Content-Disposition': f'attachment; filename="whatsapp-receipt-{message_id}.{row["extension"]}"', 'Content-Security-Policy': "default-src 'none'; sandbox"})

    @app.post(base + '/messages/{message_id}/discard')
    def discard(business_id: str, location_id: str, message_id: str, data: VoidInput, actor=Depends(verified_user)):
        with db() as conn:
            row = own_message(conn, business_id, location_id, message_id, actor)
            if row['status'] == 'submitted':
                raise HTTPException(409, 'Use the submitted expense history for this receipt')
            conn.execute("UPDATE whatsapp_messages SET status='discarded',discard_reason=? WHERE id=?", (data.reason, message_id))
        return {'success': True}

    @app.post(base + '/preview-message', status_code=201)
    def simulate(business_id: str, location_id: str, data: PreviewMessage, actor=Depends(verified_user)):
        if not local_preview:
            raise HTTPException(404, 'Not found')
        with db() as conn:
            scope(conn, business_id, location_id, actor)
        raw, mime, extension = receipt_bytes(data.receipt_base64)
        phone = 'preview-' + actor['id']; digest = hashlib.sha256(raw).hexdigest()
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE'); scope(conn, business_id, location_id, actor)
            previous = conn.execute('SELECT id,receipt_hash,caption,business_id,location_id FROM whatsapp_messages WHERE phone_id=? AND provider_id=?', (phone, data.idempotency_key)).fetchone()
            if previous:
                if (previous['receipt_hash'], previous['caption'], previous['business_id'], previous['location_id']) != (digest, data.caption, business_id, location_id):
                    raise HTTPException(409, 'Simulation reference already identifies another receipt')
                return {'id': previous['id'], 'duplicate': True}
            mid = secrets.token_hex(16)
            conn.execute('INSERT INTO whatsapp_messages (id,business_id,location_id,actor_id,phone_id,provider_id,sender,caption,sent_at,received_at,status,receipt,mime,extension,receipt_hash,simulated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)',
                (mid, business_id, location_id, actor['id'], phone, data.idempotency_key, 'fictional-sender', data.caption, time.time(), time.time(), 'ready', raw, mime, extension, digest))
        return {'id': mid, 'duplicate': False}
