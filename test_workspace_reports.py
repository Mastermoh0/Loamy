"""Exact, explicitly scoped insights and exports that preserve evidence and omit private data."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from zipfile import ZipFile
import csv
import hashlib
import json
import secrets
import sqlite3
import unittest
from test_workspace_expenses import ExpenseTests
from workspace_reports import EXPORT_LOCK, safe_csv


class ReportTests(ExpenseTests):
    def setup_reports(self):
        self.setup_expenses(); self.reports = f'/enterprise-api/businesses/{self.bid}'
        self.today = datetime.now(timezone(timedelta(hours=1))).date()

    def record(self, direction='expense', amount='300.10', days=10, **extra):
        response = self.owner.post(self.reports + '/financial-records', json={'location_id': self.lid, 'direction': direction, 'amount': amount, 'occurred_on': (self.today - timedelta(days=days)).isoformat(), 'description': 'Monthly test hosting', 'category': 'Software', 'idempotency_key': secrets.token_hex(16), **extra})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def insight(self, **extra):
        result = self.owner.post(self.reports + '/financial-insights', json=extra)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def export(self, client=None, **extra):
        return (client or self.owner).post(self.reports + '/financial-history/export', json={'start': (self.today - timedelta(days=90)).isoformat(), 'end': self.today.isoformat(), **extra})

    def test_exact_runway_requires_cash_coverage_and_regular_evidence(self):
        self.setup_reports()
        ids = [self.record(days=days) for days in [10, 40, 70]]
        self.record(direction='income', amount='500.00', days=5, description='Test payment')
        unconfirmed = self.insight(available_cash='1000.00')
        self.assertIsNone(unconfirmed['runway_days'])
        result = self.insight(available_cash='1000.00', confirm_complete_history=True)
        self.assertEqual((result['inflow'], result['outflow'], result['net_burn'], result['runway_days']), ('500.00', '900.30', '400.30', 100000 * 90 // 40030))
        self.assertEqual(set(result['recurring_candidates'][0]['record_ids']), set(ids))
        self.assertEqual(result['recurring_candidates'][0]['cadence_candidate'], 'monthly')
        self.assertIsNone(self.insight(location_id=self.other_lid, available_cash='1000.00', confirm_complete_history=True)['runway_days'])
        self.assertEqual(self.insight(available_cash='0.00', confirm_complete_history=True)['runway_days'], 0)

    def test_debtors_are_current_and_commitments_do_not_post_expenses(self):
        self.setup_reports()
        oid = self.owner.post(self.base + '/orders', json=self.payload()).json()['id']
        iid = self.owner.post(self.base + f'/orders/{oid}/invoice', json={}).json()['invoice']['id']
        plan = {'location_id': self.lid, 'vendor': 'Hosting test', 'description': 'Annual server', 'amount': '1200.12', 'cadence': 'yearly', 'next_due': self.today.isoformat(), 'idempotency_key': 'commitment-test-reference'}
        response = self.owner.post(self.reports + '/recurring-commitments', json=plan)
        self.assertEqual(response.status_code, 201, response.text); pid = response.json()['id']
        self.assertEqual(self.owner.post(self.reports + '/recurring-commitments', json=plan).json()['id'], pid)
        self.assertEqual(self.owner.post(self.reports + '/recurring-commitments', json={**plan, 'amount': '1200.13'}).status_code, 409)
        result = self.insight(); self.assertEqual(result['declared_monthly_commitments'], '100.01')
        self.assertEqual(result['debtors'][0]['invoice_id'], iid)
        self.assertEqual(result['debtors'][0]['outstanding'], '3000.30')
        self.assertEqual(self.owner.get(self.reports + '/financial-records').json()['count'], 0)
        self.owner.post(self.reports + f'/recurring-commitments/{pid}/cancel', json={'reason': 'Stop tracking fictional service'})
        result = self.insight(); self.assertEqual(result['declared_monthly_commitments'], '0.00'); self.assertEqual(result['commitments'][0]['status'], 'cancelled')

    def test_export_totals_originals_checksums_voids_and_formula_protection(self):
        self.setup_reports()
        eid = self.submit_expense(); self.approve(eid)
        self.owner.post(self.expenses + f'/{eid}/post', json={'reason': 'Post fictional receipt'})
        self.record(amount='0.10', days=0, description='=HYPERLINK("https://example.test")')
        voided = self.record(direction='income', amount='20.00', days=0)
        self.owner.post(self.reports + f'/financial-records/{voided}/void', json={'reason': 'Fictional correction'})
        oid = self.owner.post(self.base + '/orders', json=self.payload()).json()['id']
        self.owner.post(self.base + f'/orders/{oid}/invoice', json={})
        bill = self.owner.post(self.base + '/supplier-bills', json={'vendor': 'Test supplier', 'reference': 'EXP-001', 'description': 'Fictional unpaid invoice', 'category': 'Supplies', 'amount': '1200.00', 'issued_on': self.today.isoformat(), 'due_on': self.today.isoformat(), 'receipt_base64': self.receipt('red'), 'idempotency_key': 'export-supplier-reference'})
        self.assertEqual(bill.status_code, 201, bill.text)
        result = self.export(); self.assertEqual(result.status_code, 200, result.text)
        with ZipFile(BytesIO(result.content)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['posted_totals'], {'income': '0.00', 'expenses': '1000.20', 'net': '-1000.20'})
            self.assertEqual(len(manifest['evidence']), 3)
            for entry in manifest['evidence']:
                self.assertEqual(hashlib.sha256(archive.read(entry['path'])).hexdigest(), entry['sha256'])
            rows = list(csv.DictReader(StringIO(archive.read('ledger.csv').decode('utf-8-sig'))))
            self.assertTrue(any(r['description'].startswith('\t=HYPERLINK') for r in rows))
            self.assertTrue(any(r['status'] == 'voided' for r in rows))
            self.assertIn('summary.csv', archive.namelist())
            self.assertFalse(any('sessions' in name or 'whatsapp' in name for name in archive.namelist()))
        without_files = self.export(include_evidence=False)
        with ZipFile(BytesIO(without_files.content)) as archive:
            self.assertEqual(json.loads(archive.read('manifest.json'))['evidence'], [])

    def test_scope_dates_and_export_busy_limits(self):
        self.setup_reports(); self.record()
        self.record(location_id=self.other_lid, description='Other location record')
        finance = self.member('finance')
        scoped = self.export(finance); self.assertEqual(scoped.status_code, 200, scoped.text)
        with ZipFile(BytesIO(scoped.content)) as archive:
            manifest = json.loads(archive.read('manifest.json')); self.assertEqual(manifest['location_id'], self.lid); self.assertEqual(manifest['ledger_count'], 1)
        self.assertEqual(finance.post(self.reports + '/financial-insights', json={}).status_code, 403)
        self.assertEqual(self.export(finance, location_id=self.other_lid).status_code, 404)
        self.assertEqual(self.export(self.staff).status_code, 403)
        self.assertEqual(self.export(start='2020-01-01').status_code, 422)
        self.assertEqual(self.export(end='2999-01-01').status_code, 422)
        EXPORT_LOCK.acquire()
        try:
            self.assertEqual(self.export().status_code, 429)
        finally:
            EXPORT_LOCK.release()

    def test_large_evidence_is_refused_before_building_archive(self):
        self.setup_reports(); oid = self.owner.post(self.base + '/orders', json=self.payload()).json()['id']
        self.owner.post(self.base + f'/orders/{oid}/invoice', json={})
        with closing(sqlite3.connect(self.path)) as conn:
            # Oversized server-generated PDF fixture, not a public mutation capability.
            conn.execute('UPDATE invoices SET pdf=? WHERE order_id=?', (b'%PDF-' + b'x' * (26 * 1024 * 1024), oid)); conn.commit()
        self.assertEqual(self.export().status_code, 413)
        self.assertEqual(self.export(include_evidence=False).status_code, 200)

    def test_old_supplier_bill_paid_in_period_and_cancelled_invoice_evidence(self):
        self.setup_reports(); old_date = (self.today - timedelta(days=30)).isoformat()
        bill = self.owner.post(self.base + '/supplier-bills', json={'vendor': 'Prior supplier', 'reference': 'PRIOR-001', 'description': 'Previously issued invoice', 'category': 'Supplies', 'amount': '1000.10', 'issued_on': old_date, 'due_on': old_date, 'receipt_base64': self.receipt('red'), 'idempotency_key': 'prior-bill-export-reference'}).json()['id']
        debit = self.record(amount='1000.10', days=0)
        self.owner.post(self.base + f'/supplier-bills/{bill}/payments', json={'record_id': debit, 'amount': '1000.10', 'reason': 'Test existing supplier payment', 'idempotency_key': 'prior-bill-payment-key'})
        oid = self.owner.post(self.base + '/orders', json=self.payload()).json()['id']
        self.owner.post(self.base + f'/orders/{oid}/invoice', json={})
        self.owner.post(self.base + f'/orders/{oid}/cancel', json={'reason': 'Fictional cancellation'})
        result = self.export(start=self.today.isoformat())
        self.assertEqual(result.status_code, 200, result.text if result.status_code != 200 else '')
        with ZipFile(BytesIO(result.content)) as archive:
            self.assertTrue(any(name.startswith('suppliers/') for name in archive.namelist()))
            balances = list(csv.DictReader(StringIO(archive.read('current-invoice-balances.csv').decode('utf-8-sig'))))
            self.assertEqual((balances[0]['status'], balances[0]['outstanding']), ('cancelled', '0.00'))


class CsvTests(unittest.TestCase):
    def test_formula_markers_fullwidth_controls_and_embedded_quotes(self):
        rows = [{'value': value} for value in ['=2+2', '+2+2', '-2+2', '@SUM(A1)', '＝1+2', '\t=2', 'normal,"quoted"']]
        output = list(csv.DictReader(StringIO(safe_csv(['value'], rows).decode('utf-8-sig'))))
        self.assertTrue(all(r['value'].startswith('\t') for r in output[:5]))
        self.assertTrue(output[5]['value'].startswith("'"))
        self.assertEqual(output[6]['value'], 'normal,"quoted"')


def load_tests(loader, tests, pattern):
    return unittest.TestSuite([unittest.TestSuite(ReportTests(name) for name in ReportTests.__dict__ if name.startswith('test_')), loader.loadTestsFromTestCase(CsvTests)])
