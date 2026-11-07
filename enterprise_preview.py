"""Isolated, persistent local implementation of the business/locations feature.

Run with: python -m uvicorn enterprise_preview:create_app --factory --port 8001
Requires LOAMY_LOCAL_PREVIEW=1. Never imports the legacy production/Gmail app.
"""
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

from workspace_email import EmailVerification
from workspace_finances import install_finances
from workspace_orders import install_orders
from workspace_payments import install_payments
from workspace_expenses import install_expenses

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

ROLES = {"owner", "manager", "finance", "front_desk", "staff"}
COOKIE = "loamy_workspace_session"
SESSION_SECONDS = 8 * 60 * 60
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, salt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS businesses (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS locations (
 id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id),
 name TEXT NOT NULL, address TEXT NOT NULL, created_at REAL NOT NULL,
 UNIQUE(business_id, name)
);
CREATE TABLE IF NOT EXISTS memberships (
 id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id),
 user_id TEXT NOT NULL REFERENCES users(id), role TEXT NOT NULL
 CHECK(role IN ('owner','manager','finance','front_desk','staff')),
 location_id TEXT REFERENCES locations(id), UNIQUE(business_id,user_id),
 CHECK ((role='owner' AND location_id IS NULL) OR (role!='owner' AND location_id IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS invitations (
 id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE,
 business_id TEXT NOT NULL REFERENCES businesses(id), email TEXT NOT NULL,
 role TEXT NOT NULL, location_id TEXT NOT NULL REFERENCES locations(id),
 expires_at REAL NOT NULL, accepted_at REAL
);
CREATE TABLE IF NOT EXISTS audit_events (
 id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id),
 actor_id TEXT NOT NULL REFERENCES users(id), action TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS login_attempts (key TEXT NOT NULL, created_at REAL NOT NULL);
"""


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(Input):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("password", mode="before")
    @classmethod
    def preserve_password(cls, value):
        # Config trims normal fields; reject invisible boundary changes to passwords.
        if isinstance(value, str) and value != value.strip():
            raise ValueError("Password must not start or end with spaces")
        return value

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        value = value.casefold()
        if value.count("@") != 1 or " " in value or "." not in value.split("@")[1]:
            raise ValueError("Enter a valid email address")
        return value


class Registration(Credentials):
    name: str = Field(min_length=2, max_length=100)


class BusinessInput(Input):
    name: str = Field(min_length=2, max_length=100)
    location_name: str = Field(min_length=2, max_length=100)
    address: str = Field(min_length=2, max_length=240)


class LocationInput(Input):
    name: str = Field(min_length=2, max_length=100)
    address: str = Field(min_length=2, max_length=240)


class InvitationInput(Input):
    email: str = Field(min_length=5, max_length=254)
    role: str
    location_id: str

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        return Credentials.email_address(value)

    @field_validator("role")
    @classmethod
    def staff_role(cls, value):
        if value not in ROLES - {"owner"}:
            raise ValueError("Choose a team role")
        return value


class AcceptInput(Input):
    token: str = Field(min_length=20, max_length=200)


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_app(database_path=None, *, production_settings=None):
    production = production_settings is not None
    if not production and os.getenv("LOAMY_LOCAL_PREVIEW") != "1":
        raise RuntimeError("This local workspace API requires LOAMY_LOCAL_PREVIEW=1; do not deploy it.")
    path = Path(database_path or Path(__file__).parent / ".local-data" / "workspace.sqlite3")
    if not production:
        path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def db():
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    if production:
        from workspace_postgres import PostgresDatabase
        db = PostgresDatabase(production_settings.database_url)

    with db() as conn:
        conn.executescript(SCHEMA)
        columns = {r['name'] for r in conn.execute('PRAGMA table_info(users)')} if not production else {'email_verified_at', 'verification_method'}
        for column, kind in [('email_verified_at', 'REAL'), ('verification_method', 'TEXT')]:
            if column not in columns:
                conn.execute(f'ALTER TABLE users ADD COLUMN {column} {kind}')

    email = EmailVerification(db, web_origin=production_settings.web_origin if production else 'http://127.0.0.1:5173')

    app = FastAPI(title="Loamy business workspace" if production else "Loamy local business workspace", docs_url=None, redoc_url=None)
    app.state.production = production
    if production:
        from psycopg.errors import SerializationFailure, DeadlockDetected
        async def transaction_conflict(_request, _error):
            return JSONResponse({'detail': 'Another request changed these records. Refresh and retry the same save.'}, status_code=409)
        app.add_exception_handler(SerializationFailure, transaction_conflict)
        app.add_exception_handler(DeadlockDetected, transaction_conflict)

    @app.get('/enterprise-api/config')
    def public_config():
        return {'local_preview': not production}

    @app.get('/health/live')
    def liveness():
        return {'status': 'ok'}

    @app.get('/health/ready')
    def readiness():
        try:
            with db() as conn:
                conn.execute('SELECT count(*) FROM users').fetchone()
            return {'status': 'ready'}
        except Exception:
            return JSONResponse({'status': 'unavailable'}, status_code=503)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # Host and Origin are checked even behind the loopback Vite proxy.
        if request.url.path in {'/health/live', '/health/ready'}:
            return await call_next(request)
        allowed_hosts = {urlsplit(production_settings.api_origin).hostname, urlsplit(production_settings.web_origin).hostname} if production else {"127.0.0.1", "localhost", "testserver"}
        if request.url.hostname not in allowed_hosts:
            return JSONResponse({"detail": "Host not allowed" if production else "Local preview only"}, status_code=403)
        if production and request.url.scheme != 'https':
            return JSONResponse({'detail': 'HTTPS is required'}, status_code=400)
        origin = request.headers.get("origin")
        allowed_origins = {production_settings.web_origin} if production else {
            "http://127.0.0.1:5173", "http://localhost:5173", "http://testserver"
        }
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin not in allowed_origins:
            return JSONResponse({"detail": "Open this workspace from its approved site" if production else "Open this workspace from the local Loamy preview"}, status_code=403)
        size = request.headers.get('content-length', '0')
        if not size.isdigit() or int(size) > 3_000_000:
            return JSONResponse({'detail': 'Request exceeds the 3 MB limit'}, status_code=413)
        received = 0
        chunks = []
        async for chunk in request.stream():
            received += len(chunk)
            if received > 3_000_000:
                return JSONResponse({'detail': 'Request exceeds the 3 MB limit'}, status_code=413)
            chunks.append(chunk)
        # Cache the bounded body so FastAPI can parse it downstream.
        request._body = b''.join(chunks)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        if production:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    def user(request: Request):
        with db() as conn:
            row = conn.execute(
                "SELECT u.id,u.name,u.email,u.email_verified_at,u.verification_method FROM sessions s JOIN users u ON u.id=s.user_id "
                "WHERE s.token_hash=? AND s.expires_at>?", (digest(request.cookies.get(COOKIE, "")), time.time())
            ).fetchone()
        if not row:
            raise HTTPException(401, "Sign in to your business workspace")
        return dict(row)

    def verified_user(actor=Depends(user)):
        if not email.is_verified(actor):
            raise HTTPException(403, 'Verify your email before using a business workspace')
        return actor

    def membership(conn, business_id, actor, owner=False):
        row = conn.execute("SELECT * FROM memberships WHERE business_id=? AND user_id=?",
                           (business_id, actor["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Business not found")
        if owner and row["role"] != "owner":
            raise HTTPException(403, "Only the owner can manage locations and team access")
        return row

    def audit(conn, business_id, actor_id, action):
        conn.execute("INSERT INTO audit_events VALUES (?,?,?,?,?)",
                     (secrets.token_hex(16), business_id, actor_id, action, time.time()))

    def start_session(conn, user_id, response):
        token = secrets.token_urlsafe(32)
        conn.execute("DELETE FROM sessions WHERE expires_at<=?", (time.time(),))
        conn.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(token), user_id, time.time() + SESSION_SECONDS))
        response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, secure=production, samesite="strict", path="/enterprise-api")

    def throttle(conn, key):
        conn.execute("DELETE FROM login_attempts WHERE created_at<?", (time.time() - 900,))
        count = conn.execute("SELECT count(*) FROM login_attempts WHERE key=?", (key,)).fetchone()[0]
        if count >= 15:
            raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")

    @app.get("/enterprise-api/me")
    def me(actor=Depends(user)):
        with db() as conn:
            businesses = conn.execute(
                "SELECT b.id,b.name,m.role,m.location_id FROM businesses b JOIN memberships m ON m.business_id=b.id "
                "WHERE m.user_id=? ORDER BY b.created_at", (actor["id"],)).fetchall() if email.is_verified(actor) else []
            last_mail = conn.execute('SELECT status,created_at FROM mail_outbox WHERE user_id=? AND transport=? ORDER BY created_at DESC LIMIT 1',
                                     (actor['id'], email.transport)).fetchone()
        actor['verified'] = email.is_verified(actor)
        return {"user": actor, "businesses": [dict(b) for b in businesses], "local_preview": not production,
                'mail_transport': email.transport, 'last_verification_email': dict(last_mail) if last_mail else None}

    @app.post("/enterprise-api/register", status_code=201)
    def register(data: Registration, request: Request, response: Response):
        salt = secrets.token_hex(16)
        uid = secrets.token_hex(16)
        with db() as conn:
            throttle(conn, request.client.host)
            conn.execute("INSERT INTO login_attempts VALUES (?,?)", (request.client.host, time.time()))
        try:
            with db() as conn:
                conn.execute("INSERT INTO users (id,name,email,password_hash,salt) VALUES (?,?,?,?,?)",
                             (uid, data.name, data.email, password_hash(data.password, salt), salt))
                start_session(conn, uid, response)
                message = email.queue(conn, {'id': uid, 'email': data.email})
        except sqlite3.IntegrityError:
            raise HTTPException(409, "An account with this email already exists. Sign in instead.")
        email.deliver(message)
        return {"user": {"id": uid, "name": data.name, "email": data.email}}

    @app.post("/enterprise-api/login")
    def login(data: Credentials, request: Request, response: Response):
        key = request.client.host
        with db() as conn:
            throttle(conn, key)
            row = conn.execute("SELECT * FROM users WHERE email=?", (data.email,)).fetchone()
            conn.execute("INSERT INTO login_attempts VALUES (?,?)", (key, time.time()))
        actual = password_hash(data.password, row["salt"] if row else "00" * 16)
        if not row or not hmac.compare_digest(actual, row["password_hash"]):
            raise HTTPException(401, "Email or password is incorrect")
        with db() as conn:
            # Replace this browser's previous session rather than accumulating it.
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (digest(request.cookies.get(COOKIE, "")),))
            start_session(conn, row["id"], response)
        return {"user": {k: row[k] for k in ("id", "name", "email")}}

    @app.post("/enterprise-api/logout")
    def logout(request: Request, response: Response):
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (digest(request.cookies.get(COOKIE, "")),))
        response.delete_cookie(COOKIE, path="/enterprise-api")
        return {"success": True}

    @app.post("/enterprise-api/businesses", status_code=201)
    def create_business(data: BusinessInput, actor=Depends(verified_user)):
        bid, lid = secrets.token_hex(16), secrets.token_hex(16)
        with db() as conn:
            conn.execute("INSERT INTO businesses VALUES (?,?,?)", (bid, data.name, time.time()))
            conn.execute("INSERT INTO locations VALUES (?,?,?,?,?)", (lid, bid, data.location_name, data.address, time.time()))
            conn.execute("INSERT INTO memberships VALUES (?,?,?,?,NULL)", (secrets.token_hex(16), bid, actor["id"], "owner"))
            audit(conn, bid, actor["id"], "Created business and first location")
        return {"id": bid}

    @app.get("/enterprise-api/businesses/{business_id}")
    def business(business_id: str, actor=Depends(verified_user)):
        with db() as conn:
            member = membership(conn, business_id, actor)
            info = dict(conn.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone())
            locations = conn.execute("SELECT * FROM locations WHERE business_id=? AND (?='owner' OR id=?) ORDER BY created_at",
                                     (business_id, member["role"], member["location_id"])).fetchall()
            team = []
            events = []
            if member["role"] == "owner":
                team = conn.execute("SELECT m.id,u.name,u.email,m.role,l.name location FROM memberships m "
                                    "JOIN users u ON u.id=m.user_id LEFT JOIN locations l ON l.id=m.location_id "
                                    "WHERE m.business_id=? ORDER BY m.role,u.name", (business_id,)).fetchall()
                events = conn.execute("SELECT a.action,a.created_at,u.name actor FROM audit_events a JOIN users u ON u.id=a.actor_id "
                                      "WHERE a.business_id=? ORDER BY a.created_at DESC LIMIT 20", (business_id,)).fetchall()
            pending = conn.execute("SELECT id,email,role,location_id FROM invitations WHERE business_id=? AND accepted_at IS NULL "
                                   "AND expires_at>?", (business_id, time.time())).fetchall() if member["role"] == "owner" else []
        return {"business": info, "role": member["role"], "locations": [dict(r) for r in locations],
                "team": [dict(r) for r in team], "events": [dict(r) for r in events], "invitations": [dict(r) for r in pending]}

    @app.post("/enterprise-api/businesses/{business_id}/locations", status_code=201)
    def add_location(business_id: str, data: LocationInput, actor=Depends(verified_user)):
        with db() as conn:
            membership(conn, business_id, actor, owner=True)
            lid = secrets.token_hex(16)
            try:
                conn.execute("INSERT INTO locations VALUES (?,?,?,?,?)", (lid, business_id, data.name, data.address, time.time()))
            except sqlite3.IntegrityError:
                raise HTTPException(409, "This business already has a location with that name")
            audit(conn, business_id, actor["id"], f"Added location: {data.name}")
        return {"id": lid}

    @app.post("/enterprise-api/businesses/{business_id}/invitations", status_code=201)
    def invite(business_id: str, data: InvitationInput, actor=Depends(verified_user)):
        token, iid = secrets.token_urlsafe(32), secrets.token_hex(16)
        with db() as conn:
            membership(conn, business_id, actor, owner=True)
            if not conn.execute("SELECT id FROM locations WHERE id=? AND business_id=?", (data.location_id, business_id)).fetchone():
                raise HTTPException(400, "Choose a location in this business")
            if conn.execute("SELECT m.id FROM memberships m JOIN users u ON m.user_id=u.id WHERE m.business_id=? AND u.email=?",
                            (business_id, data.email)).fetchone():
                raise HTTPException(409, "This person already belongs to the business")
            conn.execute("UPDATE invitations SET expires_at=0 WHERE business_id=? AND email=? AND accepted_at IS NULL", (business_id, data.email))
            conn.execute("INSERT INTO invitations VALUES (?,?,?,?,?,?,?,NULL)",
                         (iid, digest(token), business_id, data.email, data.role, data.location_id, time.time() + 72 * 3600))
            audit(conn, business_id, actor["id"], f"Created {data.role.replace('_', ' ')} invitation for {data.email}")
        return {"id": iid, "token": token}

    @app.post("/enterprise-api/invitations/accept")
    def accept(data: AcceptInput, actor=Depends(verified_user)):
        with db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            invitation = conn.execute("SELECT * FROM invitations WHERE token_hash=? AND accepted_at IS NULL AND expires_at>?",
                                      (digest(data.token), time.time())).fetchone()
            if not invitation:
                raise HTTPException(404, "This invitation has expired or has already been used")
            if invitation["email"] != actor["email"]:
                raise HTTPException(403, "Sign in with the email this invitation was created for")
            if conn.execute("SELECT id FROM memberships WHERE business_id=? AND user_id=?", (invitation["business_id"], actor["id"])).fetchone():
                raise HTTPException(409, "You already belong to this business")
            conn.execute("INSERT INTO memberships VALUES (?,?,?,?,?)", (secrets.token_hex(16), invitation["business_id"], actor["id"],
                                                                       invitation["role"], invitation["location_id"]))
            conn.execute("UPDATE invitations SET accepted_at=? WHERE id=?", (time.time(), invitation["id"]))
            audit(conn, invitation["business_id"], actor["id"], "Joined the business")
        return {"id": invitation["business_id"]}

    @app.delete("/enterprise-api/businesses/{business_id}/members/{member_id}")
    def remove_member(business_id: str, member_id: str, actor=Depends(verified_user)):
        with db() as conn:
            membership(conn, business_id, actor, owner=True)
            member = conn.execute("SELECT * FROM memberships WHERE id=? AND business_id=?", (member_id, business_id)).fetchone()
            if not member:
                raise HTTPException(404, "Member not found")
            if member["role"] == "owner":
                raise HTTPException(400, "The business owner cannot be removed")
            conn.execute("DELETE FROM memberships WHERE id=?", (member_id,))
            audit(conn, business_id, actor["id"], "Removed a team member's access")
        return {"success": True}

    email.install(app, user, start_session)
    install_finances(app, db, verified_user, membership, audit)
    install_orders(app, db, verified_user, membership, audit, email.transport, local_preview=not production)
    install_payments(app, db, verified_user, membership, audit)
    install_expenses(app, db, verified_user, membership, audit)
    return app
