-- Generated from an empty application schema; contains no user/test data.
-- Apply as migration owner, never as the runtime application role.
-- Provision loamy_enterprise_app separately, with LOGIN and a strong secret.
BEGIN;
CREATE SCHEMA enterprise;
REVOKE ALL ON SCHEMA enterprise FROM PUBLIC;
SET LOCAL search_path TO enterprise, pg_catalog;
CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE users (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, salt TEXT NOT NULL
, email_verified_at DOUBLE PRECISION, verification_method TEXT);

CREATE TABLE sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE businesses (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);

CREATE TABLE locations (
 id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id),
 name TEXT NOT NULL, address TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL,
 UNIQUE(business_id, name)
);

CREATE TABLE memberships (
 id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id),
 user_id TEXT NOT NULL REFERENCES users(id), role TEXT NOT NULL
 CHECK(role IN ('owner','manager','finance','front_desk','staff')),
 location_id TEXT REFERENCES locations(id), UNIQUE(business_id,user_id),
 CHECK ((role='owner' AND location_id IS NULL) OR (role!='owner' AND location_id IS NOT NULL))
);

CREATE TABLE invitations (
 id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE,
 business_id TEXT NOT NULL REFERENCES businesses(id), email TEXT NOT NULL,
 role TEXT NOT NULL, location_id TEXT NOT NULL REFERENCES locations(id),
 expires_at DOUBLE PRECISION NOT NULL, accepted_at DOUBLE PRECISION
);

CREATE TABLE audit_events (
 id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id),
 actor_id TEXT NOT NULL REFERENCES users(id), action TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE login_attempts (key TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);

CREATE TABLE email_verifications (
                  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                  expires_at DOUBLE PRECISION NOT NULL, consumed_at DOUBLE PRECISION, created_at DOUBLE PRECISION NOT NULL, method TEXT NOT NULL
                );

CREATE TABLE mail_outbox (
                  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), recipient TEXT NOT NULL,
                  subject TEXT NOT NULL, body TEXT NOT NULL, verification_url TEXT NOT NULL,
                  created_at DOUBLE PRECISION NOT NULL, transport TEXT NOT NULL, status TEXT NOT NULL
                );

CREATE TABLE financial_records (
              id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id),
              location_id TEXT NOT NULL REFERENCES locations(id), actor_id TEXT NOT NULL REFERENCES users(id),
              direction TEXT NOT NULL CHECK(direction IN ('income','expense')),
              amount_minor BIGINT NOT NULL CHECK(amount_minor>0), currency TEXT NOT NULL CHECK(currency='NGN'),
              occurred_on TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
              source TEXT NOT NULL DEFAULT 'manual', status TEXT NOT NULL DEFAULT 'posted' CHECK(status IN ('posted','voided')),
              created_at DOUBLE PRECISION NOT NULL, idempotency_key TEXT NOT NULL, void_reason TEXT, voided_at DOUBLE PRECISION,
              UNIQUE(business_id,idempotency_key)
            );

CREATE TABLE location_profiles (
            location_id TEXT PRIMARY KEY REFERENCES locations(id), invoice_name TEXT NOT NULL,
            address TEXT NOT NULL, payment_instructions TEXT NOT NULL
          );

CREATE TABLE services (
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id),
            location_id TEXT NOT NULL REFERENCES locations(id), name TEXT NOT NULL,
            description TEXT NOT NULL, price_minor BIGINT NOT NULL CHECK(price_minor>0),
            active BIGINT NOT NULL CHECK(active IN (0,1)), updated_at DOUBLE PRECISION NOT NULL
          );

CREATE TABLE orders (
            id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE,
            business_id TEXT NOT NULL REFERENCES businesses(id), location_id TEXT NOT NULL REFERENCES locations(id),
            actor_id TEXT NOT NULL REFERENCES users(id), customer_name TEXT NOT NULL, customer_contact TEXT NOT NULL,
            total_minor BIGINT NOT NULL CHECK(total_minor>0), status TEXT NOT NULL CHECK(status IN ('open','cancelled')),
            created_at DOUBLE PRECISION NOT NULL, order_date TEXT NOT NULL, profile_snapshot TEXT NOT NULL,
            request_hash TEXT NOT NULL, idempotency_key TEXT NOT NULL,
            cancelled_at DOUBLE PRECISION, cancelled_by TEXT REFERENCES users(id), cancel_reason TEXT,
            UNIQUE(business_id,idempotency_key)
          );

CREATE TABLE order_lines (
            order_id TEXT NOT NULL REFERENCES orders(id), position BIGINT NOT NULL,
            service_id TEXT NOT NULL REFERENCES services(id), name TEXT NOT NULL, description TEXT NOT NULL,
            quantity BIGINT NOT NULL CHECK(quantity>0), unit_minor BIGINT NOT NULL CHECK(unit_minor>0),
            PRIMARY KEY(order_id,position)
          );

