"""Order lifecycle, historical prices and server-side role/location boundaries."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import sqlite3
import unittest
from fastapi.testclient import TestClient
from enterprise_preview import create_app
from test_enterprise_preview import WorkspaceTests


class OrderTests(WorkspaceTests):
    def setup_orders(self):
        self.register(self.owner, 'owner@example.test')
        self.bid = self.business(self.owner)
        self.lid = self.owner.get(f'/enterprise-api/businesses/{self.bid}').json()['locations'][0]['id']
        self.other_lid = self.owner.post(f'/enterprise-api/businesses/{self.bid}/locations', json={'name': 'Ikeja', 'address': '2 Test Road'}).json()['id']
        self.base = f'/enterprise-api/businesses/{self.bid}/locations/{self.lid}'
        self.service = {'name': 'Room night', 'description': 'Standard room', 'price': '1000.10', 'active': True}
        result = self.owner.post(self.base + '/services', json=self.service)
        self.assertEqual(result.status_code, 201, result.text)
        self.sid = result.json()['id']

    def payload(self, key='order-reference-0001'):
        return {'customer_name': 'Test Guest', 'customer_contact': '08000000000', 'idempotency_key': key,
                'lines': [{'service_id': self.sid, 'quantity': 3, 'expected_price': '1000.10'}]}

    def member(self, role):
        client = self.client()
        email = f'{role}@example.test'
        self.register(client, email)
        invitation = self.owner.post(f'/enterprise-api/businesses/{self.bid}/invitations', json={'email': email, 'role': role, 'location_id': self.lid}).json()
        self.assertEqual(client.post('/enterprise-api/invitations/accept', json={'token': invitation['token']}).status_code, 200)
        return client

    def test_order_snapshots_retry_cancellation_and_persistence(self):
        self.setup_orders()
        profile = {'invoice_name': 'Palm House Ltd', 'address': 'Test invoice address', 'payment_instructions': 'Test account instructions'}
        self.assertEqual(self.owner.put(self.base + '/profile', json=profile).status_code, 200)
        payload = self.payload()
        created = self.owner.post(self.base + '/orders', json=payload)
        self.assertEqual(created.status_code, 201, created.text)
        saved = created.json()
        oid = saved['id']
        self.assertTrue(saved['reference'].startswith('ORD-'))
        same = self.owner.post(self.base + '/orders', json=payload).json()
        self.assertEqual(same['id'], oid)
        self.assertTrue(same['duplicate'])
        self.assertEqual(self.owner.post(self.base + '/orders', json={**payload, 'customer_name': 'Another Guest'}).status_code, 409)
        self.assertEqual(self.owner.put(self.base + f'/services/{self.sid}', json={**self.service, 'name': 'Renamed room', 'price': '2000.20', 'active': False}).status_code, 200)
        self.owner.put(self.base + '/profile', json={**profile, 'invoice_name': 'Changed Name'})
        detail = self.owner.get(self.base + f'/orders/{oid}').json()
        self.assertEqual(detail['total'], '3000.30')
        self.assertEqual(detail['lines'][0]['name'], 'Room night')
        self.assertEqual(detail['lines'][0]['unit_price'], '1000.10')
        self.assertEqual(detail['profile'], profile)
        self.assertEqual(self.owner.post(self.base + '/orders', json=self.payload('order-reference-0002')).status_code, 409)
        # Saved retries still recover the original even after catalogue changes.
        self.assertEqual(self.owner.post(self.base + '/orders', json=payload).json()['id'], oid)
        persisted = TestClient(create_app(self.path), headers={'Origin': 'http://testserver'})
        persisted.cookies.update(self.owner.cookies)
        self.assertEqual(persisted.get(self.base + f'/orders/{oid}').json()['total'], '3000.30')
        self.assertEqual(self.owner.post(self.base + f'/orders/{oid}/cancel', json={'reason': 'Guest changed plans'}).status_code, 200)
        self.owner.post(self.base + f'/orders/{oid}/cancel', json={'reason': 'Replacement reason'})
        cancelled = self.owner.get(self.base + f'/orders/{oid}').json()
        self.assertEqual(cancelled['cancel_reason'], 'Guest changed plans')
        self.assertEqual(cancelled['total'], '3000.30')
        self.assertEqual(cancelled['status'], 'cancelled')
        self.assertTrue(cancelled['cancelled_by_name'])
        self.assertEqual(self.owner.get(self.base + '/orders').json()['counts'], {'total': 1, 'open': 0, 'cancelled': 1})
        self.assertEqual(self.owner.get(f'/enterprise-api/businesses/{self.bid}/financial-records').json()['count'], 0)

    def test_multiple_items_and_failed_order_roll_back(self):
        self.setup_orders()
        sid = self.owner.post(self.base + '/services', json={**self.service, 'name': 'Breakfast', 'price': '0.15'}).json()['id']
        payload = self.payload()
        payload['lines'].append({'service_id': sid, 'quantity': 2, 'expected_price': '0.15'})
        response = self.owner.post(self.base + '/orders', json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        order = self.owner.get(self.base + '/orders/' + response.json()['id']).json()
        self.assertEqual(order['total'], '3000.60')
        self.assertEqual([line['total'] for line in order['lines']], ['3000.30', '0.30'])
        payload['idempotency_key'] = 'failed-order-key-0000'
        payload['lines'][1]['service_id'] = 'missing-service'
        self.assertEqual(self.owner.post(self.base + '/orders', json=payload).status_code, 409)
        self.assertEqual(self.owner.get(self.base + '/orders').json()['counts']['total'], 1)
        unverified = self.client()
        unverified.post('/enterprise-api/register', json={'name': 'Unverified User', 'email': 'unverified@example.test', 'password': 'Test-password-42'})
        self.assertEqual(unverified.get(self.base + '/orders').status_code, 403)

    def test_roles_locations_and_revocation(self):
        self.setup_orders()
        other = f'/enterprise-api/businesses/{self.bid}/locations/{self.other_lid}'
        for role in ['manager', 'finance', 'front_desk', 'staff']:
            client = self.member(role)
            readable = role != 'staff'
            writable = role in {'manager', 'front_desk'}
            self.assertEqual(client.get(self.base + '/catalogue').status_code, 200 if readable else 403)
            self.assertEqual(client.get(self.base + '/orders').status_code, 200 if readable else 403)
            self.assertEqual(client.post(self.base + '/services', json=self.service).status_code, 201 if role == 'manager' else 403)
            self.assertEqual(client.put(self.base + '/profile', json={'invoice_name': 'Test Profile', 'address': 'Test address'}).status_code, 200 if role == 'manager' else 403)
            response = client.post(self.base + '/orders', json=self.payload(f'order-for-{role}-0000'))
            self.assertEqual(response.status_code, 201 if writable else 403, response.text)
            if writable:
                oid = response.json()['id']
                self.assertEqual(client.post(other + f'/orders/{oid}/cancel', json={'reason': 'Not allowed'}).status_code, 404)
                self.assertEqual(client.post(self.base + f'/orders/{oid}/cancel', json={'reason': 'Guest cancelled'}).status_code, 200)
            self.assertEqual(client.get(other + '/orders').status_code, 404 if readable else 403)
            self.assertEqual(client.put(other + f'/services/{self.sid}', json=self.service).status_code, 404 if role == 'manager' else 403)
        oid = self.owner.post(self.base + '/orders', json=self.payload()).json()['id']
        finance = self.client()
        finance.post('/enterprise-api/login', json={'email': 'finance@example.test', 'password': 'Test-password-42'})
        self.assertEqual(finance.get(self.base + f'/orders/{oid}').status_code, 200)
        self.assertEqual(finance.post(self.base + f'/orders/{oid}/cancel', json={'reason': 'Not allowed'}).status_code, 403)
        staff = self.client()
        staff.post('/enterprise-api/login', json={'email': 'staff@example.test', 'password': 'Test-password-42'})
        self.assertEqual(staff.get(self.base + f'/orders/{oid}').status_code, 403)
        outsider = self.client()
        self.register(outsider, 'outside@example.test')
        self.assertEqual(outsider.get(self.base + '/orders').status_code, 404)
        foreign_bid = self.business(outsider, 'Other Business')
        foreign_lid = outsider.get(f'/enterprise-api/businesses/{foreign_bid}').json()['locations'][0]['id']
        self.assertEqual(self.owner.get(f'/enterprise-api/businesses/{self.bid}/locations/{foreign_lid}/orders').status_code, 404)
        members = self.owner.get(f'/enterprise-api/businesses/{self.bid}').json()['team']
        fid = next(m['id'] for m in members if m['role'] == 'finance')
        self.owner.delete(f'/enterprise-api/businesses/{self.bid}/members/{fid}')
        self.assertEqual(finance.get(self.base + f'/orders/{oid}').status_code, 404)

    def test_validation_stale_prices_and_date_counts(self):
        self.setup_orders()
        payload = self.payload()
        for quantity in [0, -1, 1.5, True, 10001]:
            bad = {**payload, 'lines': [{**payload['lines'][0], 'quantity': quantity}]}
            self.assertEqual(self.owner.post(self.base + '/orders', json=bad).status_code, 422)
        for price in ['0', '-1', '1.001', 'NaN', 'Infinity']:
            self.assertEqual(self.owner.post(self.base + '/services', json={**self.service, 'price': price}).status_code, 422)
        for extra in [{'actor_id': 'spoof'}, {'total': '1.00'}, {'status': 'paid'}]:
            self.assertEqual(self.owner.post(self.base + '/orders', json={**payload, **extra}).status_code, 422)
        self.assertEqual(self.owner.post(self.base + '/orders', json={**payload, 'customer_contact': ''}).status_code, 422)
        self.assertEqual(self.owner.post(self.base + '/orders', json={**payload, 'lines': []}).status_code, 422)
        self.assertEqual(self.owner.post(self.base + '/orders', json={**payload, 'lines': payload['lines'] * 2}).status_code, 422)
        self.assertEqual(self.owner.post(self.base + '/orders', json={**payload, 'lines': [{**payload['lines'][0], 'expected_price': '1.00'}]}).status_code, 409)
        other = f'/enterprise-api/businesses/{self.bid}/locations/{self.other_lid}'
        self.assertEqual(self.owner.post(other + '/orders', json=payload).status_code, 409)
        first = self.owner.post(self.base + '/orders', json=payload).json()
        second = self.owner.post(self.base + '/orders', json=self.payload('second-order-key-0000')).json()
        self.assertNotEqual(first['reference'], second['reference'])
        yesterday = (datetime.now(timezone(timedelta(hours=1))) - timedelta(days=1)).date().isoformat()
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute('UPDATE orders SET order_date=? WHERE id=?', (yesterday, first['id']))
        self.assertEqual(self.owner.get(self.base + '/orders').json()['counts']['total'], 1)
        self.assertEqual(self.owner.get(self.base + '/orders?period=all').json()['counts']['total'], 2)
        self.assertEqual(self.owner.get(other + '/orders?period=all').json()['counts']['total'], 0)
        self.assertEqual(self.owner.get(other + f'/orders/{second["id"]}').status_code, 404)
        self.assertEqual(self.owner.get(self.base + '/orders?period=invalid').status_code, 422)


def load_tests(loader, tests, pattern):
    return loader.loadTestsFromTestCase(OrderTests)


if __name__ == '__main__':
    unittest.main()
