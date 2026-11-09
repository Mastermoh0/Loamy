"""Local catalogue and immutable order price snapshots; no payment posting or delivery."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import secrets
import time
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from workspace_finances import money, VoidInput
from workspace_invoices import install_invoices
from workspace_pricing import PricingInput, install_pricing, location_pricing, order_pricing, calculate


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ProfileInput(Input):
    invoice_name: str = Field(min_length=2, max_length=100)
    address: str = Field(min_length=2, max_length=240)
    payment_instructions: str = Field(default='', max_length=1000)


class ServiceInput(Input):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default='', max_length=500)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    active: bool = True


class OrderLine(Input):
    service_id: str = Field(min_length=1, max_length=64)
    quantity: int = Field(strict=True, ge=1, le=10000)
    expected_price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class OrderInput(Input):
    customer_name: str = Field(min_length=2, max_length=120)
    customer_contact: str = Field(min_length=3, max_length=254)
    lines: list[OrderLine] = Field(min_length=1, max_length=20)
    idempotency_key: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    expected_tax_rate: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    discount_type: Literal['none', 'fixed', 'percent'] = 'none'
    discount_value: Decimal = Field(default=Decimal('0'), ge=0, max_digits=10, decimal_places=2)
    discount_reason: str = Field(default='', max_length=240)

    @field_validator('lines')
    @classmethod
    def unique_services(cls, lines):
        if len({line.service_id for line in lines}) != len(lines):
            raise ValueError('Combine quantities for each service into one line')
        return lines


def install_orders(app, db, verified_user, membership, audit, transport, local_preview=True):
    with db() as conn:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS location_profiles (
            location_id TEXT PRIMARY KEY REFERENCES locations(id), invoice_name TEXT NOT NULL,
            address TEXT NOT NULL, payment_instructions TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS services (
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id),
            location_id TEXT NOT NULL REFERENCES locations(id), name TEXT NOT NULL,
            description TEXT NOT NULL, price_minor INTEGER NOT NULL CHECK(price_minor>0),
            active INTEGER NOT NULL CHECK(active IN (0,1)), updated_at REAL NOT NULL
          );
          CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE,
            business_id TEXT NOT NULL REFERENCES businesses(id), location_id TEXT NOT NULL REFERENCES locations(id),
            actor_id TEXT NOT NULL REFERENCES users(id), customer_name TEXT NOT NULL, customer_contact TEXT NOT NULL,
            total_minor INTEGER NOT NULL CHECK(total_minor>0), status TEXT NOT NULL CHECK(status IN ('open','cancelled')),
            created_at REAL NOT NULL, order_date TEXT NOT NULL, profile_snapshot TEXT NOT NULL,
            request_hash TEXT NOT NULL, idempotency_key TEXT NOT NULL,
            cancelled_at REAL, cancelled_by TEXT REFERENCES users(id), cancel_reason TEXT,
            UNIQUE(business_id,idempotency_key)
          );
          CREATE TABLE IF NOT EXISTS order_lines (
            order_id TEXT NOT NULL REFERENCES orders(id), position INTEGER NOT NULL,
            service_id TEXT NOT NULL REFERENCES services(id), name TEXT NOT NULL, description TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity>0), unit_minor INTEGER NOT NULL CHECK(unit_minor>0),
            PRIMARY KEY(order_id,position)
          );
          CREATE INDEX IF NOT EXISTS orders_location_date ON orders(business_id,location_id,order_date);
          CREATE INDEX IF NOT EXISTS services_location ON services(business_id,location_id);
        ''')

    def scope(conn, bid, lid, actor, write=False, catalogue=False):
        member = membership(conn, bid, actor)
        allowed = {'owner', 'manager'} if catalogue else {'owner', 'manager', 'front_desk'} if write else {'owner', 'manager', 'front_desk', 'finance'}
        if member['role'] not in allowed:
            raise HTTPException(403, 'Your role does not allow this order or catalogue action')
        if member['role'] != 'owner' and lid != member['location_id']:
            raise HTTPException(404, 'Location not found')
        location = conn.execute('SELECT * FROM locations WHERE id=? AND business_id=?', (lid, bid)).fetchone()
        if not location:
            raise HTTPException(404, 'Location not found')
        return location

    install_pricing(db)

    def profile(conn, bid, location):
        saved = conn.execute('SELECT invoice_name,address,payment_instructions FROM location_profiles WHERE location_id=?', (location['id'],)).fetchone()
        return dict(saved) if saved else {'invoice_name': conn.execute('SELECT name FROM businesses WHERE id=?', (bid,)).fetchone()[0],
                                          'address': location['address'], 'payment_instructions': ''}

    base = '/enterprise-api/businesses/{business_id}/locations/{location_id}'

    @app.get(base + '/catalogue')
    def catalogue(business_id: str, location_id: str, actor=Depends(verified_user)):
        with db() as conn:
            location = scope(conn, business_id, location_id, actor)
            rows = conn.execute('SELECT * FROM services WHERE business_id=? AND location_id=? ORDER BY active DESC,name,id', (business_id, location_id)).fetchall()
            result = []
            for row in rows:
                service = dict(row)
                service['price'] = money(service.pop('price_minor'))
                service['active'] = bool(service['active'])
                result.append(service)
            return {'services': result, 'profile': profile(conn, business_id, location), 'pricing': location_pricing(conn, location_id), 'currency': 'NGN'}

    @app.put(base + '/pricing')
    def save_pricing(business_id: str, location_id: str, data: PricingInput, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, location_id, actor, catalogue=True)
            conn.execute('INSERT INTO location_pricing VALUES (?,?,?) ON CONFLICT(location_id) DO UPDATE SET tax_label=excluded.tax_label,tax_rate_bps=excluded.tax_rate_bps',
                         (location_id, data.tax_label, int(data.tax_rate * 100)))
            audit(conn, business_id, actor['id'], f'Updated exclusive tax for location {location_id}: {data.tax_label} {data.tax_rate}%')
        return {'success': True}

    @app.put(base + '/profile')
    def save_profile(business_id: str, location_id: str, data: ProfileInput, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, location_id, actor, catalogue=True)
            conn.execute('INSERT INTO location_profiles VALUES (?,?,?,?) ON CONFLICT(location_id) DO UPDATE SET invoice_name=excluded.invoice_name,address=excluded.address,payment_instructions=excluded.payment_instructions',
                         (location_id, data.invoice_name, data.address, data.payment_instructions))
            audit(conn, business_id, actor['id'], f'Updated order profile for location {location_id}')
        return {'success': True}

    @app.post(base + '/services', status_code=201)
    def add_service(business_id: str, location_id: str, data: ServiceInput, actor=Depends(verified_user)):
        sid = secrets.token_hex(16)
        with db() as conn:
            scope(conn, business_id, location_id, actor, catalogue=True)
            conn.execute('INSERT INTO services VALUES (?,?,?,?,?,?,?,?)', (sid, business_id, location_id, data.name, data.description, int(data.price * 100), int(data.active), time.time()))
            audit(conn, business_id, actor['id'], f'Added service: {data.name} at location {location_id}')
        return {'id': sid}

    @app.put(base + '/services/{service_id}')
    def edit_service(business_id: str, location_id: str, service_id: str, data: ServiceInput, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, location_id, actor, catalogue=True)
            updated = conn.execute('UPDATE services SET name=?,description=?,price_minor=?,active=?,updated_at=? WHERE id=? AND business_id=? AND location_id=?',
                                   (data.name, data.description, int(data.price * 100), int(data.active), time.time(), service_id, business_id, location_id))
            if not updated.rowcount:
                raise HTTPException(404, 'Service not found')
            audit(conn, business_id, actor['id'], f'Updated service: {data.name} at location {location_id}')
        return {'success': True}

    @app.post(base + '/orders', status_code=201)
    def create_order(business_id: str, location_id: str, data: OrderInput, actor=Depends(verified_user)):
        request_data = data.model_dump(mode='json', exclude={'idempotency_key'})
        # Preserve retry hashes for orders created before pricing fields existed.
        for field in {'expected_tax_rate', 'discount_type', 'discount_value', 'discount_reason'} - data.model_fields_set:
            request_data.pop(field)
        request_hash = hashlib.sha256(json.dumps(request_data, sort_keys=True).encode()).hexdigest()
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            location = scope(conn, business_id, location_id, actor, write=True)
            previous = conn.execute('SELECT * FROM orders WHERE business_id=? AND idempotency_key=?', (business_id, data.idempotency_key)).fetchone()
            if previous:
                if previous['actor_id'] != actor['id'] or previous['location_id'] != location_id or previous['request_hash'] != request_hash:
                    raise HTTPException(409, 'This save reference was already used for another order')
                return {'id': previous['id'], 'reference': previous['reference'], 'duplicate': True}
            lines, total = [], 0
            for item in data.lines:
                service = conn.execute('SELECT * FROM services WHERE id=? AND business_id=? AND location_id=? AND active=1', (item.service_id, business_id, location_id)).fetchone()
                if not service:
                    raise HTTPException(409, 'A chosen service is no longer available. Refresh the catalogue and review this order.')
                if int(item.expected_price * 100) != service['price_minor']:
                    raise HTTPException(409, 'A service price changed. Refresh the catalogue and review this order before saving.')
                lines.append((item.service_id, service['name'], service['description'], item.quantity, service['price_minor']))
                total += item.quantity * service['price_minor']
            pricing = location_pricing(conn, location_id)
            rate_bps = int(Decimal(pricing['tax_rate']) * 100)
            if data.expected_tax_rate is None and rate_bps or data.expected_tax_rate is not None and int(data.expected_tax_rate * 100) != rate_bps:
                raise HTTPException(409, 'Tax settings changed. Refresh the catalogue and review this order before saving.')
            member = membership(conn, business_id, actor)
            if data.discount_type != 'none' and member['role'] not in {'owner', 'manager'}:
                raise HTTPException(403, 'Only an owner or manager can apply a discount')
            if data.discount_type != 'none' and (data.discount_value <= 0 or len(data.discount_reason) < 3):
                raise HTTPException(422, 'Enter a positive discount and a reason of at least three characters')
            subtotal = total
            discount, tax, total = calculate(subtotal, data.discount_type, data.discount_value, rate_bps)
            oid = secrets.token_hex(16)
            today = datetime.now(timezone(timedelta(hours=1))).date().isoformat()
            # The complete random ID keeps the human-readable reference unique without a shared counter.
            reference = f'ORD-{today.replace("-", "")}-{oid.upper()}'
            conn.execute('INSERT INTO orders (id,reference,business_id,location_id,actor_id,customer_name,customer_contact,total_minor,status,created_at,order_date,profile_snapshot,request_hash,idempotency_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (oid, reference, business_id, location_id, actor['id'], data.customer_name, data.customer_contact, total, 'open', time.time(), today,
                          json.dumps(profile(conn, business_id, location)), request_hash, data.idempotency_key))
            for position, line in enumerate(lines):
                conn.execute('INSERT INTO order_lines VALUES (?,?,?,?,?,?,?)', (oid, position, *line))
            conn.execute('INSERT INTO order_pricing VALUES (?,?,?,?,?,?,?,?,?)',
                         (oid, subtotal, data.discount_type, int(data.discount_value * 100), discount, data.discount_reason, pricing['tax_label'], rate_bps, tax))
            audit(conn, business_id, actor['id'], f'Created order {reference} at location {location_id}')
        return {'id': oid, 'reference': reference, 'duplicate': False}

    @app.get(base + '/orders')
    def list_orders(business_id: str, location_id: str, period: str = 'today', actor=Depends(verified_user)):
        if period not in {'today', 'all'}:
            raise HTTPException(422, 'Choose today or all orders')
        today = datetime.now(timezone(timedelta(hours=1))).date().isoformat()
        with db() as conn:
            scope(conn, business_id, location_id, actor)
            params = (business_id, location_id, period, today)
            where = "business_id=? AND location_id=? AND (?='all' OR order_date=?)"
            rows = conn.execute(f'SELECT id,reference,customer_name,total_minor,status,created_at,order_date FROM orders WHERE {where} ORDER BY created_at DESC,id DESC LIMIT 100', params).fetchall()
            counts = dict(conn.execute(f"SELECT count(*) total,coalesce(sum(CASE WHEN status='open' THEN 1 ELSE 0 END),0) open,coalesce(sum(CASE WHEN status='cancelled' THEN 1 ELSE 0 END),0) cancelled FROM orders WHERE {where}", params).fetchone())
            result = []
            for row in rows:
                order = dict(row)
                order['total'] = money(order.pop('total_minor'))
                result.append(order)
        return {'orders': result, 'counts': counts, 'today': today, 'period': period}

    @app.get(base + '/orders/{order_id}')
    def order_detail(business_id: str, location_id: str, order_id: str, actor=Depends(verified_user)):
        with db() as conn:
            scope(conn, business_id, location_id, actor)
            row = conn.execute('SELECT o.*,u.name created_by,c.name cancelled_by_name FROM orders o JOIN users u ON u.id=o.actor_id LEFT JOIN users c ON c.id=o.cancelled_by WHERE o.id=? AND o.business_id=? AND o.location_id=?', (order_id, business_id, location_id)).fetchone()
            if not row:
                raise HTTPException(404, 'Order not found')
            order = dict(row)
            order['total'] = money(order.pop('total_minor'))
            order['pricing'] = order_pricing(conn, order_id, row['total_minor'])
            order['profile'] = json.loads(order.pop('profile_snapshot'))
            order.pop('request_hash')
            order.pop('idempotency_key')
            order['lines'] = [{'service_id': line['service_id'], 'name': line['name'], 'description': line['description'], 'quantity': line['quantity'],
                               'unit_price': money(line['unit_minor']), 'total': money(line['quantity'] * line['unit_minor'])}
                              for line in conn.execute('SELECT * FROM order_lines WHERE order_id=? ORDER BY position', (order_id,))]
        return order

    @app.post(base + '/orders/{order_id}/cancel')
    def cancel_order(business_id: str, location_id: str, order_id: str, data: VoidInput, actor=Depends(verified_user)):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            scope(conn, business_id, location_id, actor, write=True)
            order = conn.execute('SELECT * FROM orders WHERE id=? AND business_id=? AND location_id=?', (order_id, business_id, location_id)).fetchone()
            if not order:
                raise HTTPException(404, 'Order not found')
            if order['status'] == 'open':
                if conn.execute("SELECT n.id FROM customer_notices n JOIN invoices i ON i.id=n.invoice_id WHERE i.order_id=? AND n.status='sending' AND n.updated_at>?", (order_id, time.time() - 120)).fetchone():
                    raise HTTPException(409, 'A customer balance notice is being sent. Wait for its result before cancelling.')
                if conn.execute('SELECT a.id FROM payment_allocations a JOIN invoices i ON i.id=a.invoice_id WHERE i.order_id=? AND a.reversed_at IS NULL', (order_id,)).fetchone():
                    raise HTTPException(409, 'Reverse invoice payment allocations before cancelling. Reversal does not refund money.')
                if conn.execute("SELECT d.id FROM invoice_deliveries d JOIN invoices i ON i.id=d.invoice_id WHERE i.order_id=? AND d.status='sending' AND d.created_at>?", (order_id, time.time() - 120)).fetchone():
                    raise HTTPException(409, 'An invoice email is being sent. Wait for its result before cancelling.')
                conn.execute("UPDATE orders SET status='cancelled',cancel_reason=?,cancelled_at=?,cancelled_by=? WHERE id=?", (data.reason, time.time(), actor['id'], order_id))
                conn.execute("UPDATE invoices SET status='cancelled' WHERE order_id=?", (order_id,))
                audit(conn, business_id, actor['id'], f'Cancelled order {order["reference"]}: {data.reason}')
        return {'success': True}

    install_invoices(app, db, verified_user, scope, audit, transport, local_preview=local_preview)