CREATE TABLE invoices (
            id TEXT PRIMARY KEY, order_id TEXT NOT NULL UNIQUE REFERENCES orders(id), number TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('issued','cancelled')), issued_at DOUBLE PRECISION NOT NULL,
            issued_by TEXT NOT NULL REFERENCES users(id), due_on TEXT, snapshot TEXT NOT NULL, pdf BYTEA NOT NULL
          );

CREATE TABLE invoice_deliveries (
            id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES invoices(id), actor_id TEXT NOT NULL REFERENCES users(id),
            recipient TEXT NOT NULL, transport TEXT NOT NULL, status TEXT NOT NULL,
            created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL, idempotency_key TEXT NOT NULL,
            subject TEXT NOT NULL, body TEXT NOT NULL, UNIQUE(invoice_id,idempotency_key)
          );

CREATE TABLE payment_accounts (
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id), location_id TEXT NOT NULL REFERENCES locations(id),
            name TEXT NOT NULL, account_reference TEXT NOT NULL, UNIQUE(business_id,location_id,account_reference)
          );

CREATE TABLE payment_evidence (
            record_id TEXT PRIMARY KEY REFERENCES financial_records(id), business_id TEXT NOT NULL REFERENCES businesses(id),
            account_id TEXT REFERENCES payment_accounts(id), account_key TEXT NOT NULL, source_id TEXT NOT NULL,
            payer TEXT NOT NULL,narration TEXT NOT NULL, UNIQUE(business_id,account_key,source_id)
          );

CREATE TABLE invoice_accounts (
            invoice_id TEXT PRIMARY KEY REFERENCES invoices(id), account_id TEXT NOT NULL REFERENCES payment_accounts(id)
          );

CREATE TABLE payment_allocations (
            id TEXT PRIMARY KEY, business_id TEXT NOT NULL REFERENCES businesses(id), location_id TEXT NOT NULL REFERENCES locations(id),
            record_id TEXT NOT NULL REFERENCES financial_records(id), invoice_id TEXT NOT NULL REFERENCES invoices(id),
            amount_minor BIGINT NOT NULL CHECK(amount_minor>0), actor_id TEXT NOT NULL REFERENCES users(id), note TEXT NOT NULL,
            created_at DOUBLE PRECISION NOT NULL, idempotency_key TEXT NOT NULL, reversed_at DOUBLE PRECISION, reversed_by TEXT REFERENCES users(id), reversal_reason TEXT,
            UNIQUE(business_id,idempotency_key)
          );

CREATE TABLE expense_submissions (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            submitter_id TEXT NOT NULL REFERENCES users(id),status TEXT NOT NULL,revision BIGINT NOT NULL,
            created_at DOUBLE PRECISION NOT NULL,record_id TEXT UNIQUE REFERENCES financial_records(id)
          );

CREATE TABLE expense_versions (
            expense_id TEXT NOT NULL REFERENCES expense_submissions(id),revision BIGINT NOT NULL,
            vendor TEXT NOT NULL,purpose TEXT NOT NULL,category TEXT NOT NULL,amount_minor BIGINT NOT NULL CHECK(amount_minor>0),
            occurred_on TEXT NOT NULL,receipt BYTEA NOT NULL,mime TEXT NOT NULL,extension TEXT NOT NULL,receipt_hash TEXT NOT NULL,
            created_at DOUBLE PRECISION NOT NULL,idempotency_key TEXT NOT NULL,request_hash TEXT NOT NULL,
            PRIMARY KEY(expense_id,revision),UNIQUE(expense_id,idempotency_key)
          );

CREATE TABLE expense_events (
            id TEXT PRIMARY KEY,expense_id TEXT NOT NULL REFERENCES expense_submissions(id),revision BIGINT NOT NULL,
            actor_id TEXT NOT NULL REFERENCES users(id),action TEXT NOT NULL,reason TEXT NOT NULL,created_at DOUBLE PRECISION NOT NULL
          );

CREATE TABLE expense_creation_keys (
            business_id TEXT NOT NULL REFERENCES businesses(id),actor_id TEXT NOT NULL REFERENCES users(id),
            idempotency_key TEXT NOT NULL,expense_id TEXT NOT NULL REFERENCES expense_submissions(id),PRIMARY KEY(business_id,actor_id,idempotency_key)
          );

CREATE INDEX financial_location_date ON financial_records(business_id,location_id,occurred_on);

CREATE INDEX orders_location_date ON orders(business_id,location_id,order_date);

CREATE INDEX services_location ON services(business_id,location_id);

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
