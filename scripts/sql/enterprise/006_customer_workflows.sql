-- Forward upgrade after 005; reviewed backup and migration owner required.
BEGIN;
SET LOCAL search_path TO enterprise, pg_catalog;
CREATE TABLE order_contacts (
          order_id TEXT PRIMARY KEY REFERENCES orders(id), customer_email TEXT NOT NULL,
          additional_emails TEXT NOT NULL, customer_whatsapp TEXT NOT NULL,
          preferred_channel TEXT NOT NULL CHECK(preferred_channel IN ('none','email','whatsapp')),
          whatsapp_consent BIGINT NOT NULL CHECK(whatsapp_consent IN (0,1))
        );

CREATE TABLE supplier_email_evidence (
          bill_id TEXT PRIMARY KEY REFERENCES supplier_bills(id), email_sha256 TEXT NOT NULL,
          sender TEXT NOT NULL, subject TEXT NOT NULL, attachment_sha256 TEXT NOT NULL
        );

CREATE TABLE reminder_plans (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            invoice_id TEXT NOT NULL REFERENCES invoices(id),actor_id TEXT NOT NULL REFERENCES users(id),channel TEXT NOT NULL CHECK(channel IN ('email','whatsapp')),
            recipient TEXT NOT NULL,next_run DOUBLE PRECISION NOT NULL,interval_days BIGINT NOT NULL CHECK(interval_days BETWEEN 1 AND 90),max_sends BIGINT NOT NULL CHECK(max_sends BETWEEN 1 AND 10),
            sent_count BIGINT NOT NULL DEFAULT 0 CHECK(sent_count>=0 AND sent_count<=max_sends),status TEXT NOT NULL CHECK(status IN ('active','running','paused','completed','stopped','cancelled')),created_at DOUBLE PRECISION NOT NULL,last_result TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,request_hash TEXT NOT NULL,UNIQUE(business_id,idempotency_key)
          );

CREATE TABLE message_receipts (
            attempt_id TEXT PRIMARY KEY,invoice_id TEXT NOT NULL REFERENCES invoices(id),purpose TEXT NOT NULL,
            phone_id TEXT NOT NULL,provider_id TEXT NOT NULL UNIQUE,status TEXT NOT NULL,updated_at DOUBLE PRECISION NOT NULL
          );

CREATE INDEX reminder_due ON reminder_plans(status,next_run);

ALTER TABLE reminder_plans ADD FOREIGN KEY(location_id,business_id) REFERENCES locations(id,business_id);
REVOKE ALL ON order_contacts,supplier_email_evidence,reminder_plans,message_receipts FROM PUBLIC;
GRANT SELECT,INSERT ON order_contacts,supplier_email_evidence,reminder_plans,message_receipts TO loamy_enterprise_app;
GRANT UPDATE(whatsapp_consent) ON order_contacts TO loamy_enterprise_app;
GRANT UPDATE(status,next_run,sent_count,last_result) ON reminder_plans TO loamy_enterprise_app;
GRANT UPDATE(status,updated_at) ON message_receipts TO loamy_enterprise_app;
INSERT INTO schema_migrations(version) VALUES ('006_customer_workflows');
COMMIT;
