"""QR payload, authentication, location boundaries and revoked access."""
import base64
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree
from unittest.mock import patch
import qrcode
from test_workspace_orders import OrderTests


class LocationLinkTests(OrderTests):
    def test_qr_uses_configured_origin_and_scoped_navigation_only(self):
        self.setup_orders()
        with patch('workspace_location_links.qrcode.make', wraps=qrcode.make) as generate:
            response = self.owner.get(self.base + '/link')
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(generate.call_args.args[0], result['url'])
            self.assertEqual(generate.call_args.kwargs['border'], 4)
        url = urlparse(result['url'])
        self.assertEqual((url.scheme, url.netloc, url.path, url.fragment), ('http', '127.0.0.1:5173', '/business', ''))
        self.assertEqual(parse_qs(url.query), {'business': [self.bid], 'location': [self.lid]})
        svg = ElementTree.fromstring(base64.b64decode(result['qr_data_url'].split(',')[1]))
        self.assertTrue(svg.tag.endswith('svg'))
        self.assertTrue(any(child.tag.endswith('path') for child in svg))
        self.assertEqual(self.client().get(self.base + '/link').status_code, 401)
        outsider = self.client(); self.register(outsider, 'qr-outsider@example.test')
        self.assertEqual(outsider.get(self.base + '/link').status_code, 404)
        for role in ['manager', 'front_desk', 'finance', 'staff']:
            member = self.member(role)
            self.assertEqual(member.get(self.base + '/link').status_code, 200)
            self.assertEqual(member.get(self.base.replace(self.lid, self.other_lid) + '/link').status_code, 404)
        member_id = next(m['id'] for m in self.owner.get(f'/enterprise-api/businesses/{self.bid}').json()['team'] if m['role'] == 'staff')
        self.owner.delete(f'/enterprise-api/businesses/{self.bid}/members/{member_id}')
        self.assertEqual(member.get(self.base + '/link').status_code, 404)


def load_tests(loader, tests, pattern):
    return loader.loadTestsFromName('test_qr_uses_configured_origin_and_scoped_navigation_only', LocationLinkTests)
