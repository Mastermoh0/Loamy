"""Customer notices are reviewed, current, scoped and deduplicated; links are capabilities."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import sqlite3
import time
import unittest
from unittest.mock import patch
from test_workspace_payments import PaymentTests


class NotificationTests(PaymentTests):
    def setup_notices(self):
        self.setup_payment(); self.notices = self.base + '/customer-notifications'; self.shares = self.base + f'/invoices/{self.iid}/shares'
        self.rid = self.owner.post(self.pay + '/credits', json=self.credit()).json()['id']
        self.aid = self.owner.post(self.pay + '/allocations', json=self.allocation(self.rid)).json()['id']

    def prepare(self, **changes):
        return self.owner.post(self.notices, json={'invoice_id': self.iid, 'kind': 'partial_payment', 'recipient': 'guest@example.test', 'idempotency_key': 'notice-reference-0001', **changes})

    def test_partial_draft_capture_exact_values_dedup_and_cooldown(self):
        self.setup_notices(); response = self.prepare(); self.assertEqual(response.status_code, 201, response.text)
        nid = response.json()['id']
        self.assertEqual(self.prepare().json()['id'], nid)
        self.assertEqual(self.prepare(idempotency_key='notice-reference-0002').json()['id'], nid)
        draft = self.owner.get(self.notices).json()['history'][0]
        self.assertEqual(draft['status'], 'draft'); self.assertIn('NGN 500.20', draft['body'])
        sent = self.owner.post(f'{self.notices}/{nid}/send', json={})
        self.assertEqual(sent.status_code, 200, sent.text); self.assertEqual(sent.json()['status'], 'captured')
        self.assertTrue(self.owner.post(f'{self.notices}/{nid}/send', json={}).json()['duplicate'])
        second = self.prepare(recipient='other@example.test', idempotency_key='notice-reference-0003').json()['id']
        self.assertEqual(self.owner.post(f'{self.notices}/{second}/send', json={}).status_code, 429)
        self.assertEqual(self.owner.get(f'/enterprise-api/businesses/{self.bid}/financial-records').json()['count'], 1)

    def test_stale_paid_or_reversed_balances_cannot_be_sent(self):
        self.setup_notices(); nid = self.prepare().json()['id']
        extra = self.owner.post(self.pay + '/credits', json=self.credit('changed-balance-credit', '10.00')).json()['id']
        added = self.owner.post(self.pay + '/allocations', json=self.allocation(extra, '10.00', 'changed-balance-alloc')).json()['id']
        changed = self.owner.post(f'{self.notices}/{nid}/send', json={})
        self.assertEqual(changed.status_code, 409); self.assertIn('balance changed', changed.text)
        self.owner.post(self.pay + f'/allocations/{self.aid}/reverse', json={'reason': 'Wrong customer allocation'})
        self.owner.post(self.pay + f'/allocations/{added}/reverse', json={'reason': 'Reverse second test allocation'})
        self.assertEqual(self.owner.post(f'{self.notices}/{nid}/send', json={}).status_code, 409)
        self.assertEqual(self.prepare(kind='overdue', idempotency_key='overdue-reference-test').status_code, 409)
        self.assertEqual(self.owner.get(self.notices).json()['candidates'], [])

    def test_failed_retry_requires_explicit_confirmation_and_wait(self):
        self.setup_notices(); nid = self.prepare().json()['id']
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("UPDATE customer_notices SET status='failed',updated_at=? WHERE id=?", (time.time(), nid)); conn.commit()
        self.assertEqual(self.owner.post(f'{self.notices}/{nid}/send', json={}).status_code, 409)
        self.assertEqual(self.owner.post(f'{self.notices}/{nid}/send', json={'confirm_retry': True}).status_code, 429)
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('UPDATE customer_notices SET updated_at=? WHERE id=?', (time.time() - 61, nid)); conn.commit()
        self.assertEqual(self.owner.post(f'{self.notices}/{nid}/send', json={'confirm_retry': True}).json()['status'], 'captured')

    def test_live_send_guard_and_delivery_uncertainty_never_retries(self):
        self.setup_notices(); nid = self.prepare().json()['id']
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("UPDATE customer_notices SET status='sending',updated_at=? WHERE id=?", (time.time(), nid)); conn.commit()
        self.assertEqual(self.owner.post(self.pay + f'/allocations/{self.aid}/reverse', json={'reason': 'Wait for notice'}).status_code, 409)
        extra = self.owner.post(self.pay + '/credits', json=self.credit('another-credit', '10.00')).json()['id']
        self.assertEqual(self.owner.post(self.pay + '/allocations', json=self.allocation(extra, '10.00', 'guarded-allocation-key')).status_code, 409)
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('UPDATE customer_notices SET updated_at=? WHERE id=?', (time.time() - 121, nid)); conn.commit()
        self.assertEqual(self.owner.get(self.notices).json()['history'][0]['status'], 'unknown')
        self.assertEqual(self.owner.post(f'{self.notices}/{nid}/send', json={'confirm_retry': True}).json()['status'], 'unknown')

    def test_overdue_clock_and_role_location_isolation(self):
        self.setup_notices()
        today = datetime.now(timezone(timedelta(hours=1))).date()
        with closing(sqlite3.connect(self.path)) as conn:
            # Fixture represents a previously issued due date; no public API rewrites it.
            conn.execute('UPDATE invoices SET due_on=? WHERE id=?', ((today - timedelta(days=1)).isoformat(), self.iid)); conn.commit()
        response = self.prepare(kind='overdue'); self.assertEqual(response.status_code, 201, response.text)
        self.assertIn('Overdue payment reminder', self.owner.get(self.notices).json()['history'][0]['subject'])
        self.assertEqual(self.member('staff').get(self.notices).status_code, 403)
        finance = self.member('finance'); self.assertEqual(finance.get(self.notices).status_code, 200)
        self.assertEqual(finance.get(self.notices.replace(self.lid, self.other_lid)).status_code, 404)
        self.assertEqual(self.prepare(recipient='a@example.test\nBcc: bad@example.test').status_code, 422)

    def test_share_scoped_expiry_revocation_public_pdf_and_private_fields(self):
        self.setup_notices(); result = self.owner.post(self.shares, json={'expires_days': 7})
        self.assertEqual(result.status_code, 201, result.text)
        share = result.json(); token = share['url'].split('#token=')[1]
        outsider = self.client()
        public = outsider.post('/enterprise-api/customer-invoice', json={'token': token})
        self.assertEqual(public.status_code, 200, public.text)
        self.assertEqual(public.json()['payments']['outstanding'], '500.20')
        self.assertNotIn('allocations', public.json()['payments'])
        self.assertTrue(outsider.post('/enterprise-api/customer-invoice/pdf', json={'token': token}).content.startswith(b'%PDF'))
        self.assertNotIn(token, self.owner.get(self.shares).text)
        self.assertEqual(outsider.get(self.shares).status_code, 401)
        self.owner.post(self.shares + f'/{share["id"]}/revoke')
        self.assertEqual(outsider.post('/enterprise-api/customer-invoice', json={'token': token}).status_code, 404)
        expired = self.owner.post(self.shares, json={'expires_days': 1}).json()
        with patch('workspace_notifications.time.time', return_value=time.time() + 86401):
            self.assertEqual(outsider.post('/enterprise-api/customer-invoice', json={'token': expired['url'].split('#token=')[1]}).status_code, 404)

    def test_cancelled_invoice_link_refuses_access_and_cancel_guard(self):
        self.setup_notices(); share = self.owner.post(self.shares, json={}).json(); token = share['url'].split('#token=')[1]
        nid = self.prepare().json()['id']; self.owner.post(self.pay + f'/allocations/{self.aid}/reverse', json={'reason': 'Fixture correction'})
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("UPDATE customer_notices SET status='sending',updated_at=? WHERE id=?", (time.time(), nid)); conn.commit()
        self.assertEqual(self.owner.post(self.base + f'/orders/{self.oid}/cancel', json={'reason': 'Wait for message'}).status_code, 409)
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("UPDATE customer_notices SET status='failed' WHERE id=?", (nid,)); conn.commit()
        self.assertEqual(self.owner.post(self.base + f'/orders/{self.oid}/cancel', json={'reason': 'Guest cancelled'}).status_code, 200)
        self.assertEqual(self.client().post('/enterprise-api/customer-invoice', json={'token': token}).status_code, 410)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(NotificationTests(name) for name in NotificationTests.__dict__ if name.startswith('test_'))
