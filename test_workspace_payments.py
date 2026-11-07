from datetime import datetime, timedelta, timezone
import unittest
from test_workspace_invoices import InvoiceTests


class PaymentTests(InvoiceTests):
    def setup_payment(self):
        self.setup_invoice()
        self.iid = self.owner.post(self.endpoint, json={}).json()['invoice']['id']
        self.pay = self.base + '/payments'
        self.account_id = self.owner.post(self.pay + '/accounts', json={'name': 'Test Bank', 'account_reference': 'TEST-001'}).json()['id']
        self.owner.put(self.pay + '/invoice-account', json={'invoice_id': self.iid, 'account_id': self.account_id})

    def credit(self, source='source-reference-001', amount='2500.10', **extra):
        return {'account_id': self.account_id, 'source_id': source, 'amount': amount, 'occurred_on': datetime.now(timezone(timedelta(hours=1))).date().isoformat(),
                'payer': 'Test Guest', 'narration': self.owner.get(self.endpoint).json()['invoice']['snapshot']['order_reference'], **extra}

    def allocation(self, rid, amount='2500.10', key='allocation-reference-001', **extra):
        return {'record_id': rid, 'invoice_id': self.iid, 'amount': amount, 'note': 'Checked source and account', 'idempotency_key': key, **extra}

    def test_partial_duplicate_overpayment_reversal_and_ledger_once(self):
        self.setup_payment()
        credit = self.credit()
        rid = self.owner.post(self.pay + '/credits', json=credit).json()['id']
        self.assertEqual(self.owner.post(self.pay + '/credits', json=credit).json()['id'], rid)
        self.assertEqual(self.owner.post(self.pay + '/credits', json={**credit, 'amount': '2500.11'}).status_code, 409)
        allocation = self.allocation(rid)
        result = self.owner.post(self.pay + '/allocations', json=allocation)
        self.assertEqual(result.status_code, 201, result.text)
        aid = result.json()['id']
        self.assertEqual(self.owner.post(self.pay + '/allocations', json=allocation).json()['id'], aid)
        summary = self.owner.get(self.endpoint).json()['invoice']['payments']
        self.assertEqual((summary['status'], summary['allocated'], summary['outstanding']), ('part_paid', '2500.10', '500.20'))
        ledger = self.owner.get(f'/enterprise-api/businesses/{self.bid}/financial-records').json()
        self.assertEqual((ledger['count'], ledger['totals']['income']), (1, '2500.10'))
        self.assertEqual(self.owner.post(self.pay + '/allocations', json=self.allocation(rid, '0.01', 'another-alloc-key-0000')).status_code, 409)
        self.assertEqual(self.owner.post(f'/enterprise-api/businesses/{self.bid}/financial-records/{rid}/void', json={'reason': 'Should fail'}).status_code, 409)
        self.assertEqual(self.owner.post(self.base + f'/orders/{self.oid}/cancel', json={'reason': 'Should fail'}).status_code, 409)
        second = self.owner.post(self.pay + '/credits', json=self.credit('second-source-id', '600.20')).json()['id']
        self.owner.post(self.pay + '/allocations', json=self.allocation(second, '600.20', 'second-allocation-key'))
        summary = self.owner.get(self.endpoint).json()['invoice']['payments']
        self.assertEqual((summary['status'], summary['outstanding'], summary['overpayment']), ('overpaid', '0.00', '100.00'))
        self.assertEqual(self.owner.post(self.pay + f'/allocations/{aid}/reverse', json={'reason': 'Incorrect association'}).status_code, 200)
        self.owner.post(self.pay + f'/allocations/{aid}/reverse', json={'reason': 'Different reason'})
        summary = self.owner.get(self.endpoint).json()['invoice']['payments']
        self.assertEqual(summary['outstanding'], '2400.10')
        self.assertEqual(next(a for a in summary['allocations'] if a['id'] == aid)['reversal_reason'], 'Incorrect association')

    def test_account_and_location_guards_and_ambiguous_matches(self):
        self.setup_payment()
        other_account = self.owner.post(self.pay + '/accounts', json={'name': 'Other Bank', 'account_reference': 'TEST-002'}).json()['id']
        rid = self.owner.post(self.pay + '/credits', json=self.credit(account_id=other_account)).json()['id']
        self.assertEqual(self.owner.post(self.pay + '/allocations', json=self.allocation(rid)).status_code, 409)
        other_oid = self.owner.post(self.base + '/orders', json=self.payload('another-order-key-0000')).json()['id']
        second = self.owner.post(self.base + f'/orders/{other_oid}/invoice', json={}).json()['invoice']
        self.owner.put(self.pay + '/invoice-account', json={'invoice_id': second['id'], 'account_id': self.account_id})
        narration = self.credit()['narration'] + ' ' + second['snapshot']['order_reference']
        rid = self.owner.post(self.pay + '/credits', json=self.credit('ambiguous-credit-id', narration=narration)).json()['id']
        review = self.owner.get(self.pay).json()
        self.assertEqual(len(next(c for c in review['credits'] if c['id'] == rid)['candidates']), 2)
        self.assertEqual(self.owner.get(self.endpoint).json()['invoice']['payments']['allocated'], '0.00')
        foreign = self.pay.replace(self.lid, self.other_lid)
        self.assertEqual(self.owner.post(foreign + '/allocations', json=self.allocation(rid)).status_code, 404)
        self.assertEqual(self.owner.get(foreign).json()['credits'], [])
        for role in ['front_desk', 'staff', 'finance', 'manager']:
            client = self.member(role)
            allowed = role in {'finance', 'manager'}
            self.assertEqual(client.get(self.pay).status_code, 200 if allowed else 403)
            self.assertEqual(client.post(self.pay + '/allocations', json=self.allocation(rid, key=f'allocation-{role}-000')).status_code, 201 if role == 'finance' else 409 if role == 'manager' else 403)
            self.assertEqual(client.get(foreign).status_code, 404 if allowed else 403)

    def test_split_credit_and_cash_without_bank_binding_and_validation(self):
        self.setup_payment()
        credit = self.credit(amount='1000.00', account_id=None)
        rid = self.owner.post(self.pay + '/credits', json=credit).json()['id']
        self.owner.post(self.pay + '/allocations', json=self.allocation(rid, '400.00'))
        second_oid = self.owner.post(self.base + '/orders', json=self.payload('second-cash-order-000')).json()['id']
        second_invoice = self.owner.post(self.base + f'/orders/{second_oid}/invoice', json={}).json()['invoice']['id']
        self.assertEqual(self.owner.post(self.pay + '/allocations', json=self.allocation(rid, '600.00', 'split-allocation-key', invoice_id=second_invoice)).status_code, 201)
        self.assertEqual(self.owner.get(self.pay).json()['credits'][0]['available'], '0.00')
        for extra in [{'amount': '1.001'}, {'amount': '-1'}, {'amount': 'NaN'}, {'occurred_on': '2999-01-01'}, {'currency': 'USD'}]:
            self.assertEqual(self.owner.post(self.pay + '/credits', json={**credit, **extra}).status_code, 422)
        self.assertEqual(self.owner.put(self.pay + '/invoice-account', json={'invoice_id': self.iid, 'account_id': self.account_id}).status_code, 409)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(PaymentTests(name) for name in PaymentTests.__dict__ if name.startswith('test_'))
