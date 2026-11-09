"""Exact adjustment rounding, immutable invoices and permission/stale-setting guards."""
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO, StringIO
import sqlite3
from contextlib import closing
from zipfile import ZipFile
from test_workspace_orders import OrderTests
from workspace_pricing import calculate


class PricingTests(OrderTests):
    def test_adjusted_invoice_balances_export_and_immutable_history(self):
        self.setup_orders()
        self.assertEqual(self.owner.put(self.base + '/pricing', json={'tax_label': 'Test VAT', 'tax_rate': '7.50'}).status_code, 200)
        payload = {**self.payload(), 'expected_tax_rate': '7.50', 'discount_type': 'percent', 'discount_value': '10.00', 'discount_reason': 'Seasonal offer'}
        response = self.owner.post(self.base + '/orders', json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        oid = response.json()['id']; endpoint = self.base + f'/orders/{oid}/invoice'
        self.assertEqual(self.owner.post(self.base + '/orders', json=payload).json()['id'], oid)
        order = self.owner.get(self.base + f'/orders/{oid}').json()
        self.assertEqual((order['pricing']['subtotal'], order['pricing']['discount'], order['pricing']['tax'], order['total']), ('3000.30', '300.03', '202.52', '2902.79'))
        self.owner.put(self.base + '/pricing', json={'tax_label': 'Changed tax', 'tax_rate': '20'})
        invoice = self.owner.post(endpoint, json={}).json()['invoice']
        self.assertEqual(invoice['snapshot']['pricing'], order['pricing'])
        self.assertEqual(invoice['payments']['outstanding'], '2902.79')
        pdf = self.owner.get(endpoint + '/pdf').content
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.owner.put(self.base + '/pricing', json={'tax_label': 'Disabled tax', 'tax_rate': '0'})
        self.assertEqual(self.owner.get(endpoint + '/pdf').content, pdf)
        pay = self.base + '/payments'
        aid = self.owner.post(pay + '/accounts', json={'name': 'Test account', 'account_reference': 'TEST-TAX'}).json()['id']
        self.owner.put(pay + '/invoice-account', json={'invoice_id': invoice['id'], 'account_id': aid})
        today = datetime.now(timezone(timedelta(hours=1))).date().isoformat()
        rid = self.owner.post(pay + '/credits', json={'account_id': aid, 'source_id': 'tax-test-credit-0001', 'amount': '1000', 'occurred_on': today, 'payer': 'Test Guest', 'narration': order['reference']}).json()['id']
        allocated = self.owner.post(pay + '/allocations', json={'record_id': rid, 'invoice_id': invoice['id'], 'amount': '1000', 'note': 'Checked payment', 'idempotency_key': 'tax-allocation-00001'})
        self.assertEqual(allocated.status_code, 201, allocated.text)
        self.assertEqual(self.owner.get(endpoint).json()['invoice']['payments']['outstanding'], '1902.79')
        result = self.owner.post(f'/enterprise-api/businesses/{self.bid}/financial-history/export', json={'start': today, 'end': today, 'include_evidence': True})
        self.assertEqual(result.status_code, 200, result.text if result.status_code != 200 else '')
        with ZipFile(BytesIO(result.content)) as archive:
            row = list(csv.DictReader(StringIO(archive.read('current-invoice-balances.csv').decode('utf-8-sig'))))[0]
            self.assertEqual((row['subtotal'], row['discount'], row['tax'], row['total'], row['outstanding']), ('3000.30', '300.03', '202.52', '2902.79', '1902.79'))
        self.assertEqual(self.owner.get(f'/enterprise-api/businesses/{self.bid}/financial-records').json()['count'], 1)

    def test_validation_roles_stale_settings_and_legacy_orders(self):
        self.setup_orders()
        payload = self.payload()
        oid = self.owner.post(self.base + '/orders', json=payload).json()['id']
        # An upgrade must still recover a retry saved with the old input hash.
        import hashlib, json
        with closing(sqlite3.connect(self.path)) as conn, conn:
            old = hashlib.sha256(json.dumps({k: v for k, v in payload.items() if k != 'idempotency_key'}, sort_keys=True).encode()).hexdigest()
            conn.execute('UPDATE orders SET request_hash=? WHERE id=?', (old, oid))
            conn.execute('DELETE FROM order_pricing WHERE order_id=?', (oid,))
        self.assertTrue(self.owner.post(self.base + '/orders', json=payload).json()['duplicate'])
        self.assertEqual(self.owner.get(self.base + f'/orders/{oid}').json()['pricing']['subtotal'], '3000.30')
        self.owner.put(self.base + '/pricing', json={'tax_label': 'Test tax', 'tax_rate': '7.50'})
        self.assertEqual(self.owner.post(self.base + '/orders', json=self.payload('stale-tax-order-0001')).status_code, 409)
        for values in [{'discount_type': 'fixed', 'discount_value': '3000.30', 'discount_reason': 'Too much'}, {'discount_type': 'percent', 'discount_value': '100.01', 'discount_reason': 'Too much'}, {'discount_type': 'fixed', 'discount_value': '1', 'discount_reason': ''}, {'discount_type': 'none', 'discount_value': '1'}, {'discount_value': 'NaN'}, {'discount_value': '0.001'}]:
            bad = {**self.payload('invalid-tax-order-001'), 'expected_tax_rate': '7.50', **values}
            self.assertEqual(self.owner.post(self.base + '/orders', json=bad).status_code, 422, values)
        for tax in ['-1', '100.01', '0.001', 'NaN', 'Infinity']:
            self.assertEqual(self.owner.put(self.base + '/pricing', json={'tax_label': 'Test tax', 'tax_rate': tax}).status_code, 422)
        for role in ['manager', 'front_desk', 'finance', 'staff']:
            member = self.member(role)
            self.assertEqual(member.put(self.base + '/pricing', json={'tax_label': 'Test tax', 'tax_rate': '7.50'}).status_code, 200 if role == 'manager' else 403)
            discounted = {**self.payload('discount-for-' + role), 'expected_tax_rate': '7.50', 'discount_type': 'fixed', 'discount_value': '0.10', 'discount_reason': 'Approved offer'}
            self.assertEqual(member.post(self.base + '/orders', json=discounted).status_code, 201 if role == 'manager' else 403)
            self.assertEqual(member.put(self.base.replace(self.lid, self.other_lid) + '/pricing', json={'tax_label': 'Test tax', 'tax_rate': '1'}).status_code, 404 if role == 'manager' else 403)
        front = self.client(); front.post('/enterprise-api/login', json={'email': 'front_desk@example.test', 'password': 'Test-password-42'})
        self.assertEqual(front.post(self.base + '/orders', json={**self.payload('front-tax-order-0001'), 'expected_tax_rate': '7.50'}).status_code, 201)

    def test_half_up_rounding_fixed_and_percentage(self):
        self.assertEqual(calculate(10, 'percent', Decimal('5'), 0), (1, 0, 9))
        self.assertEqual(calculate(10, 'none', Decimal('0'), 500), (0, 1, 11))
        self.assertEqual(calculate(300030, 'fixed', Decimal('100.10'), 750), (10010, 21752, 311772))


def load_tests(loader, tests, pattern):
    return loader.loadTestsFromNames(['test_adjusted_invoice_balances_export_and_immutable_history', 'test_validation_roles_stale_settings_and_legacy_orders', 'test_half_up_rounding_fixed_and_percentage'], PricingTests)
