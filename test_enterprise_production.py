"""Opt-in release rehearsal against a disposable, TLS-verified PostgreSQL database."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
import re
import secrets
import sqlite3
import unittest
from unittest.mock import patch
from urllib.parse import quote, urlencode

from fastapi.testclient import TestClient
from workspace_runtime import ProductionSettings

ROOT = Path(__file__).resolve().parent


class ProductionConfigTests(unittest.TestCase):
    def settings(self, **extra):
        return {'LOAMY_LOCAL_PREVIEW': '0', 'LOAMY_WORKSPACE_WEB_ORIGIN': 'https://workspace.example.test',
                'LOAMY_WORKSPACE_API_ORIGIN': 'https://workspace.example.test',
                'LOAMY_WORKSPACE_DATABASE_URL': 'postgresql://loamy_enterprise_app:fake@database.example.test/app?sslmode=verify-full',
                'LOAMY_MAIL_TRANSPORT': 'smtp', 'LOAMY_SMTP_HOST': 'mail.example.test', 'LOAMY_SMTP_FROM': 'test@example.test',
                'LOAMY_SMTP_USERNAME': 'test', 'LOAMY_SMTP_PASSWORD': 'fake-test-only', **extra}

    def test_fail_closed_configuration(self):
        for extra in [{'LOAMY_LOCAL_PREVIEW': '1'}, {'LOAMY_MAIL_TRANSPORT': 'capture'}, {'LOAMY_SMTP_PASSWORD': ''},
                      {'LOAMY_WORKSPACE_WEB_ORIGIN': 'http://workspace.example.test'},
                      {'LOAMY_WORKSPACE_API_ORIGIN': 'https://workspace.example.test/path'},
                      {'LOAMY_WORKSPACE_DATABASE_URL': 'postgresql://postgres:fake@database.example.test/app?sslmode=verify-full'},
                      {'LOAMY_WORKSPACE_DATABASE_URL': 'postgresql://loamy_enterprise_app:fake@database.example.test/app?sslmode=disable'}]:
            with self.subTest(extra=list(extra)), patch.dict(os.environ, self.settings(**extra)), self.assertRaises(RuntimeError):
                ProductionSettings.from_env()
        with patch.dict(os.environ, self.settings()):
            self.assertEqual(ProductionSettings.from_env().web_origin, 'https://workspace.example.test')


@unittest.skipUnless(os.getenv('LOAMY_RUN_POSTGRES_TESTS') == '1', 'Opt-in: requires the isolated TLS PostgreSQL rehearsal database')
class PostgresReleaseTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        password = (ROOT / '.local-data/postgres-test.env').read_text().strip().split('=', 1)[1]
        certificate = str(ROOT / '.local-data/postgres-certs/ca.crt')
        query = urlencode({'sslmode': 'verify-full', 'sslrootcert': certificate})
        self.admin_dsn = f'postgresql://postgres:{quote(password)}@127.0.0.1:55432/enterprise_test?{query}'
        self.app_dsn = f'postgresql://loamy_enterprise_app:{quote(password)}@127.0.0.1:55432/enterprise_test?{query}'
        with psycopg.connect(self.admin_dsn, autocommit=True) as admin:
            # Destructive reset is restricted to the named, loopback-only disposable database.
            self.assertEqual(admin.info.dbname, 'enterprise_test')
            self.assertEqual(admin.info.host, '127.0.0.1')
            if not admin.execute("SELECT 1 FROM pg_roles WHERE rolname='loamy_enterprise_app'").fetchone():
                admin.execute(sql.SQL('CREATE ROLE loamy_enterprise_app LOGIN PASSWORD {}').format(sql.Literal(password)))
            for role in ['anon', 'authenticated', 'service_role']:
                if not admin.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                    admin.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
            admin.execute('DROP SCHEMA IF EXISTS enterprise CASCADE')
            admin.execute('CREATE TABLE IF NOT EXISTS public.loamy_rehearsal_sentinel (id INT PRIMARY KEY)')
            admin.execute('INSERT INTO public.loamy_rehearsal_sentinel VALUES (1) ON CONFLICT DO NOTHING')
            admin.execute((ROOT / 'scripts/sql/enterprise/001_enterprise.sql').read_text())
            admin.execute((ROOT / 'scripts/sql/enterprise/002_receipt_extraction.sql').read_text())
        self.env = patch.dict(os.environ, ProductionConfigTests().settings(LOAMY_WORKSPACE_WEB_ORIGIN='https://workspace.example.test',
                            LOAMY_WORKSPACE_API_ORIGIN='https://workspace.example.test', LOAMY_WORKSPACE_DATABASE_URL=self.app_dsn))
        self.env.start()
        self.messages = []
        self.sender = patch('workspace_email.send_smtp', side_effect=self.messages.append)
        self.invoice_sender = patch('workspace_invoices.send_smtp', side_effect=self.messages.append)
        self.sender.start(); self.invoice_sender.start()
        from enterprise_production import create_app
        self.app = create_app()
        self.owner = self.client()
        self.register(self.owner, 'owner@example.test')

    def tearDown(self):
        self.sender.stop(); self.invoice_sender.stop(); self.env.stop()

    def client(self):
        return TestClient(self.app, base_url='https://workspace.example.test', headers={'Origin': 'https://workspace.example.test'})

    def register(self, client, email):
        response = client.post('/enterprise-api/register', json={'name': 'Rehearsal User', 'email': email, 'password': 'Rehearsal-password-42'})
        self.assertEqual(response.status_code, 201, response.text)
        body = self.messages[-1].get_content()
        token = re.search(r'#verify=([A-Za-z0-9_-]+)', body)[1]
        self.assertIn('https://workspace.example.test/business#verify=', body)
        self.assertEqual(client.post('/enterprise-api/email/verify', json={'token': token}).status_code, 200)

    def fixture(self):
        business = self.owner.post('/enterprise-api/businesses', json={'name': 'Rehearsal business', 'location_name': 'Lekki', 'address': 'Fictional test address'})
        self.assertEqual(business.status_code, 201, business.text)
        self.bid = business.json()['id']
        self.lid = self.owner.get(f'/enterprise-api/businesses/{self.bid}').json()['locations'][0]['id']
        self.base = f'/enterprise-api/businesses/{self.bid}/locations/{self.lid}'
        service = self.owner.post(self.base + '/services', json={'name': 'Test service', 'price': '50000.00'})
        self.assertEqual(service.status_code, 201, service.text)
        self.sid = service.json()['id']
        return self.new_invoice()

    def new_invoice(self):
        order = self.owner.post(self.base + '/orders', json={'customer_name': 'Test Guest', 'customer_contact': 'guest@example.test',
                'lines': [{'service_id': self.sid, 'quantity': 1, 'expected_price': '50000.00'}], 'idempotency_key': secrets.token_hex(16)})
        self.assertEqual(order.status_code, 201, order.text)
        oid = order.json()['id']
        invoice = self.owner.post(self.base + f'/orders/{oid}/invoice', json={})
        self.assertEqual(invoice.status_code, 201, invoice.text)
        return oid, invoice.json()['invoice']['id']

    def test_auth_headers_scope_and_private_schema(self):
        import psycopg
        self.assertTrue(self.app.state.production)
        self.fixture()
        cookie = self.owner.post('/enterprise-api/login', json={'email': 'owner@example.test', 'password': 'Rehearsal-password-42'}).headers['set-cookie'].lower()
        for flag in ['secure', 'httponly', 'samesite=strict']:
            self.assertIn(flag, cookie)
        self.assertEqual(self.owner.get('/enterprise-api/email/inbox').status_code, 404)
        self.assertFalse(self.owner.get('/enterprise-api/config').json()['local_preview'])
        self.assertEqual(self.owner.get('/health/ready').status_code, 200)
        self.assertEqual(self.owner.get('/enterprise-api/me').headers['strict-transport-security'], 'max-age=31536000')
        self.assertEqual(self.owner.post('/enterprise-api/logout', headers={'Origin': 'https://attacker.example.test'}).status_code, 403)
        self.assertEqual(self.owner.post('/enterprise-api/logout', content=b'x' * 3_000_001).status_code, 413)
        self.assertEqual(self.owner.post('/enterprise-api/logout', content=iter([b'x' * 1_500_001] * 2)).status_code, 413)
        self.assertEqual(self.owner.get('http://workspace.example.test/enterprise-api/me').status_code, 400)
        outsider = self.client(); self.register(outsider, 'outside@example.test')
        self.assertEqual(outsider.get(f'/enterprise-api/businesses/{self.bid}').status_code, 404)
        with psycopg.connect(self.app_dsn, autocommit=True) as connection:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                connection.execute('CREATE TABLE enterprise.should_not_exist (id INT)')
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                connection.execute("UPDATE enterprise.audit_events SET action='tampered'")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                connection.execute("UPDATE enterprise.financial_records SET amount_minor=1")
        with psycopg.connect(self.admin_dsn) as admin:
            self.assertEqual(admin.execute('SELECT id FROM public.loamy_rehearsal_sentinel').fetchone()[0], 1)
            self.assertTrue(admin.execute('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone()[0])
            for role in ['anon', 'authenticated', 'service_role']:
                self.assertFalse(admin.execute("SELECT has_schema_privilege(%s,'enterprise','USAGE')", (role,)).fetchone()[0])

    def test_compiled_frontend_is_served_without_exposing_unknown_api_routes(self):
        from enterprise_production import create_app
        with patch.dict(os.environ, {'LOAMY_WORKSPACE_SERVE_DIST': '1'}):
            app = create_app()
        client = TestClient(app, base_url='https://workspace.example.test')
        page = client.get('/business')
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn('id="root"', page.text)
        self.assertEqual(client.get('/enterprise-api/not-a-route').status_code, 404)
        self.assertEqual(client.get('/health/not-a-route').status_code, 404)
        oid, _ = self.fixture()
        invoice = self.owner.get(self.base + f'/orders/{oid}/invoice').json()['invoice']
        self.assertFalse(invoice['snapshot']['local_preview'])

    def test_concurrent_payment_cannot_allocate_same_money_twice(self):
        oid, iid = self.fixture()
        _, second_iid = self.new_invoice()
        today = datetime.now(timezone(timedelta(hours=1))).date().isoformat()
        credit = self.owner.post(self.base + '/payments/credits', json={'source_id': 'test-receipt-001', 'amount': '45000.00', 'occurred_on': today, 'payer': 'Test Guest', 'narration': 'Fictional cash receipt'})
        self.assertEqual(credit.status_code, 201, credit.text)
        rid = credit.json()['id']
        def allocate(invoice):
            client = self.client(); client.cookies.update(self.owner.cookies)
            return client.post(self.base + '/payments/allocations', json={'record_id': rid, 'invoice_id': invoice, 'amount': '45000.00', 'note': 'Concurrent rehearsal allocation', 'idempotency_key': secrets.token_hex(16)})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(allocate, [iid, second_iid]))
        self.assertEqual(sorted(response.status_code for response in responses), [201, 409], [r.text for r in responses])
        review = self.owner.get(self.base + '/payments').json()
        self.assertEqual(sum(float(invoice['allocated']) for invoice in review['invoices']), 45000)
        ledger = self.owner.get(f'/enterprise-api/businesses/{self.bid}/financial-records')
        self.assertEqual(ledger.status_code, 200, ledger.text)
        self.assertEqual(ledger.json()['count'], 1)
        winner = next(item for item in review['invoices'] if item['allocated'] == '45000.00')
        self.assertEqual((winner['status'], winner['outstanding']), ('part_paid', '5000.00'))

    def test_postgres_receipt_approval_posting_and_category(self):
        import base64
        from io import BytesIO
        from PIL import Image
        self.fixture()
        staff = self.client(); self.register(staff, 'staff@example.test')
        invitation = self.owner.post(f'/enterprise-api/businesses/{self.bid}/invitations', json={'email': 'staff@example.test', 'role': 'staff', 'location_id': self.lid}).json()
        self.assertEqual(staff.post('/enterprise-api/invitations/accept', json={'token': invitation['token']}).status_code, 200)
        buffer = BytesIO(); Image.new('RGB', (20, 20), 'green').save(buffer, format='PNG')
        payload = {'vendor': 'Test store', 'purpose': 'Fictional supplies', 'category': 'Supplies', 'amount': '1000.10',
                   'occurred_on': datetime.now(timezone(timedelta(hours=1))).date().isoformat(), 'receipt_base64': base64.b64encode(buffer.getvalue()).decode(), 'idempotency_key': secrets.token_hex(16)}
        with patch('workspace_expenses.read_receipt', return_value=('TEST STORE\nTotal NGN 1000.10', 'rehearsal-reader')):
            extraction = staff.post(self.base + '/expenses/extract', json={'receipt_base64': payload['receipt_base64']})
        self.assertEqual(extraction.status_code, 200, extraction.text)
        payload['extraction_id'] = extraction.json()['id']
        response = staff.post(self.base + '/expenses', json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        eid = response.json()['id']
        reviewed = self.owner.post(self.base + f'/expenses/{eid}/review', json={'decision': 'approved', 'revision': 1, 'reason': 'Receipt reviewed independently'})
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        posted = self.owner.post(self.base + f'/expenses/{eid}/post', json={'reason': 'Record paid expense'})
        self.assertEqual(posted.status_code, 200, posted.text)
        self.assertTrue(self.owner.post(self.base + f'/expenses/{eid}/post', json={'reason': 'Repeat request'}).json()['duplicate'])
        listed = self.owner.get(self.base + '/expenses')
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()['categories'][0]['amount'], '1000.10')
        self.assertEqual(listed.json()['expenses'][0]['versions'][0]['extraction']['engine'], 'rehearsal-reader')
        self.assertEqual(staff.get(self.base + f'/expenses/{eid}/receipt/1').content, buffer.getvalue())
        dashboard = self.owner.get(f'/enterprise-api/businesses/{self.bid}/owner-dashboard')
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        self.assertEqual((dashboard.json()['totals']['outflow'], dashboard.json()['totals']['outstanding']), ('1000.10', '50000.00'))
        self.assertEqual(staff.get(f'/enterprise-api/businesses/{self.bid}/owner-dashboard').status_code, 403)


if __name__ == '__main__':
    unittest.main()
