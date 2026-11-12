"""Opt-in release rehearsal against a disposable, TLS-verified PostgreSQL database."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import os
import json
import time
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
            admin.execute("INSERT INTO enterprise.businesses VALUES ('upgrade-sentinel','Existing upgrade fixture',0)")
            admin.execute((ROOT / 'scripts/sql/enterprise/003_supplier_whatsapp.sql').read_text())
            admin.execute((ROOT / 'scripts/sql/enterprise/004_reports_notifications.sql').read_text())
            admin.execute((ROOT / 'scripts/sql/enterprise/005_pricing.sql').read_text())
            admin.execute((ROOT / 'scripts/sql/enterprise/006_customer_workflows.sql').read_text())
            self.assertEqual(admin.execute("SELECT name FROM enterprise.businesses WHERE id='upgrade-sentinel'").fetchone()[0], 'Existing upgrade fixture')
            admin.execute("DELETE FROM enterprise.businesses WHERE id='upgrade-sentinel'")
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

    def test_pricing_upgrade_exact_totals_private_history_and_location_qr(self):
        import psycopg
        oid, _ = self.fixture()
        self.assertEqual(self.owner.get(self.base + f'/orders/{oid}').json()['total'], '50000.00')
        self.assertEqual(self.owner.put(self.base + '/pricing', json={'tax_label': 'Test VAT', 'tax_rate': '7.50'}).status_code, 200)
        response = self.owner.post(self.base + '/orders', json={'customer_name': 'Tax Guest', 'customer_contact': 'guest@example.test',
            'lines': [{'service_id': self.sid, 'quantity': 1, 'expected_price': '50000.00'}], 'idempotency_key': secrets.token_hex(16),
            'expected_tax_rate': '7.50', 'discount_type': 'percent', 'discount_value': '10', 'discount_reason': 'Approved test offer'})
        self.assertEqual(response.status_code, 201, response.text)
        adjusted = response.json()['id']
        detail = self.owner.get(self.base + f'/orders/{adjusted}').json()
        self.assertEqual((detail['pricing']['discount'], detail['pricing']['tax'], detail['total']), ('5000.00', '3375.00', '48375.00'))
        invoice = self.owner.post(self.base + f'/orders/{adjusted}/invoice', json={}).json()['invoice']
        self.assertEqual(invoice['payments']['outstanding'], '48375.00')
        link = self.owner.get(self.base + '/link')
        self.assertEqual(link.status_code, 200, link.text)
        self.assertEqual(link.json()['url'], f'https://workspace.example.test/business?business={self.bid}&location={self.lid}')
        with psycopg.connect(self.app_dsn, autocommit=True) as conn:
            for query in ['UPDATE enterprise.order_pricing SET tax_minor=1', 'DELETE FROM enterprise.order_pricing', 'DELETE FROM enterprise.location_pricing']:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(query)

    def test_customer_workflow_runtime_grants_worker_outcomes_and_webhook_receipts(self):
        import psycopg
        self.fixture()
        response=self.owner.post(self.base+'/orders',json={'customer_name':'Contact Guest','customer_email':'contact@example.test','customer_whatsapp':'+2348012345678','whatsapp_consent':True,'preferred_channel':'whatsapp',
            'lines':[{'service_id':self.sid,'quantity':1,'expected_price':'50000.00'}],'idempotency_key':'production-contact-order-01'})
        self.assertEqual(response.status_code,201,response.text)
        oid=response.json()['id'];invoice=self.owner.post(self.base+f'/orders/{oid}/invoice',json={}).json()['invoice'];iid=invoice['id']
        with psycopg.connect(self.admin_dsn,autocommit=True) as conn:
            conn.execute('UPDATE enterprise.invoices SET due_on=%s WHERE id=%s',((datetime.now(timezone(timedelta(hours=1)))-timedelta(days=1)).date().isoformat(),iid))
        route={'phone_id':'1234567890','invoice_template':'invoice_test','reminder_template':'reminder_test','language':'en_US'}
        env={'LOAMY_WHATSAPP_APP_SECRET':'x'*32,'LOAMY_WHATSAPP_VERIFY_TOKEN':'v'*32,'LOAMY_WHATSAPP_ACCESS_TOKEN':'fake-provider-token','LOAMY_WHATSAPP_GRAPH_VERSION':'v99.0','LOAMY_WHATSAPP_ROUTES':json.dumps({'1234567890':self.bid}),'LOAMY_WHATSAPP_OUTBOUND':json.dumps({self.bid:route})}
        with patch.dict(os.environ,env):
            from enterprise_production import create_app
            app=create_app();client=TestClient(app,base_url='https://workspace.example.test',headers={'Origin':'https://workspace.example.test'});client.cookies.update(self.owner.cookies)
            comm=self.base+f'/invoices/{iid}'
            choice={'channel':'whatsapp','confirm':True,'idempotency_key':'production-wa-invoice-01'}
            with patch('workspace_followups.send_whatsapp',return_value='provider-invoice-test') as send:
                sent=client.post(comm+'/deliver',json=choice)
                self.assertEqual(sent.status_code,200,sent.text);self.assertEqual(sent.json()['status'],'accepted')
                self.assertTrue(client.post(comm+'/deliver',json=choice).json()['duplicate']);self.assertEqual(send.call_count,1)
            import hmac,hashlib
            payload={'object':'whatsapp_business_account','entry':[{'changes':[{'field':'messages','value':{'messaging_product':'whatsapp','metadata':{'phone_number_id':'1234567890'},'statuses':[{'id':'provider-invoice-test','status':'delivered'}]}}]}]}
            raw=json.dumps(payload).encode();signature='sha256='+hmac.new(b'x'*32,raw,hashlib.sha256).hexdigest()
            public=TestClient(app,base_url='https://workspace.example.test')
            event=public.post('/enterprise-api/integrations/whatsapp/webhook',content=raw,headers={'X-Hub-Signature-256':signature,'Content-Type':'application/json'})
            self.assertEqual(event.status_code,200,event.text)
            self.assertEqual(client.get(comm+'/communications').json()['deliveries'][0]['status'],'delivered')
            plan=client.post(comm+'/reminder-plans',json={**choice,'idempotency_key':'production-reminder-plan-01','first_run_at':time.time(),'max_sends':2,'interval_days':1})
            self.assertEqual(plan.status_code,201,plan.text)
            with patch('workspace_followups.send_whatsapp',side_effect=OSError('uncertain provider connection')) as send:
                run=app.state.run_due_followup();self.assertEqual(run['status'],'paused');self.assertEqual(run['result'],'unknown')
                self.assertFalse(app.state.run_due_followup()['processed']);self.assertEqual(send.call_count,1)
            self.assertEqual(client.post(self.base+'/followups/run-local').status_code,404)
            self.assertEqual(client.post(f'/enterprise-api/businesses/{self.bid}/financial-review/pdf',json={'start':datetime.now(timezone.utc).date().isoformat(),'end':datetime.now(timezone.utc).date().isoformat()}).status_code,200)
        with psycopg.connect(self.app_dsn,autocommit=True) as conn:
            for query in ['UPDATE enterprise.order_contacts SET customer_whatsapp=\'spoof\'','DELETE FROM enterprise.reminder_plans','UPDATE enterprise.reminder_plans SET recipient=\'spoof\'','DELETE FROM enterprise.supplier_email_evidence']:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):conn.execute(query)

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
        self.assertEqual(client.get('/customer-invoice').status_code, 200)
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


    def test_postgres_supplier_split_concurrency_and_immutable_bill(self):
        import base64
        from io import BytesIO
        from PIL import Image
        import psycopg
        self.fixture()
        today = datetime.now(timezone(timedelta(hours=1))).date().isoformat()
        bills = self.base + '/supplier-bills'; ids = []
        for index, color in enumerate(['green', 'red']):
            out = BytesIO(); Image.new('RGB', (20, 20), color).save(out, format='PNG')
            response = self.owner.post(bills, json={'vendor': 'Rehearsal Supplier', 'reference': f'SUP-{index}', 'description': 'Fictional office invoice', 'category': 'Supplies', 'amount': '50000.00', 'issued_on': today, 'due_on': today, 'receipt_base64': base64.b64encode(out.getvalue()).decode(), 'idempotency_key': secrets.token_hex(16)})
            self.assertEqual(response.status_code, 201, response.text); ids.append(response.json()['id'])
        ledger = f'/enterprise-api/businesses/{self.bid}/financial-records'
        debit = self.owner.post(ledger, json={'location_id': self.lid, 'direction': 'expense', 'amount': '45000.00', 'occurred_on': today, 'description': 'Fictional supplier debit', 'category': 'Supplies', 'idempotency_key': secrets.token_hex(16)})
        self.assertEqual(debit.status_code, 201, debit.text)
        def allocate(bill):
            client = self.client(); client.cookies.update(self.owner.cookies)
            return client.post(f'{bills}/{bill}/payments', json={'record_id': debit.json()['id'], 'amount': '45000.00', 'reason': 'Rehearsal concurrency check', 'idempotency_key': secrets.token_hex(16)})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(allocate, ids))
        self.assertEqual(sorted(r.status_code for r in responses), [201, 409], [r.text for r in responses])
        self.assertEqual(self.owner.get(bills).json()['outstanding'], '55000.00')
        self.assertEqual(self.owner.get(ledger).json()['count'], 1)
        with psycopg.connect(self.app_dsn, autocommit=True) as conn:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute('UPDATE enterprise.supplier_bills SET amount_minor=1')
        self.assertEqual(self.owner.get(f'/enterprise-api/businesses/{self.bid}/owner-dashboard').json()['totals']['payables'], '55000.00')

    def test_postgres_whatsapp_signed_intake_worker_and_submission(self):
        import base64, hashlib, hmac, json
        from io import BytesIO
        from PIL import Image
        import psycopg
        from workspace_whatsapp import WhatsAppSettings, WEBHOOK
        self.fixture()
        settings = WhatsAppSettings('fake-secret-12345678901234567890', 'fake-verify-12345678901234567890', 'fake-token', 'v99.0', {'1234567890': self.bid})
        from enterprise_production import create_app
        cookies = self.owner.cookies
        with patch('workspace_whatsapp.WhatsAppSettings.from_env', return_value=settings):
            self.app = create_app()
        self.owner = self.client(); self.owner.cookies.update(cookies)
        staff = self.client(); self.register(staff, 'whatsapp-staff@example.test')
        invite = self.owner.post(f'/enterprise-api/businesses/{self.bid}/invitations', json={'email': 'whatsapp-staff@example.test', 'role': 'staff', 'location_id': self.lid}).json()
        staff.post('/enterprise-api/invitations/accept', json={'token': invite['token']})
        inbox = self.base + '/whatsapp'
        code = staff.post(inbox + '/link-code', json={'phone_id': '1234567890'}); self.assertEqual(code.status_code, 200, code.text)
        def deliver(message):
            raw = json.dumps({'object': 'whatsapp_business_account', 'entry': [{'changes': [{'field': 'messages', 'value': {'messaging_product': 'whatsapp', 'metadata': {'phone_number_id': '1234567890'}, 'messages': [message]}}]}]}).encode()
            return TestClient(self.app, base_url='https://workspace.example.test').post(WEBHOOK, content=raw, headers={'x-hub-signature-256': 'sha256=' + hmac.new(settings.secret.encode(), raw, hashlib.sha256).hexdigest()})
        self.assertEqual(deliver({'id': 'wamid.link', 'from': '2348000000000', 'type': 'text', 'text': {'body': code.json()['message']}}).status_code, 200)
        out = BytesIO(); Image.new('RGB', (20, 20), 'blue').save(out, format='PNG'); raw = out.getvalue()
        import time
        response = deliver({'id': 'wamid.receipt', 'from': '2348000000000', 'timestamp': str(int(time.time())), 'type': 'image', 'image': {'id': '98765', 'mime_type': 'image/png', 'sha256': base64.b64encode(hashlib.sha256(raw).digest()).decode()}})
        self.assertEqual(response.status_code, 200, response.text)
        with patch('workspace_whatsapp.download_media', return_value=(raw, 'image/png', 'png')):
            self.assertTrue(self.app.state.process_whatsapp_message())
        message = staff.get(inbox).json()['messages'][0]
        self.assertEqual(message['status'], 'ready')
        today = datetime.now(timezone(timedelta(hours=1))).date().isoformat()
        payload = {'vendor': 'Fictional Store', 'purpose': 'Fictional staff paper', 'category': 'Supplies', 'amount': '1000.10', 'occurred_on': today, 'receipt_base64': base64.b64encode(raw).decode(), 'whatsapp_message_id': message['id'], 'idempotency_key': secrets.token_hex(16)}
        result = staff.post(self.base + '/expenses', json=payload); self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(staff.get(inbox).json()['messages'][0]['status'], 'submitted')
        self.assertEqual(self.owner.get(self.base + '/expenses').json()['expenses'][0]['whatsapp_source']['provider_id'], 'wamid.receipt')
        self.assertEqual(self.owner.post(inbox + '/preview-message', json={'receipt_base64': payload['receipt_base64'], 'idempotency_key': secrets.token_hex(16)}).status_code, 404)
        with psycopg.connect(self.app_dsn, autocommit=True) as conn:
            conn.execute("UPDATE enterprise.whatsapp_messages SET status='queued'")
            with self.assertRaises(psycopg.errors.RaiseException):
                conn.execute("UPDATE enterprise.whatsapp_messages SET receipt='tampered'::bytea")
            conn.execute("UPDATE enterprise.whatsapp_messages SET status='submitted'")


    def test_postgres_customer_notice_send_guard_and_unknown_no_retry(self):
        import time
        _, iid = self.fixture(); today = datetime.now(timezone(timedelta(hours=1))).date().isoformat()
        def credit(amount):
            result = self.owner.post(self.base + '/payments/credits', json={'source_id': secrets.token_hex(16), 'amount': amount, 'occurred_on': today, 'payer': 'Fictional customer', 'narration': 'Rehearsal payment'})
            self.assertEqual(result.status_code, 201, result.text); return result.json()['id']
        def allocation(record, invoice, amount):
            return self.owner.post(self.base + '/payments/allocations', json={'record_id': record, 'invoice_id': invoice, 'amount': amount, 'note': 'Rehearsal confirmed evidence', 'idempotency_key': secrets.token_hex(16)})
        first = credit('20000.00'); self.assertEqual(allocation(first, iid, '20000.00').status_code, 201)
        extra = credit('1000.00'); base = self.base + '/customer-notifications'
        prepared = self.owner.post(base, json={'invoice_id': iid, 'kind': 'partial_payment', 'recipient': 'test-recipient@example.test', 'idempotency_key': secrets.token_hex(16)})
        self.assertEqual(prepared.status_code, 201, prepared.text); nid = prepared.json()['id']
        def guarded_sender(message):
            self.assertIn('NGN 30000.00', message.get_content())
            self.assertEqual(allocation(extra, iid, '1000.00').status_code, 409)
        with patch('workspace_notifications.send_smtp', side_effect=guarded_sender):
            sent = self.owner.post(base + f'/{nid}/send', json={})
        self.assertEqual(sent.status_code, 200, sent.text); self.assertEqual(sent.json()['status'], 'accepted')
        _, second_iid = self.new_invoice(); self.assertEqual(allocation(extra, second_iid, '1000.00').status_code, 201)
        second = self.owner.post(base, json={'invoice_id': second_iid, 'kind': 'partial_payment', 'recipient': 'test-recipient@example.test', 'idempotency_key': secrets.token_hex(16)}).json()['id']
        with patch('workspace_notifications.send_smtp', side_effect=OSError('Fictional uncertain transport')) as sender:
            self.assertEqual(self.owner.post(base + f'/{second}/send', json={}).json()['status'], 'unknown')
            self.assertEqual(self.owner.post(base + f'/{second}/send', json={'confirm_retry': True}).json()['status'], 'unknown')
            self.assertEqual(sender.call_count, 1)

    def test_postgres_insights_exports_and_customer_share_permissions(self):
        from io import BytesIO
        from zipfile import ZipFile
        import json, hashlib, psycopg
        _, iid = self.fixture(); today = datetime.now(timezone(timedelta(hours=1))).date()
        ledger = f'/enterprise-api/businesses/{self.bid}/financial-records'
        for days in [5, 35, 65]:
            response = self.owner.post(ledger, json={'location_id': self.lid, 'direction': 'expense', 'amount': '100.10', 'occurred_on': (today - timedelta(days=days)).isoformat(), 'description': 'Recurring rehearsal hosting', 'category': 'Software', 'idempotency_key': secrets.token_hex(16)})
            self.assertEqual(response.status_code, 201, response.text)
        insights = self.owner.post(f'/enterprise-api/businesses/{self.bid}/financial-insights', json={'available_cash': '1000.00', 'confirm_complete_history': True})
        self.assertEqual(insights.status_code, 200, insights.text)
        self.assertEqual(insights.json()['runway_days'], 100000 * 90 // 30030)
        self.assertEqual(len(insights.json()['recurring_candidates']), 1)
        plan = self.owner.post(f'/enterprise-api/businesses/{self.bid}/recurring-commitments', json={'location_id': self.lid, 'vendor': 'Rehearsal hosting', 'description': 'Tracked monthly service', 'amount': '100.10', 'cadence': 'monthly', 'next_due': today.isoformat(), 'idempotency_key': secrets.token_hex(16)})
        self.assertEqual(plan.status_code, 201, plan.text)
        report = self.owner.post(f'/enterprise-api/businesses/{self.bid}/financial-history/export', json={'start': (today - timedelta(days=90)).isoformat(), 'end': today.isoformat()})
        self.assertEqual(report.status_code, 200, report.text if report.status_code != 200 else '')
        with ZipFile(BytesIO(report.content)) as archive:
            manifest = json.loads(archive.read('manifest.json')); self.assertEqual(manifest['posted_totals']['expenses'], '300.30')
            entry = manifest['evidence'][0]; self.assertEqual(hashlib.sha256(archive.read(entry['path'])).hexdigest(), entry['sha256'])
        shares = self.base + f'/invoices/{iid}/shares'; link = self.owner.post(shares, json={})
        self.assertEqual(link.status_code, 201, link.text); token = link.json()['url'].split('#token=')[1]
        public = self.client().post('/enterprise-api/customer-invoice', json={'token': token})
        self.assertEqual(public.status_code, 200, public.text); self.assertNotIn('allocations', public.json()['payments'])
        self.assertEqual(self.owner.post(shares + f'/{link.json()["id"]}/revoke').status_code, 200)
        self.assertEqual(self.client().post('/enterprise-api/customer-invoice', json={'token': token}).status_code, 404)
        with psycopg.connect(self.app_dsn, autocommit=True) as conn:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute('UPDATE enterprise.recurring_commitments SET amount_minor=1')


if __name__ == '__main__':
    unittest.main()
