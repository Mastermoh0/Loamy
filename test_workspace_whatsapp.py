"""No live provider calls: signed webhook fixtures and a mocked bounded media transport."""
import base64
import hashlib
import hmac
import json
import os
import time
import unittest
import httpx
from io import BytesIO
from PIL import Image
from unittest.mock import patch
from fastapi.testclient import TestClient
from enterprise_preview import create_app
from test_workspace_expenses import ExpenseTests
from workspace_whatsapp import WhatsAppSettings, WEBHOOK, download_media


class WhatsAppTests(ExpenseTests):
    def setup_whatsapp(self):
        self.setup_expenses()
        self.settings = WhatsAppSettings('fake-secret-for-tests-1234567890', 'fake-verification-token-1234567890', 'fake-provider-token', 'v99.0', {'1234567890': self.bid})
        owner_cookies, staff_cookies = self.owner.cookies, self.staff.cookies
        with patch('workspace_whatsapp.WhatsAppSettings.from_env', return_value=self.settings):
            self.app = create_app(self.path)
        self.owner = self.client(); self.owner.cookies.update(owner_cookies)
        self.staff = self.client(); self.staff.cookies.update(staff_cookies)
        self.inbox = self.base + '/whatsapp'; self.sender = '2348000000000'; self.pid = '1234567890'

    def deliver(self, message, **extra):
        value = {'messaging_product': 'whatsapp', 'metadata': {'phone_number_id': self.pid}, 'messages': [message], **extra}
        raw = json.dumps({'object': 'whatsapp_business_account', 'entry': [{'changes': [{'field': 'messages', 'value': value}]}]}).encode()
        signature = 'sha256=' + hmac.new(self.settings.secret.encode(), raw, hashlib.sha256).hexdigest()
        return TestClient(self.app).post(WEBHOOK, content=raw, headers={'x-hub-signature-256': signature})

    def link(self):
        code = self.staff.post(self.inbox + '/link-code', json={'phone_id': self.pid})
        self.assertEqual(code.status_code, 200, code.text)
        self.link_text = code.json()['message']
        linked = self.deliver({'id': 'wamid.link', 'from': self.sender, 'type': 'text', 'text': {'body': self.link_text}})
        self.assertEqual(linked.status_code, 200, linked.text)
        return self.staff.get(self.inbox).json()['links'][0]

    def image_message(self, **extra):
        return {'id': 'wamid.receipt1', 'from': self.sender, 'timestamp': str(int(time.time())), 'type': 'image',
            'image': {'id': '987654321', 'mime_type': 'image/png', 'sha256': base64.b64encode(hashlib.sha256(base64.b64decode(self.receipt())).digest()).decode(), 'caption': 'Office paper'}, **extra}

    def test_signed_identity_queue_download_confirm_and_independent_review(self):
        self.setup_whatsapp(); self.link()
        message = self.image_message()
        self.assertEqual(self.deliver(message).status_code, 200)
        self.deliver(message)
        self.assertEqual(len(self.staff.get(self.inbox).json()['messages']), 1)
        with patch('workspace_whatsapp.download_media', return_value=(base64.b64decode(self.receipt()), 'image/png', 'png')) as downloader:
            self.assertTrue(self.app.state.process_whatsapp_message()); self.assertFalse(self.app.state.process_whatsapp_message())
            self.assertEqual(downloader.call_count, 1)
        received = self.staff.get(self.inbox).json()['messages'][0]
        self.assertEqual(received['status'], 'ready')
        self.assertEqual(self.owner.get(self.inbox).json()['messages'], [])
        self.assertEqual(self.owner.get(self.inbox + f'/messages/{received["id"]}/draft').status_code, 404)
        draft = self.staff.get(self.inbox + f'/messages/{received["id"]}/draft').json()
        self.assertEqual(draft['receipt_base64'], self.receipt())
        self.assertEqual(self.staff.get(self.inbox + f'/messages/{received["id"]}/receipt').content, base64.b64decode(self.receipt()))
        self.assertEqual(self.owner.get(self.expenses).json()['count'], 0)
        eid = self.submit_expense(whatsapp_message_id=received['id'])
        self.assertEqual(self.staff.get(self.inbox).json()['messages'][0]['status'], 'submitted')
        self.assertEqual(self.staff.get(self.inbox + f'/messages/{received["id"]}/draft').status_code, 409)
        self.assertEqual(self.owner.get(self.expenses).json()['expenses'][0]['whatsapp_source']['provider_id'], message['id'])
        self.assertEqual(self.staff.post(self.expenses + f'/{eid}/review', json={'decision': 'approved', 'revision': 1, 'reason': 'Self approval forbidden'}).status_code, 403)
        self.approve(eid)
        self.assertEqual(self.owner.get(f'/enterprise-api/businesses/{self.bid}/financial-records').json()['count'], 0)

    def test_signature_handshake_unlinked_group_unsupported_and_code_replay(self):
        self.setup_whatsapp()
        self.assertEqual(TestClient(self.app).post(WEBHOOK, json={}).status_code, 401)
        self.assertEqual(self.owner.get(WEBHOOK, params={'hub.mode': 'subscribe', 'hub.verify_token': self.settings.verify_token, 'hub.challenge': '1234'}).text, '1234')
        self.assertEqual(self.owner.get(WEBHOOK, params={'hub.mode': 'subscribe', 'hub.verify_token': 'wrong', 'hub.challenge': '1234'}).status_code, 403)
        self.deliver(self.image_message())
        self.assertEqual(self.staff.get(self.inbox).json()['messages'], [])
        self.link()
        self.deliver({'id': 'wamid.replay', 'from': '2348000000001', 'type': 'text', 'text': {'body': self.link_text}})
        self.assertEqual(len(self.staff.get(self.inbox).json()['links']), 1)
        self.deliver(self.image_message(group_id='group-test'))
        self.deliver(self.image_message(), group_id='group-test')
        self.deliver(self.image_message(type='audio'))
        self.assertEqual(self.staff.get(self.inbox).json()['messages'], [])
        self.assertEqual(self.staff.post(self.inbox + '/link-code', json={'phone_id': 'foreign-phone'}).status_code, 422)

    def test_revocation_blocks_queue_processing_and_wrong_evidence(self):
        self.setup_whatsapp(); link = self.link(); self.deliver(self.image_message())
        self.staff.post(self.inbox + f'/links/{link["id"]}/revoke', json={'reason': 'Phone no longer in use'})
        with patch('workspace_whatsapp.download_media') as downloader:
            self.assertTrue(self.app.state.process_whatsapp_message()); downloader.assert_not_called()
        self.assertEqual(self.staff.get(self.inbox).json()['messages'][0]['status'], 'failed')
        self.deliver(self.image_message(id='wamid.after-revoke'))
        self.assertEqual(len(self.staff.get(self.inbox).json()['messages']), 1)
        fake = self.staff.post(self.inbox + '/preview-message', json={'receipt_base64': self.receipt(), 'caption': 'Fictional', 'idempotency_key': 'fictional-receipt-test'}).json()['id']
        response = self.staff.post(self.expenses, json=self.expense(whatsapp_message_id=fake, receipt_base64=self.receipt('red')))
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.owner.post(self.expenses, json=self.expense(whatsapp_message_id=fake)).status_code, 422)

    def test_failed_download_retry_discard_and_staff_location_scope(self):
        self.setup_whatsapp(); self.link(); self.deliver(self.image_message())
        with patch('workspace_whatsapp.download_media', side_effect=ValueError('test failure')):
            self.app.state.process_whatsapp_message()
        message = self.staff.get(self.inbox).json()['messages'][0]
        self.assertEqual(message['status'], 'failed')
        self.assertEqual(self.staff.post(self.inbox + f'/messages/{message["id"]}/retry').status_code, 200)
        self.assertEqual(self.staff.post(self.inbox + f'/messages/{message["id"]}/discard', json={'reason': 'Duplicate paper receipt'}).status_code, 200)
        with patch('workspace_whatsapp.download_media') as downloader:
            self.assertFalse(self.app.state.process_whatsapp_message()); downloader.assert_not_called()
        self.assertEqual(self.staff.get(self.inbox.replace(self.lid, self.other_lid)).status_code, 404)


