"""Boot the candidate on loopback, emulate the trusted TLS proxy, then remove only this test container."""
from pathlib import Path
import json
import secrets
import subprocess
import time
from urllib.parse import quote, urlencode
import httpx

ROOT = Path(__file__).resolve().parents[1]


def docker(*args, check=True):
    return subprocess.run(['docker', *args], cwd=ROOT, capture_output=True, text=True, check=check, timeout=60)


network = json.loads(docker('network', 'inspect', 'loamy-enterprise-test_default').stdout)[0]
gateway = network['IPAM']['Config'][0]['Gateway']
database = next(item for item in network['Containers'].values() if item['Name'] == 'loamy-enterprise-test-postgres-1')
address = database['IPv4Address'].split('/')[0]
password = (ROOT / '.local-data/postgres-test.env').read_text().strip().split('=', 1)[1]
query = urlencode({'sslmode': 'verify-full', 'sslrootcert': '/run/secrets/database-ca.crt', 'hostaddr': address})
dsn = f'postgresql://loamy_enterprise_app:{quote(password)}@localhost:5432/enterprise_test?{query}'
env_file = ROOT / '.local-data/container-rehearsal.env'
env_file.write_text('\n'.join([
    'LOAMY_WORKSPACE_DATABASE_URL=' + dsn,
    'LOAMY_WORKSPACE_WEB_ORIGIN=https://workspace.example.test',
    'LOAMY_WORKSPACE_API_ORIGIN=https://workspace.example.test',
    'LOAMY_MAIL_TRANSPORT=smtp', 'LOAMY_SMTP_HOST=mail.example.test',
    'LOAMY_SMTP_FROM=test@example.test', 'LOAMY_SMTP_USERNAME=rehearsal',
    'LOAMY_SMTP_PASSWORD=fake-test-only', 'FORWARDED_ALLOW_IPS=' + gateway,
]) + '\n')
name = 'loamy-enterprise-rehearsal-' + secrets.token_hex(4)
certificate = ROOT / '.local-data/postgres-certs/ca.crt'
report = {'scope': 'loopback-only rehearsal; no real SMTP or public deployment', 'database_tls': 'verify-full', 'proxy_tls': 'simulated trusted proxy header, not a public certificate test'}
try:
    docker('run', '-d', '--name', name, '--read-only', '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m', '--cap-drop', 'ALL',
           '--security-opt', 'no-new-privileges', '--network', 'loamy-enterprise-test_default',
           '-p', '127.0.0.1:58080:8080', '--env-file', str(env_file),
           '--mount', f'type=bind,source={certificate},target=/run/secrets/database-ca.crt,readonly', 'loamy-enterprise:rehearsal')
    for attempt in range(30):
        try:
            if httpx.get('http://127.0.0.1:58080/health/ready', timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        raise RuntimeError('Candidate container did not become ready; inspect its local logs')
    headers = {'Host': 'workspace.example.test', 'X-Forwarded-Proto': 'https'}
    root = 'http://127.0.0.1:58080'
    assert httpx.get(root + '/business', headers=headers).status_code == 200
    assert httpx.get(root + '/enterprise-api/config', headers=headers).json() == {'local_preview': False}
    assert httpx.get(root + '/enterprise-api/missing', headers=headers).status_code == 404
    assert httpx.get(root + '/enterprise-api/config', headers={'Host': 'workspace.example.test'}).status_code == 400
    assert httpx.get(root + '/enterprise-api/config', headers={'Host': 'attacker.example.test'}).status_code == 403
    assert docker('exec', name, 'id', '-u').stdout.strip() == '10001'
    assert docker('exec', name, 'python', 'scripts/process_whatsapp_inbox.py', '--help').returncode == 0
    assert docker('exec', name, 'python', 'scripts/process_whatsapp_inbox.py', '--once', check=False).returncode != 0
    # Verify the packaged reader with the same non-root/read-only runtime, not a mock.
    docker('exec', name, 'python', '-c', '''from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from workspace_receipt_reader import native_text, parse_receipt
picture=Image.new('RGB',(1200,300),'white')
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',44)
ImageDraw.Draw(picture).multiline_text((40,40),'TEST STORE\\nTOTAL NGN 1,000.10',font=font,fill='black',spacing=25)
out=BytesIO(); picture.save(out,format='PNG')
assert parse_receipt(native_text(out.getvalue(),'image/png'))['suggested']['amount']=='1000.10'
print('Packaged offline OCR passed')''')
    refused = docker('run', '--rm', '--network', 'none', '-e', 'LOAMY_MAIL_TRANSPORT=capture', 'loamy-enterprise:rehearsal', check=False)
    assert refused.returncode != 0
    report.update({'container_nonroot_uid': 10001, 'read_only_filesystem': True, 'readiness': 'passed',
                   'compiled_frontend': 'passed', 'offline_receipt_ocr': 'passed', 'unknown_api_route': '404', 'http_rejected': True,
                   'unexpected_host_rejected': True, 'missing_configuration_rejected': True,
                   'image': docker('image', 'inspect', 'loamy-enterprise:rehearsal', '--format', '{{.Id}}').stdout.strip()})
    target = ROOT.parent / 'output' / 'loamy-study' / 'production-container-rehearsal.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    print('Container rehearsal passed: non-root, read-only, TLS database, frontend, health and fail-closed checks.')
finally:
    # This random name is created by this script; never stop a user-owned service.
    docker('rm', '-f', name, check=False)
