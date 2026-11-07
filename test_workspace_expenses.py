import base64
from datetime import datetime, timedelta, timezone
from io import BytesIO
import unittest
from PIL import Image
from test_workspace_orders import OrderTests


class ExpenseTests(OrderTests):
    def setup_expenses(self):
        self.setup_orders()
        self.staff = self.member('staff')
        self.expenses = self.base + '/expenses'

    def receipt(self, color='green'):
        out = BytesIO()
        Image.new('RGB', (20, 20), color=color).save(out, format='PNG')
        return base64.b64encode(out.getvalue()).decode()

    def expense(self, **extra):
        return {'vendor': 'Test Store', 'purpose': 'Office supplies', 'category': 'Supplies', 'amount': '1000.10',
                'occurred_on': datetime.now(timezone(timedelta(hours=1))).date().isoformat(), 'receipt_base64': self.receipt(), 'idempotency_key': 'expense-test-reference', **extra}

    def submit_expense(self, client=None, **extra):
        response = (client or self.staff).post(self.expenses, json=self.expense(**extra))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def approve(self, eid, revision=1):
        response = self.owner.post(self.expenses + f'/{eid}/review', json={'decision': 'approved', 'revision': revision, 'reason': 'Receipt and purpose checked'})
        self.assertEqual(response.status_code, 200, response.text)

    def test_receipt_review_posting_and_category_ledger_once(self):
        self.setup_expenses()
        eid = self.submit_expense()
        self.assertEqual(self.staff.post(self.expenses, json=self.expense()).json()['id'], eid)
        self.assertEqual(self.staff.post(self.expenses, json=self.expense(idempotency_key='another-submission-key')).status_code, 409)
        self.assertEqual(self.owner.get(self.expenses).json()['categories'], [])
        self.assertEqual(self.owner.post(self.expenses + f'/{eid}/post', json={'reason': 'Too early'}).status_code, 409)
        self.approve(eid)
        self.assertEqual(self.owner.get(self.expenses).json()['categories'], [])
        response = self.owner.post(self.expenses + f'/{eid}/post', json={'reason': 'Post checked receipt'})
        self.assertEqual(response.status_code, 200, response.text)
        rid = response.json()['record_id']
        self.assertTrue(self.owner.post(self.expenses + f'/{eid}/post', json={'reason': 'Retry'}).json()['duplicate'])
        listed = self.owner.get(self.expenses).json()
        self.assertEqual(listed['categories'], [{'category': 'Supplies', 'amount': '1000.10', 'count': 1}])
        self.assertEqual(listed['expenses'][0]['status'], 'posted')
        detail = self.owner.get(self.expenses + '/categories/Supplies').json()['records'][0]
        self.assertEqual((detail['expense_id'], detail['expense_revision'], detail['submitter']), (eid, 1, 'Test Person'))
        self.assertEqual(self.owner.get(f'/enterprise-api/businesses/{self.bid}/financial-records').json()['count'], 1)
        downloaded = self.staff.get(self.expenses + f'/{eid}/receipt/1')
        self.assertEqual(downloaded.content, base64.b64decode(self.receipt()))
        self.assertEqual(downloaded.headers['content-type'], 'application/octet-stream')
        self.assertIn('attachment;', downloaded.headers['content-disposition'])
        self.owner.post(f'/enterprise-api/businesses/{self.bid}/financial-records/{rid}/void', json={'reason': 'Correct an incorrect expense'})
        self.assertEqual(self.owner.get(self.expenses).json()['categories'], [])
        self.assertEqual(self.staff.get(self.expenses).json()['expenses'][0]['ledger_status'], 'voided')

    def test_clarification_revision_stale_review_and_private_evidence(self):
        self.setup_expenses()
        eid = self.submit_expense()
        self.assertEqual(self.staff.post(self.expenses + f'/{eid}/review', json={'decision': 'approved', 'revision': 1, 'reason': 'Not allowed'}).status_code, 403)
        self.owner.post(self.expenses + f'/{eid}/review', json={'decision': 'needs_clarification', 'revision': 1, 'reason': 'Explain the purchase'})
        revised = self.expense(purpose='Paper for guest invoices', receipt_base64=self.receipt('blue'), idempotency_key='expense-revision-key')
        self.assertEqual(self.staff.put(self.expenses + f'/{eid}', json=revised).status_code, 200)
        self.assertTrue(self.staff.put(self.expenses + f'/{eid}', json=revised).json()['duplicate'])
        self.assertEqual(self.owner.post(self.expenses + f'/{eid}/review', json={'decision': 'approved', 'revision': 1, 'reason': 'Stale view'}).status_code, 409)
        self.approve(eid, 2)
        expense = self.staff.get(self.expenses).json()['expenses'][0]
        self.assertEqual((expense['revision'], len(expense['history']), len(expense['versions'])), (2, 4, 2))
        self.assertEqual(self.staff.get(self.expenses + f'/{eid}/receipt/1').content, base64.b64decode(self.receipt()))
        self.assertEqual(self.staff.get(self.expenses + f'/{eid}/receipt/2').content, base64.b64decode(self.receipt('blue')))
        other = self.member('front_desk')
        self.assertEqual(other.get(self.expenses).json()['expenses'], [])
        self.assertEqual(other.get(self.expenses + f'/{eid}/receipt/1').status_code, 404)
        self.assertEqual(self.staff.get(self.expenses + '/categories/Supplies').status_code, 403)
        self.assertEqual(self.staff.get(self.expenses.replace(self.lid, self.other_lid)).status_code, 404)
        own = self.submit_expense(self.owner, receipt_base64=self.receipt('red'), idempotency_key='owner-own-expense-key')
        self.assertEqual(self.owner.post(self.expenses + f'/{own}/review', json={'decision': 'approved', 'revision': 1, 'reason': 'Self review'}).status_code, 403)

    def test_link_existing_debit_and_reject_duplicate_or_wrong_link(self):
        self.setup_expenses()
        eid = self.submit_expense()
        ledger = f'/enterprise-api/businesses/{self.bid}/financial-records'
        record = {'location_id': self.lid, 'direction': 'expense', 'amount': '1000.10', 'occurred_on': self.expense()['occurred_on'], 'description': 'Already recorded debit', 'category': 'Supplies', 'idempotency_key': 'expense-existing-debit'}
        rid = self.owner.post(ledger, json=record).json()['id']
        wrong = self.owner.post(ledger, json={**record, 'amount': '2.00', 'idempotency_key': 'expense-wrong-debit-key'}).json()['id']
        self.approve(eid)
        self.assertEqual(self.owner.post(self.expenses + f'/{eid}/post', json={'reason': 'Would duplicate'}).status_code, 409)
        self.assertEqual(self.owner.post(self.expenses + f'/{eid}/post', json={'reason': 'Wrong debit', 'record_id': wrong}).status_code, 409)
        self.assertEqual(self.owner.post(self.expenses + f'/{eid}/post', json={'reason': 'Matched original debit', 'record_id': rid}).status_code, 200)
        self.assertEqual(self.owner.get(ledger).json()['count'], 2)
        second = self.submit_expense(receipt_base64=self.receipt('blue'), idempotency_key='second-receipt-expense')
        self.approve(second)
        self.assertEqual(self.owner.post(self.expenses + f'/{second}/post', json={'reason': 'Same bank debit', 'record_id': rid}).status_code, 409)
        self.assertEqual(self.owner.post(self.expenses + f'/{second}/post', json={'reason': 'Separate purchase verified', 'confirm_new': True}).status_code, 200)

    def test_file_validation_money_identity_and_revocation(self):
        self.setup_expenses()
        for extra in [{'receipt_base64': base64.b64encode(b'<html>not a receipt</html>').decode()}, {'receipt_base64': '!' * 20}, {'amount': '1.001'}, {'amount': 'NaN'}, {'occurred_on': '2999-01-01'}, {'actor_id': 'spoof'}, {'status': 'approved'}]:
            self.assertIn(self.staff.post(self.expenses, json=self.expense(**extra)).status_code, [422])
        eid = self.submit_expense()
        self.assertEqual(self.owner.get(self.expenses + f'/{eid}/receipt/99').status_code, 404)
        owner_view = self.owner.get(f'/enterprise-api/businesses/{self.bid}').json()
        member = next(row for row in owner_view['team'] if row['role'] == 'staff')
        self.owner.delete(f'/enterprise-api/businesses/{self.bid}/members/{member["id"]}')
        self.assertEqual(self.staff.get(self.expenses + f'/{eid}/receipt/1').status_code, 404)
        self.assertEqual(self.staff.get(self.expenses).status_code, 404)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(ExpenseTests(name) for name in ExpenseTests.__dict__ if name.startswith('test_'))
