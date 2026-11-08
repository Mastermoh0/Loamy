-- Additive release after 003; apply as migration owner.
BEGIN;
SET LOCAL search_path TO enterprise, pg_catalog;
CREATE TABLE customer_notices (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            invoice_id TEXT NOT NULL REFERENCES invoices(id),actor_id TEXT NOT NULL REFERENCES users(id),kind TEXT NOT NULL,
            recipient TEXT NOT NULL,balance_hash TEXT NOT NULL,subject TEXT NOT NULL,body TEXT NOT NULL,
            status TEXT NOT NULL,transport TEXT NOT NULL,created_at DOUBLE PRECISION NOT NULL,updated_at DOUBLE PRECISION NOT NULL,
            idempotency_key TEXT NOT NULL,dedupe_key TEXT NOT NULL,UNIQUE(business_id,idempotency_key),UNIQUE(invoice_id,dedupe_key)
          );

CREATE TABLE invoice_shares (
            id TEXT PRIMARY KEY,token_hash TEXT NOT NULL UNIQUE,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            invoice_id TEXT NOT NULL REFERENCES invoices(id),actor_id TEXT NOT NULL REFERENCES users(id),created_at DOUBLE PRECISION NOT NULL,expires_at DOUBLE PRECISION NOT NULL,revoked_at DOUBLE PRECISION
          );

CREATE TABLE recurring_commitments (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            actor_id TEXT NOT NULL REFERENCES users(id),vendor TEXT NOT NULL,description TEXT NOT NULL,amount_minor BIGINT NOT NULL CHECK(amount_minor>0),
            cadence TEXT NOT NULL,next_due TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('active','cancelled')),
            created_at DOUBLE PRECISION NOT NULL,cancelled_at DOUBLE PRECISION,cancel_reason TEXT,idempotency_key TEXT NOT NULL,request_hash TEXT NOT NULL,
            UNIQUE(business_id,idempotency_key)
          );

CREATE INDEX customer_notice_invoice_time ON customer_notices(invoice_id,updated_at);

ALTER TABLE customer_notices ADD FOREIGN KEY(location_id,business_id) REFERENCES locations(id,business_id);
ALTER TABLE invoice_shares ADD FOREIGN KEY(location_id,business_id) REFERENCES locations(id,business_id);
ALTER TABLE recurring_commitments ADD FOREIGN KEY(location_id,business_id) REFERENCES locations(id,business_id);
REVOKE ALL ON customer_notices,invoice_shares,recurring_commitments FROM PUBLIC;
GRANT SELECT,INSERT ON customer_notices,invoice_shares,recurring_commitments TO loamy_enterprise_app;
GRANT UPDATE(status,updated_at) ON customer_notices TO loamy_enterprise_app;
GRANT UPDATE(revoked_at) ON invoice_shares TO loamy_enterprise_app;
GRANT UPDATE(status,cancelled_at,cancel_reason) ON recurring_commitments TO loamy_enterprise_app;
INSERT INTO schema_migrations(version) VALUES ('004_reports_notifications');
COMMIT;