class TransportTests(unittest.TestCase):
    def test_bounded_media_download_digest_and_redirect_rejection(self):
        out = BytesIO(); Image.new('RGB', (20, 20), 'green').save(out, format='PNG'); raw = out.getvalue()
        digest = base64.b64encode(hashlib.sha256(raw).digest()).decode()
        original_client = httpx.Client
        settings = WhatsAppSettings('fake-secret', 'fake-verify', 'fake-access', 'v99.0', {})
        for mode in ['valid', 'digest', 'redirect', 'oversize']:
            def handler(request):
                self.assertEqual(request.headers['authorization'], 'Bearer fake-access')
                if request.url.host == 'graph.facebook.com':
                    return httpx.Response(200, json={'url': 'https://lookaside.fbsbx.com/media/test', 'file_size': 2097153 if mode == 'oversize' else len(raw)})
                self.assertEqual(request.url.host, 'lookaside.fbsbx.com')
                return httpx.Response(302, headers={'Location': 'https://evil.test'}) if mode == 'redirect' else httpx.Response(200, content=raw)
            with self.subTest(mode=mode), patch('workspace_whatsapp.httpx.Client', side_effect=lambda **kw: original_client(transport=httpx.MockTransport(handler), **kw)):
                if mode == 'valid':
                    self.assertEqual(download_media(settings, '123', '456', digest)[0], raw)
                else:
                    with self.assertRaises(ValueError):
                        download_media(settings, '123', '456', 'A' * 43 + '=' if mode == 'digest' else digest)

    def test_partial_configuration_fails_and_media_host_token_is_not_forwarded(self):
        with patch.dict(os.environ, {'LOAMY_WHATSAPP_APP_SECRET': 'partial'}):
            with self.assertRaises(RuntimeError):
                WhatsAppSettings.from_env()
        settings = WhatsAppSettings('fake-secret', 'fake-verify', 'fake-access', 'v99.0', {})
        for target in ['http://lookaside.fbsbx.com/media', 'https://evil.test/receipt', 'https://lookaside.fbsbx.com@evil.test/receipt', 'https://lookaside.fbsbx.com:8443/receipt']:
            with self.subTest(target=target), patch('workspace_whatsapp.httpx.Client') as client:
                transport = client.return_value.__enter__.return_value
                transport.get.return_value.json.return_value = {'url': target, 'file_size': 10}
                with self.assertRaises(ValueError):
                    download_media(settings, '12345', '67890', 'test-hash')
                transport.stream.assert_not_called()


def load_tests(loader, tests, pattern):
    return unittest.TestSuite([unittest.TestSuite(WhatsAppTests(name) for name in WhatsAppTests.__dict__ if name.startswith('test_')), loader.loadTestsFromTestCase(TransportTests)])
