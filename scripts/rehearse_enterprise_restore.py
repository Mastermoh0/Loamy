"""Backup/restore only the disposable named local rehearsal database; never production."""
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import quote, urlencode
import psycopg
from psycopg import sql


def snapshot(connection):
    tables = connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='enterprise' ORDER BY tablename").fetchall()
    return {table: sorted([repr(row) for row in connection.execute(sql.SQL('SELECT * FROM enterprise.{}').format(sql.Identifier(table))).fetchall()]) for (table,) in tables}

ROOT = Path(__file__).resolve().parents[1]
password = (ROOT / '.local-data/postgres-test.env').read_text().strip().split('=', 1)[1]
query = urlencode({'sslmode': 'verify-full', 'sslrootcert': str(ROOT / '.local-data/postgres-certs/ca.crt')})
dsn = f'postgresql://postgres:{quote(password)}@127.0.0.1:55432/enterprise_test?{query}'
with psycopg.connect(dsn) as connection:
    if connection.info.dbname != 'enterprise_test' or connection.info.host != '127.0.0.1':
        raise RuntimeError('Restore rehearsal is restricted to the disposable loopback database')
    expected = connection.execute('SELECT count(*) FROM enterprise.users').fetchone()[0]
    if expected < 1:
        raise RuntimeError('Run the PostgreSQL release tests before backup/restore')
    original = snapshot(connection)
name = 'enterprise_restore_test_' + secrets.token_hex(4)
compose = ['docker', 'compose', '--env-file', '.local-data/postgres-test.env', '-f', 'compose.enterprise-test.yml', '-p', 'loamy-enterprise-test', 'exec', '-T', 'postgres']
commands = [
    ['pg_dump', '-U', 'postgres', '-d', 'enterprise_test', '-n', 'enterprise', '-Fc', '-f', '/tmp/enterprise-rehearsal.dump'],
    ['createdb', '-U', 'postgres', name],
    ['pg_restore', '-U', 'postgres', '-d', name, '--exit-on-error', '/tmp/enterprise-rehearsal.dump'],
]
for command in commands:
    subprocess.run(compose + command, cwd=ROOT, check=True, capture_output=True, timeout=60)
restored_dsn = f'postgresql://loamy_enterprise_app:{quote(password)}@127.0.0.1:55432/{name}?{query}'
with psycopg.connect(restored_dsn) as restored:
    actual = restored.execute('SELECT count(*) FROM enterprise.users').fetchone()[0]
    version = restored.execute('SELECT version FROM enterprise.schema_migrations ORDER BY version DESC LIMIT 1').fetchone()[0]
    if actual != expected or version != '004_reports_notifications' or snapshot(restored) != original:
        raise RuntimeError('Restored data or migration version differs')
print(f'Backup/restore passed: all {len(original)} tables, including receipt/PDF bytes and financial rows, match; source unchanged.')
