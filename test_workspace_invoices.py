"""Invoice identity/snapshots, PDF downloads, deduplicated delivery and access checks."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import smtplib
import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from enterprise_preview import create_app
from test_workspace_orders import OrderTests
from workspace_invoices import render_invoice


class InvoiceTests(OrderTests):
    def setup_invoice(self):
        self.setup_orders()
        self.oid = self.owner.post(self.base + '/orders', json=self.payload()).json()['id']
        self.endpoint = self.base + '/orders/' + self.oid + '/invoice'

    def email(self, key='invoice-email-key-0001', recipient='guest@example.test'):
        return {'recipient': recipient, 'idempotency_key': key}

    def test_invoice_identity_pdf_snapshot_and_cancel(self):
        self.setup_invoice()
        self.assertIsNone(self.owner.get(self.endpoint).json()['invoice'])
        response = self.owner.post(self.endpoint, json={})
        self.assertEqual(response.status_code, 201, response.text)
        invoice = response.json()['invoice']
        self.assertEqual(invoice['status'], 'issued')
        self.assertEqual(invoice['payment_status'], 'unpaid')
        self.assertEqual(invoice['snapshot']['total'], '3000.30')
        self.assertEqual(invoice['snapshot']['customer_name'], 'Test Guest')
        again = self.owner.post(self.endpoint, json={}).json()
        self.assertTrue(again['duplicate'])
        self.assertEqual(again['invoice']['id'], invoice['id'])
        due = (datetime.now(timezone(timedelta(hours=1))) + timedelta(days=10)).date().isoformat()
        self.assertEqual(self.owner.post(self.endpoint, json={'due_on': due}).status_code, 409)
        pdf = self.owner.get(self.endpoint + '/pdf')
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b'%PDF-'))
        self.assertEqual(pdf.headers['content-type'], 'application/pdf')
        self.owner.put(self.base + f'/services/{self.sid}', json={**self.service, 'price': '9999.00'})
        self.owner.put(self.base + '/profile', json={'invoice_name': 'Changed Business', 'address': 'Changed Address'})
        self.assertEqual(self.owner.get(self.endpoint + '/pdf').content, pdf.content)
        restarted = TestClient(create_app(self.path), headers={'Origin': 'http://testserver'})
        restarted.cookies.update(self.owner.cookies)
        self.assertEqual(restarted.get(self.endpoint).json()['invoice']['id'], invoice['id'])
        self.owner.post(self.base + f'/orders/{self.oid}/cancel', json={'reason': 'Guest cancelled'})
        self.assertEqual(self.owner.get(self.endpoint).json()['invoice']['status'], 'cancelled')
        self.assertNotEqual(self.owner.get(self.endpoint + '/pdf').content, pdf.content)
        self.assertEqual(self.owner.post(self.endpoint + '/email', json=self.email()).status_code, 409)
        self.assertEqual(self.owner.get(f'/enterprise-api/businesses/{self.bid}/financial-records').json()['count'], 0)

    def test_capture_delivery_retry_and_validation(self):
        self.setup_invoice()
        self.owner.post(self.endpoint, json={})
        response = self.owner.post(self.endpoint + '/email', json=self.email())
        self.assertEqual(response.status_code, 200, response.text)
        delivery = response.json()
        self.assertEqual(delivery['status'], 'captured')
        again = self.owner.post(self.endpoint + '/email', json=self.email()).json()
        self.assertEqual(delivery['delivery_id'], again['delivery_id'])
        self.assertTrue(again['duplicate'])
        self.assertEqual(self.owner.post(self.endpoint + '/email', json=self.email(recipient='changed@example.test')).status_code, 409)
        self.assertEqual(self.owner.post(self.endpoint + '/email', json=self.email('another-email-key-0000')).status_code, 429)
        history = self.owner.get(self.endpoint).json()['invoice']['deliveries']
        self.assertEqual(len(history), 1)
        self.assertIn('3000.30', history[0]['body'])
        attachment = self.endpoint + f'/email/{delivery["delivery_id"]}/attachment'
        self.assertEqual(self.owner.get(attachment).content, self.owner.get(self.endpoint + '/pdf').content)
        self.assertEqual(self.owner.get(self.endpoint + '/email/missing/attachment').status_code, 404)
        for recipient in ['not-an-email', 'a@example.test,b@example.test', 'a@example.test\r\nBcc: x@y.test', 'Name <a@example.test>']:
            self.assertEqual(self.owner.post(self.endpoint + '/email', json=self.email(recipient=recipient)).status_code, 422)
        self.assertEqual(self.owner.post(self.endpoint + '/email', json={**self.email(), 'actor_id': 'spoof'}).status_code, 422)
        original = self.owner.get(attachment).content
        self.owner.post(self.base + f'/orders/{self.oid}/cancel', json={'reason': 'Cancelled after capture'})
        self.assertEqual(self.owner.get(attachment).content, original)
        self.assertNotEqual(self.owner.get(self.endpoint + '/pdf').content, original)

    def test_invoice_role_location_and_business_boundaries(self):
        self.setup_invoice()
        self.owner.post(self.endpoint, json={})
        for role in ['manager', 'front_desk', 'finance', 'staff']:
            client = self.member(role)
            readable = role != 'staff'
            writable = role in {'manager', 'front_desk'}
            self.assertEqual(client.get(self.endpoint).status_code, 200 if readable else 403)
            self.assertEqual(client.get(self.endpoint + '/pdf').status_code, 200 if readable else 403)
            self.assertEqual(client.post(self.endpoint, json={}).status_code, 201 if writable else 403)
            self.assertEqual(client.post(self.endpoint + '/email', json=self.email(f'email-for-{role}-0000')).status_code, (200 if role == 'manager' else 429) if writable else 403)
            foreign = self.endpoint.replace(self.lid, self.other_lid)
            self.assertEqual(client.get(foreign).status_code, 404 if readable else 403)
            self.assertEqual(client.get(foreign + '/pdf').status_code, 404 if readable else 403)
        outsider = self.client()
        self.register(outsider, 'outsider@example.test')
        self.assertEqual(outsider.get(self.endpoint).status_code, 404)
        self.assertEqual(outsider.post(self.endpoint, json={}).status_code, 404)
        unverified = self.client()
        unverified.post('/enterprise-api/register', json={'name': 'Unverified User', 'email': 'unverified@example.test', 'password': 'Test-password-42'})
        self.assertEqual(unverified.get(self.endpoint + '/pdf').status_code, 403)

    def test_smtp_attachment_deduplication_failure_and_uncertainty(self):
        self.setup_invoice()
        self.owner.post(self.endpoint, json={})
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE users SET verification_method='smtp'")
        env = {'LOAMY_MAIL_TRANSPORT': 'smtp', 'LOAMY_SMTP_HOST': 'smtp.example.test', 'LOAMY_SMTP_FROM': 'no-reply@example.test',
               'LOAMY_SMTP_USERNAME': 'test', 'LOAMY_SMTP_PASSWORD': 'fake-test-only'}
        with patch.dict(os.environ, env), patch('workspace_email.smtplib.SMTP') as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value = {}
            client = TestClient(create_app(self.path), headers={'Origin': 'http://testserver'})
            client.cookies.update(self.owner.cookies)
            sent = client.post(self.endpoint + '/email', json=self.email())
            self.assertEqual(sent.json()['status'], 'accepted', sent.text)
            same = client.post(self.endpoint + '/email', json=self.email())
            self.assertTrue(same.json()['duplicate'])
            sender = smtp.return_value.__enter__.return_value
            sender.send_message.assert_called_once()
            message = sender.send_message.call_args.args[0]
            self.assertEqual(message['To'], 'guest@example.test')
            attachment = list(message.iter_attachments())[0]
            self.assertEqual(attachment.get_content_type(), 'application/pdf')
            self.assertEqual(attachment.get_payload(decode=True), client.get(self.endpoint + '/pdf').content)
            with closing(sqlite3.connect(self.path)) as conn, conn:
                self.assertEqual(conn.execute("SELECT body FROM invoice_deliveries WHERE transport='smtp'").fetchone()[0], '')
                conn.execute('UPDATE invoice_deliveries SET created_at=0')
            smtp.side_effect = OSError('simulated timeout after possible acceptance')
            uncertain = client.post(self.endpoint + '/email', json=self.email('uncertain-email-key-0000'))
            self.assertEqual(uncertain.json()['status'], 'unknown')
            calls = smtp.call_count
            client.post(self.endpoint + '/email', json=self.email('uncertain-email-key-0000'))
            self.assertEqual(smtp.call_count, calls)
            with closing(sqlite3.connect(self.path)) as conn, conn:
                conn.execute('UPDATE invoice_deliveries SET created_at=0')
            smtp.side_effect = smtplib.SMTPAuthenticationError(535, b'test bad credentials')
            self.assertEqual(client.post(self.endpoint + '/email', json=self.email('failed-email-key-0000')).json()['status'], 'failed')

    def test_due_date_cancelled_order_and_inflight_delivery(self):
        self.setup_invoice()
        yesterday = (datetime.now(timezone(timedelta(hours=1))) - timedelta(days=1)).date().isoformat()
        self.assertEqual(self.owner.post(self.endpoint, json={'due_on': yesterday}).status_code, 422)
        tomorrow = (datetime.now(timezone(timedelta(hours=1))) + timedelta(days=1)).date().isoformat()
        self.assertEqual(self.owner.post(self.endpoint, json={'due_on': tomorrow}).status_code, 201)
        self.owner.post(self.endpoint + '/email', json=self.email())
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE invoice_deliveries SET status='sending'")
        self.assertEqual(self.owner.post(self.base + f'/orders/{self.oid}/cancel', json={'reason': 'Wait for sending'}).status_code, 409)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute('UPDATE invoice_deliveries SET created_at=0')
        self.assertEqual(self.owner.get(self.endpoint).json()['invoice']['deliveries'][0]['status'], 'unknown')
        self.assertEqual(self.owner.post(self.base + f'/orders/{self.oid}/cancel', json={'reason': 'Cancelled after checking'}).status_code, 200)
        oid = self.owner.post(self.base + '/orders', json=self.payload('new-cancelled-order-0000')).json()['id']
        self.owner.post(self.base + f'/orders/{oid}/cancel', json={'reason': 'Cancelled before invoice'})
        self.assertEqual(self.owner.post(self.base + f'/orders/{oid}/invoice', json={}).status_code, 409)

    def test_pdf_long_content_pagination_and_escaping(self):
        snapshot = {'number': 'INV-LAYOUT-TEST', 'profile': {'invoice_name': 'Palm House Test Business', 'address': '1 Example Road, Lagos', 'payment_instructions': 'Test bank instructions\n' + 'Payment notes ' * 60},
                    'location_name': 'Lekki', 'order_reference': 'ORD-' + 'A' * 32, 'issued_on': '2026-11-07', 'due_on': None,
                    'customer_name': '<Test & Guest>', 'customer_contact': 'guest@example.test', 'total': '2000.20',
                    'lines': [{'name': f'Test service {i+1}', 'description': 'Detailed description & <literal text> ' * 10, 'quantity': 1, 'unit_price': '100.01', 'total': '100.01'} for i in range(20)]}
        pdf = render_invoice(snapshot)
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertGreater(len(pdf), 10000)
        # Optional local evidence output, separate from all application data.
        if os.getenv('LOAMY_PDF_EVIDENCE') == '1':
            target = Path(__file__).resolve().parent.parent / 'output' / 'pdf'
            target.mkdir(parents=True, exist_ok=True)
            (target / 'invoice-layout-test.pdf').write_bytes(pdf)


def load_tests(loader, tests, pattern):
    names = [name for name in InvoiceTests.__dict__ if name.startswith('test_')]
    return unittest.TestSuite(InvoiceTests(name) for name in names)


if __name__ == '__main__':
    unittest.main()
