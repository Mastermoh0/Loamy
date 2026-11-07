"""Verification and location-ledger integration tests. No external email or financial data."""
from contextlib import closing
import os
import secrets
import smtplib
import sqlite3
from unittest.mock import patch

from fastapi.testclient import TestClient
from enterprise_preview import create_app
from test_enterprise_preview import WorkspaceTests


def load_tests(loader, _tests, _pattern):
    # FeatureTests inherits the original checks; do not run that imported class twice.
    return loader.loadTestsFromTestCase(FeatureTests)


class FeatureTests(WorkspaceTests):
    # Reuse the temporary database/identity helpers and the original regression checks.
    def raw_registration(self, client, email):
        return client.post('/enterprise-api/register', json={'name': 'Preview Person', 'email': email, 'password': 'Test-password-42'})

    def token(self, client):
        response = client.get('/enterprise-api/email/inbox')
        self.assertEqual(response.status_code, 200)
        return response.json()['messages'][0]['verification_url'].split('#verify=')[1]

    def member(self, bid, lid, role, email):
        client = self.client()
        self.register(client, email)
        response = self.owner.post(f'/enterprise-api/businesses/{bid}/invitations', json={'email': email, 'role': role, 'location_id': lid})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(client.post('/enterprise-api/invitations/accept', json={'token': response.json()['token']}).status_code, 200)
        return client

    def record(self, lid, **changes):
        return {'location_id': lid, 'direction': 'income', 'amount': '1000.10', 'occurred_on': '2026-01-01',
                'description': 'Test payment', 'category': 'Sales', 'idempotency_key': secrets.token_hex(16), **changes}

    def test_verification_gate_identity_replay_and_session_rotation(self):
        self.assertEqual(self.raw_registration(self.owner, 'owner@example.test').status_code, 201)
        self.assertFalse(self.owner.get('/enterprise-api/me').json()['user']['verified'])
        self.assertEqual(self.owner.post('/enterprise-api/businesses', json={'name': 'Business', 'location_name': 'Lekki', 'address': 'Test address'}).status_code, 403)
        token = self.token(self.owner)
        another_session = self.client()
        another_session.cookies.update(self.owner.cookies)
        outsider = self.client()
        self.register(outsider, 'outsider@example.test')
        self.assertNotIn(token, outsider.get('/enterprise-api/email/inbox').text)
        self.assertEqual(outsider.post('/enterprise-api/email/verify', json={'token': token}).status_code, 403)
        self.assertEqual(self.owner.post('/enterprise-api/email/verify', json={'token': token}).status_code, 200)
        self.assertTrue(self.owner.get('/enterprise-api/me').json()['user']['verified'])
        self.assertEqual(another_session.get('/enterprise-api/me').status_code, 401)
        self.assertEqual(self.owner.post('/enterprise-api/email/verify', json={'token': token}).status_code, 400)
        self.business(self.owner)

    def test_verification_expiry_resend_and_invitation_gate(self):
        self.register(self.owner, 'owner@example.test')
        bid = self.business(self.owner)
        lid = self.owner.get(f'/enterprise-api/businesses/{bid}').json()['locations'][0]['id']
        staff = self.client()
        self.raw_registration(staff, 'staff@example.test')
        invitation = self.owner.post(f'/enterprise-api/businesses/{bid}/invitations', json={'email': 'staff@example.test', 'role': 'finance', 'location_id': lid}).json()['token']
        self.assertEqual(staff.post('/enterprise-api/invitations/accept', json={'token': invitation}).status_code, 403)
        old = self.token(staff)
        self.assertEqual(staff.post('/enterprise-api/email/request').status_code, 429)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute('UPDATE email_verifications SET expires_at=0,created_at=0 WHERE consumed_at IS NULL')
        self.assertEqual(staff.post('/enterprise-api/email/verify', json={'token': old}).status_code, 400)
        self.assertEqual(staff.post('/enterprise-api/email/request').status_code, 200)
        new = self.token(staff)
        self.assertNotEqual(old, new)
        self.assertEqual(staff.post('/enterprise-api/email/verify', json={'token': old}).status_code, 400)
        self.assertEqual(staff.post('/enterprise-api/email/verify', json={'token': new}).status_code, 200)
        self.assertEqual(staff.post('/enterprise-api/invitations/accept', json={'token': invitation}).status_code, 200)

    def test_ledger_amounts_scope_retry_and_void_history(self):
        self.register(self.owner, 'owner@example.test')
        bid = self.business(self.owner)
        lid = self.owner.get(f'/enterprise-api/businesses/{bid}').json()['locations'][0]['id']
        second = self.owner.post(f'/enterprise-api/businesses/{bid}/locations', json={'name': 'Ikeja', 'address': 'Other address'}).json()['id']
        endpoint = f'/enterprise-api/businesses/{bid}/financial-records'
        payload = self.record(lid)
        first = self.owner.post(endpoint, json=payload)
        self.assertEqual(first.status_code, 201, first.text)
        rid = first.json()['id']
        self.assertTrue(self.owner.post(endpoint, json=payload).json()['duplicate'])
        self.assertEqual(self.owner.post(endpoint, json={**payload, 'amount': '999.00'}).status_code, 409)
        self.owner.post(endpoint, json=self.record(lid, direction='expense', amount='0.10'))
        self.owner.post(endpoint, json=self.record(second, amount='2000.00'))
        all_records = self.owner.get(endpoint).json()
        self.assertEqual(all_records['count'], 3)
        self.assertEqual(all_records['totals'], {'income': '3000.10', 'expenses': '0.10', 'net': '3000.00'})
        local = self.owner.get(endpoint, params={'location_id': lid}).json()
        self.assertEqual(local['count'], 2)
        self.assertEqual(local['totals']['net'], '1000.00')
        finance = self.member(bid, lid, 'finance', 'finance@example.test')
        self.assertEqual(finance.get(endpoint).json()['count'], 2)
        self.assertEqual(finance.get(endpoint, params={'location_id': second}).status_code, 404)
        self.assertEqual(finance.post(endpoint, json=self.record(second)).status_code, 404)
        other_record = next(r['id'] for r in all_records['records'] if r['location_id'] == second)
        self.assertEqual(finance.post(f'{endpoint}/{other_record}/void', json={'reason': 'Wrong location'}).status_code, 404)
        self.assertEqual(finance.post(f'{endpoint}/{rid}/void', json={'reason': 'Duplicate bookkeeping'}).status_code, 200)
        self.assertEqual(finance.post(f'{endpoint}/{rid}/void', json={'reason': 'Repeat request'}).status_code, 200)
        after = self.owner.get(endpoint, params={'location_id': lid}).json()
        self.assertEqual(after['count'], 2)
        self.assertEqual(after['totals']['net'], '-0.10')
        voided = next(r for r in after['records'] if r['id'] == rid)
        self.assertEqual(voided['void_reason'], 'Duplicate bookkeeping')
        self.assertEqual(voided['status'], 'voided')
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('SELECT amount_minor FROM financial_records WHERE id=?', (rid,)).fetchone()[0], 100010)

    def test_financial_role_and_business_boundaries(self):
        self.register(self.owner, 'owner@example.test')
        bid = self.business(self.owner)
        lid = self.owner.get(f'/enterprise-api/businesses/{bid}').json()['locations'][0]['id']
        endpoint = f'/enterprise-api/businesses/{bid}/financial-records'
        for role in ['front_desk', 'staff', 'manager']:
            member = self.member(bid, lid, role, f'{role}@example.test')
            expected_read = 200 if role == 'manager' else 403
            expected_write = 201 if role == 'manager' else 403
            self.assertEqual(member.get(endpoint).status_code, expected_read)
            self.assertEqual(member.post(endpoint, json=self.record(lid)).status_code, expected_write)
        outsider = self.client()
        self.register(outsider, 'outsider@example.test')
        self.assertEqual(outsider.get(endpoint).status_code, 404)
        self.assertEqual(outsider.post(endpoint, json=self.record(lid)).status_code, 404)
        foreign = self.business(outsider)
        foreign_lid = outsider.get(f'/enterprise-api/businesses/{foreign}').json()['locations'][0]['id']
        self.assertEqual(self.owner.post(endpoint, json=self.record(foreign_lid)).status_code, 404)
        for changes in [{'amount': '0'}, {'amount': '-1'}, {'amount': '1.001'}, {'amount': 'NaN'}, {'amount': 'Infinity'}, {'currency': 'USD'}, {'occurred_on': '2999-01-01'}, {'source': 'bank_alert'}, {'actor_id': 'spoof'}, {'location_id': ''}]:
            self.assertEqual(self.owner.post(endpoint, json=self.record(lid, **changes)).status_code, 422, changes)

    def test_smtp_delivery_isolated_from_capture_and_failure_visible(self):
        self.register(self.owner, 'owner@example.test')
        env = {'LOAMY_MAIL_TRANSPORT': 'smtp', 'LOAMY_SMTP_HOST': 'smtp.example.test', 'LOAMY_SMTP_FROM': 'no-reply@example.test',
               'LOAMY_SMTP_USERNAME': 'example', 'LOAMY_SMTP_PASSWORD': 'fake-test-only'}
        with patch.dict(os.environ, env), patch('workspace_email.smtplib.SMTP') as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value = {}
            app = create_app(self.path)
            client = TestClient(app, headers={'Origin': 'http://testserver'})
            client.cookies.update(self.owner.cookies)
            self.assertFalse(client.get('/enterprise-api/me').json()['user']['verified'])
            self.assertEqual(client.get('/enterprise-api/email/inbox').status_code, 404)
            with closing(sqlite3.connect(self.path)) as conn, conn:
                conn.execute('UPDATE email_verifications SET created_at=0')
            self.assertEqual(client.post('/enterprise-api/email/request').status_code, 200)
            smtp.return_value.__enter__.return_value.send_message.assert_called_once()
            with closing(sqlite3.connect(self.path)) as conn:
                row = conn.execute("SELECT body,verification_url,status FROM mail_outbox WHERE transport='smtp'").fetchone()
                self.assertEqual(row, ('', '', 'sent'))
            with closing(sqlite3.connect(self.path)) as conn, conn:
                conn.execute('UPDATE email_verifications SET created_at=0')
            smtp.side_effect = smtplib.SMTPException('test unavailable')
            self.assertEqual(client.post('/enterprise-api/email/request').status_code, 503)
