"""Bills owed stay separate from cash; allocations only reuse recorded expense debits."""
from datetime import datetime, timedelta, timezone
import secrets
import unittest
from test_workspace_expenses import ExpenseTests


class SupplierTests(ExpenseTests):
    def setup_bills(self):
        self.setup_expenses(); self.bills = self.base + '/supplier-bills'
        self.ledger = f'/enterprise-api/businesses/{self.bid}/financial-records'
        self.today = datetime.now(timezone(timedelta(hours=1))).date().isoformat()

    def bill(self, **extra):
        return {'vendor': 'Test Supplier', 'reference': 'SUP-001', 'description': 'Paper invoice for office', 'category': 'Supplies',
                'amount': '1000.10', 'issued_on': self.today, 'due_on': self.today, 'receipt_base64': self.receipt(), 'idempotency_key': 'supplier-import-reference', **extra}

    def import_bill(self, **extra):
        response = self.owner.post(self.bills, json=self.bill(**extra))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def debit(self, amount='600.05', **extra):
        response = self.owner.post(self.ledger, json={'location_id': self.lid, 'direction': 'expense', 'amount': amount, 'occurred_on': self.today,
            'description': 'Fictional supplier payment', 'category': 'Supplies', 'idempotency_key': secrets.token_hex(16), **extra})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def allocate(self, bill, record, amount='600.05', **extra):
        return self.owner.post(f'{self.bills}/{bill}/payments', json={'record_id': record, 'amount': amount, 'reason': 'Checked supplier payment evidence', 'idempotency_key': 'supplier-payment-reference', **extra})

    def test_import_snapshot_dedup_download_and_no_cash_posting(self):
        self.setup_bills(); bill = self.import_bill()
        self.assertEqual(self.import_bill(), bill)
        for extra in [{'amount': '1000.11'}, {'vendor': 'test supplier', 'idempotency_key': 'another-import-reference'}, {'reference': 'SUP-002', 'idempotency_key': 'another-import-reference'}]:
            self.assertEqual(self.owner.post(self.bills, json=self.bill(**extra)).status_code, 409)
        result = self.owner.get(self.bills).json()
        self.assertEqual((result['outstanding'], result['bills'][0]['payment_status']), ('1000.10', 'unpaid'))
        self.assertEqual(self.owner.get(self.ledger).json()['count'], 0)
        dashboard = self.owner.get(f'/enterprise-api/businesses/{self.bid}/owner-dashboard').json()['totals']
        self.assertEqual((dashboard['payables'], dashboard['outflow']), ('1000.10', '0.00'))
        original = self.owner.get(f'{self.bills}/{bill}/invoice')
        self.assertEqual(original.headers['content-type'], 'application/octet-stream')
        self.assertTrue(original.content.startswith(b'\x89PNG'))

    def test_partial_paid_reversal_void_guards_and_original_debit_once(self):
        self.setup_bills(); bill = self.import_bill(); record = self.debit()
        payment = self.allocate(bill, record); self.assertEqual(payment.status_code, 201, payment.text)
        self.assertEqual(self.allocate(bill, record).json()['id'], payment.json()['id'])
        self.assertEqual(self.allocate(bill, record, amount='0.01', idempotency_key='different-payment-reference').status_code, 409)
        listed = self.owner.get(self.bills).json()['bills'][0]
        self.assertEqual((listed['paid'], listed['outstanding'], listed['payment_status']), ('600.05', '400.05', 'part_paid'))
        self.assertEqual(self.owner.post(self.ledger + f'/{record}/void', json={'reason': 'Invalid while allocated'}).status_code, 409)
        self.assertEqual(self.owner.post(f'{self.bills}/{bill}/void', json={'reason': 'Invalid while allocated'}).status_code, 409)
        second = self.debit('400.05'); self.assertEqual(self.allocate(bill, second, '400.05', idempotency_key='second-payment-reference').status_code, 201)
        self.assertEqual(self.owner.get(self.bills).json()['bills'][0]['payment_status'], 'paid')
        self.assertEqual(self.owner.get(self.ledger).json()['totals']['expenses'], '1000.10')
        path = f'{self.bills}/{bill}/payments/{payment.json()["id"]}/reverse'
        self.assertEqual(self.owner.post(path, json={'reason': 'Wrong supplier association'}).status_code, 200)
        self.owner.post(path, json={'reason': 'Do not rewrite original reason'})
        self.assertEqual(self.owner.get(self.bills).json()['bills'][0]['payments'][0]['reverse_reason'], 'Wrong supplier association')
        self.assertEqual(self.owner.post(self.ledger + f'/{record}/void', json={'reason': 'Incorrect paid debit'}).status_code, 200)
        self.assertEqual(self.owner.get(self.bills).json()['outstanding'], '600.05')

    def test_split_debit_cannot_be_spent_twice_or_accept_income_foreign_location(self):
        self.setup_bills(); bill = self.import_bill(); second = self.import_bill(reference='SUP-002', receipt_base64=self.receipt('red'), idempotency_key='second-supplier-reference')
        record = self.debit(); self.assertEqual(self.allocate(bill, record, '300.03').status_code, 201)
        self.assertEqual(self.allocate(second, record, '300.02', idempotency_key='split-supplier-reference').status_code, 201)
        self.assertEqual(self.allocate(second, record, '0.01', idempotency_key='excess-supplier-reference').status_code, 409)
        income = self.debit(direction='income'); other = self.debit(location_id=self.other_lid)
        for rid in [income, other]:
            self.assertEqual(self.allocate(bill, rid, idempotency_key=secrets.token_hex(16)).status_code, 404)

    def test_scopes_invalid_money_dates_void_retention(self):
        self.setup_bills(); bill = self.import_bill()
        self.assertEqual(self.staff.get(self.bills).status_code, 403)
        manager = self.member('manager')
        self.assertEqual(manager.get(self.bills.replace(self.lid, self.other_lid)).status_code, 404)
        outsider = self.client(); self.register(outsider, 'outside@example.test')
        self.assertEqual(outsider.get(f'{self.bills}/{bill}/invoice').status_code, 404)
        for extra in [{'amount': '0'}, {'amount': '1.001'}, {'issued_on': '2999-01-01'}, {'due_on': '2000-01-01'}, {'currency': 'USD'}]:
            self.assertEqual(self.owner.post(self.bills, json=self.bill(**extra)).status_code, 422)
        self.assertEqual(self.owner.post(f'{self.bills}/{bill}/void', json={'reason': 'Imported in error'}).status_code, 200)
        self.assertEqual(self.owner.get(self.bills).json()['outstanding'], '0.00')
        self.assertEqual(self.owner.get(f'{self.bills}/{bill}/invoice').status_code, 200)
        self.assertEqual(self.allocate(bill, self.debit()).status_code, 409)

    def test_voided_import_can_be_replaced_without_erasing_original_evidence(self):
        self.setup_bills(); old = self.import_bill()
        self.owner.post(f'{self.bills}/{old}/void', json={'reason': 'Correct a mistyped total'})
        new = self.import_bill(amount='1000.20', idempotency_key='replacement-import-reference')
        self.assertNotEqual(old, new)
        self.assertEqual(self.owner.get(self.bills).json()['outstanding'], '1000.20')
        self.assertEqual(self.owner.get(f'{self.bills}/{old}/invoice').content, self.owner.get(f'{self.bills}/{new}/invoice').content)
        self.assertEqual(self.owner.get(self.bills).json()['count'], 2)
        self.assertEqual(self.import_bill(), old)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(SupplierTests(name) for name in SupplierTests.__dict__ if name.startswith('test_'))
