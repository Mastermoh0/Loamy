"""Consolidation is owner-only and never counts orders/allocations as extra income."""
import unittest
import secrets
from datetime import datetime, timedelta, timezone
from test_workspace_payments import PaymentTests


class OwnerTests(PaymentTests):
    def dashboard(self, **params):
        result = self.owner.get(f'/enterprise-api/businesses/{self.bid}/owner-dashboard', params=params)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_combined_locations_exact_expense_and_cancelled_orders(self):
        self.setup_payment()
        ledger = f'/enterprise-api/businesses/{self.bid}/financial-records'
        today = datetime.now(timezone(timedelta(hours=1))).date().isoformat()
        for lid, direction, amount in [(self.lid, 'income', '0.10'), (self.other_lid, 'income', '2000.20'), (self.other_lid, 'expense', '500.05')]:
            response = self.owner.post(ledger, json={'location_id': lid, 'direction': direction, 'amount': amount, 'occurred_on': today,
                'description': 'Fictional dashboard fixture', 'category': 'Test', 'idempotency_key': secrets.token_hex(16)})
            self.assertEqual(response.status_code, 201, response.text)
        totals = self.dashboard()['totals']
        self.assertEqual((totals['inflow'], totals['outflow'], totals['net']), ('2000.30', '500.05', '1500.25'))
        self.assertEqual(self.dashboard(location_id=self.other_lid)['totals']['net'], '1500.15')
        cancelled = self.owner.post(self.base + f'/orders/{self.oid}/cancel', json={'reason': 'Fictional guest cancellation'})
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        totals = self.dashboard()['totals']
        self.assertEqual((totals['open_orders'], totals['cancelled_orders'], totals['order_value'], totals['outstanding']), (0, 1, '0.00', '0.00'))
        self.assertEqual(totals['inflow'], '2000.30')

    def test_exact_consolidation_reversal_void_and_empty_location(self):
        self.setup_payment()
        rid = self.owner.post(self.pay + '/credits', json=self.credit()).json()['id']
        aid = self.owner.post(self.pay + '/allocations', json=self.allocation(rid)).json()['id']
        result = self.dashboard()
        self.assertEqual((result['totals']['inflow'], result['totals']['outstanding'], result['totals']['order_value']), ('2500.10', '500.20', '3000.30'))
        self.assertEqual(result['totals']['records'], 1)
        empty = next(l for l in result['locations'] if l['id'] == self.other_lid)
        self.assertEqual((empty['net'], empty['outstanding']), ('0.00', '0.00'))
        self.assertEqual(result['accounts'][0]['recorded_credits'], '2500.10')
        self.assertIsNone(result['accounts'][0]['bank_balance'])
        self.owner.post(self.pay + f'/allocations/{aid}/reverse', json={'reason': 'Wrong allocation'})
        self.assertEqual(self.dashboard()['totals']['outstanding'], '3000.30')
        self.owner.post(f'/enterprise-api/businesses/{self.bid}/financial-records/{rid}/void', json={'reason': 'Incorrect credit'})
        self.assertEqual(self.dashboard()['totals']['inflow'], '0.00')
        self.assertEqual(self.dashboard(location_id=self.other_lid)['totals']['orders'], 0)

    def test_owner_boundaries_and_period_does_not_hide_receivables(self):
        self.setup_payment()
        url = f'/enterprise-api/businesses/{self.bid}/owner-dashboard'
        for role in ['manager', 'finance', 'staff']:
            self.assertEqual(self.member(role).get(url).status_code, 403)
        outsider = self.client(); self.register(outsider, 'outsider@example.test')
        self.assertEqual(outsider.get(url).status_code, 404)
        self.assertEqual(self.owner.get(url, params={'location_id': 'other-location'}).status_code, 404)
        self.assertEqual(self.owner.get(url, params={'start': '2020-01-01', 'end': '2026-01-01'}).status_code, 422)
        self.assertEqual(self.owner.get(url, params={'start': '2026-02-01', 'end': '2026-01-01'}).status_code, 422)
        historical = self.dashboard(start='2020-01-01', end='2020-01-02')
        self.assertEqual(historical['totals']['orders'], 0)
        self.assertEqual(historical['totals']['outstanding'], '3000.30')


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(OwnerTests(name) for name in OwnerTests.__dict__ if name.startswith('test_'))
