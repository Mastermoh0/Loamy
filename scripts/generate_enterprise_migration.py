"""Generate the reviewed initial private PostgreSQL schema without reading preview data."""
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from enterprise_preview import create_app


def generate():
    os.environ['LOAMY_LOCAL_PREVIEW'] = '1'
    os.environ['LOAMY_MAIL_TRANSPORT'] = 'capture'
    scratch = ROOT / '.local-data' / 'migration-generation'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        path = Path(directory) / 'schema.sqlite3'
        create_app(path)
        with closing(sqlite3.connect(path)) as connection:
            # Freeze migration 001; later additive tables belong in migration 002.
            objects = connection.execute("SELECT sql FROM sqlite_master WHERE type IN ('table','index') AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%' AND tbl_name NOT IN ('receipt_extractions','expense_extractions') ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END,rowid").fetchall()
    statements = []
    for (sql,) in objects:
        sql = re.sub(r'\bINTEGER\b', 'BIGINT', sql, flags=re.I)
        sql = re.sub(r'\bREAL\b', 'DOUBLE PRECISION', sql, flags=re.I)
        sql = re.sub(r'\bBLOB\b', 'BYTEA', sql, flags=re.I)
        statements.append(sql + ';')
    prefix = '''-- Generated from an empty application schema; contains no user/test data.
-- Apply as migration owner, never as the runtime application role.
-- Provision loamy_enterprise_app separately, with LOGIN and a strong secret.
BEGIN;
CREATE SCHEMA enterprise;
REVOKE ALL ON SCHEMA enterprise FROM PUBLIC;
SET LOCAL search_path TO enterprise, pg_catalog;
CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());
'''
    suffix = '''
-- Database-level tenant/location consistency, in addition to API authorization.
ALTER TABLE locations ADD UNIQUE (id,business_id);
ALTER TABLE financial_records ADD UNIQUE (id,business_id,location_id);
ALTER TABLE orders ADD UNIQUE (id,business_id,location_id);
ALTER TABLE payment_accounts ADD UNIQUE (id,business_id,location_id);
ALTER TABLE memberships ADD FOREIGN KEY (location_id,business_id) REFERENCES locations(id,business_id);
ALTER TABLE invitations ADD FOREIGN KEY (location_id,business_id) REFERENCES locations(id,business_id);
ALTER TABLE financial_records ADD FOREIGN KEY (location_id,business_id) REFERENCES locations(id,business_id);
ALTER TABLE orders ADD FOREIGN KEY (location_id,business_id) REFERENCES locations(id,business_id);
ALTER TABLE services ADD FOREIGN KEY (location_id,business_id) REFERENCES locations(id,business_id);
ALTER TABLE payment_accounts ADD FOREIGN KEY (location_id,business_id) REFERENCES locations(id,business_id);
ALTER TABLE expense_submissions ADD FOREIGN KEY (location_id,business_id) REFERENCES locations(id,business_id);
ALTER TABLE payment_allocations ADD FOREIGN KEY (record_id,business_id,location_id) REFERENCES financial_records(id,business_id,location_id);
ALTER TABLE payment_allocations ADD FOREIGN KEY (location_id,business_id) REFERENCES locations(id,business_id);
ALTER TABLE expense_submissions ADD FOREIGN KEY (record_id,business_id,location_id) REFERENCES financial_records(id,business_id,location_id);
CREATE INDEX sessions_expiry ON sessions(expires_at);
CREATE INDEX login_attempts_key_time ON login_attempts(key,created_at);
CREATE INDEX allocations_record_active ON payment_allocations(record_id) WHERE reversed_at IS NULL;
CREATE INDEX allocations_invoice_active ON payment_allocations(invoice_id) WHERE reversed_at IS NULL;
CREATE INDEX receipt_hash_lookup ON expense_versions(receipt_hash);
CREATE INDEX mail_user_time ON mail_outbox(user_id,transport,created_at);
CREATE INDEX verification_user_time ON email_verifications(user_id,created_at);
CREATE INDEX invoice_delivery_time ON invoice_deliveries(invoice_id,created_at);
CREATE INDEX expense_location_time ON expense_submissions(business_id,location_id,created_at);
CREATE INDEX expense_event_time ON expense_events(expense_id,created_at);
CREATE INDEX login_attempts_expiry ON login_attempts(created_at);
REVOKE ALL ON ALL TABLES IN SCHEMA enterprise FROM PUBLIC;
DO $private$
DECLARE browser_role TEXT;
BEGIN
  FOREACH browser_role IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=browser_role) THEN
      EXECUTE format('REVOKE ALL ON SCHEMA enterprise FROM %I', browser_role);
      EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA enterprise FROM %I', browser_role);
      EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA enterprise REVOKE ALL ON TABLES FROM %I', browser_role);
    END IF;
  END LOOP;
END $private$;
ALTER DEFAULT PRIVILEGES IN SCHEMA enterprise REVOKE ALL ON TABLES FROM PUBLIC;
GRANT USAGE ON SCHEMA enterprise TO loamy_enterprise_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA enterprise TO loamy_enterprise_app;
REVOKE INSERT,UPDATE,DELETE ON schema_migrations FROM loamy_enterprise_app;
REVOKE UPDATE,DELETE ON audit_events,expense_events,expense_versions,order_lines FROM loamy_enterprise_app;
REVOKE UPDATE,DELETE ON financial_records,orders,invoices FROM loamy_enterprise_app;
GRANT UPDATE(status,void_reason,voided_at) ON financial_records TO loamy_enterprise_app;
GRANT UPDATE(status,cancel_reason,cancelled_at,cancelled_by) ON orders TO loamy_enterprise_app;
GRANT UPDATE(status) ON invoices TO loamy_enterprise_app;
INSERT INTO schema_migrations(version) VALUES ('001_enterprise');
COMMIT;
'''
    target = ROOT / 'scripts' / 'sql' / 'enterprise' / '001_enterprise.sql'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(prefix + '\n\n'.join(statements) + '\n' + suffix, encoding='utf-8', newline='\n')
    print('Generated scripts/sql/enterprise/001_enterprise.sql (no data)')


if __name__ == '__main__':
    generate()
