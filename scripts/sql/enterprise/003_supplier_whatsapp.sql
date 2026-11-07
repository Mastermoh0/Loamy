-- Additive upgrade after 002; apply as migration owner, never runtime role.
BEGIN;
SET LOCAL search_path TO enterprise, pg_catalog;
CREATE TABLE supplier_bills (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            actor_id TEXT NOT NULL REFERENCES users(id),vendor TEXT NOT NULL,vendor_key TEXT NOT NULL,reference TEXT NOT NULL,reference_key TEXT NOT NULL,
            description TEXT NOT NULL,category TEXT NOT NULL,amount_minor BIGINT NOT NULL CHECK(amount_minor>0),issued_on TEXT NOT NULL,due_on TEXT NOT NULL,
            receipt BYTEA NOT NULL,mime TEXT NOT NULL,extension TEXT NOT NULL,receipt_hash TEXT NOT NULL,extraction_id TEXT REFERENCES receipt_extractions(id),
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','voided')),void_reason TEXT,voided_at DOUBLE PRECISION,
            created_at DOUBLE PRECISION NOT NULL,idempotency_key TEXT NOT NULL,request_hash TEXT NOT NULL,
            UNIQUE(business_id,idempotency_key)
          );

CREATE TABLE supplier_payments (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            bill_id TEXT NOT NULL REFERENCES supplier_bills(id),record_id TEXT NOT NULL REFERENCES financial_records(id),
            amount_minor BIGINT NOT NULL CHECK(amount_minor>0),actor_id TEXT NOT NULL REFERENCES users(id),reason TEXT NOT NULL,
            created_at DOUBLE PRECISION NOT NULL,idempotency_key TEXT NOT NULL,request_hash TEXT NOT NULL,reversed_at DOUBLE PRECISION,reversed_by TEXT REFERENCES users(id),reverse_reason TEXT,
            UNIQUE(business_id,idempotency_key)
          );

CREATE TABLE whatsapp_challenges (
            token_hash TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            actor_id TEXT NOT NULL REFERENCES users(id),phone_id TEXT NOT NULL,created_at DOUBLE PRECISION NOT NULL,expires_at DOUBLE PRECISION NOT NULL,used_at DOUBLE PRECISION
          );

CREATE TABLE whatsapp_senders (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            actor_id TEXT NOT NULL REFERENCES users(id),phone_id TEXT NOT NULL,sender TEXT NOT NULL,linked_at DOUBLE PRECISION NOT NULL,revoked_at DOUBLE PRECISION,
            UNIQUE(phone_id,sender)
          );

CREATE TABLE whatsapp_messages (
            id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
            actor_id TEXT NOT NULL REFERENCES users(id),sender_link_id TEXT REFERENCES whatsapp_senders(id),phone_id TEXT NOT NULL,
            provider_id TEXT NOT NULL,sender TEXT NOT NULL,media_id TEXT,expected_hash TEXT,caption TEXT NOT NULL,sent_at DOUBLE PRECISION NOT NULL,received_at DOUBLE PRECISION NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('queued','ready','failed','submitted','discarded')),
            attempts BIGINT NOT NULL DEFAULT 0,lease_until DOUBLE PRECISION,receipt BYTEA,mime TEXT,extension TEXT,receipt_hash TEXT,error TEXT,
            expense_id TEXT UNIQUE REFERENCES expense_submissions(id),simulated BIGINT NOT NULL DEFAULT 0,discard_reason TEXT,
            UNIQUE(phone_id,provider_id)
          );

CREATE UNIQUE INDEX supplier_bill_active_reference ON supplier_bills(business_id,vendor_key,reference_key) WHERE status='open';

CREATE UNIQUE INDEX supplier_bill_active_receipt ON supplier_bills(business_id,receipt_hash) WHERE status='open';

CREATE INDEX supplier_bill_location ON supplier_bills(business_id,location_id,due_on);

CREATE INDEX supplier_payment_record ON supplier_payments(record_id,reversed_at);

CREATE INDEX whatsapp_message_queue ON whatsapp_messages(status,lease_until);

CREATE INDEX whatsapp_message_actor ON whatsapp_messages(business_id,location_id,actor_id,received_at);

ALTER TABLE supplier_bills ADD UNIQUE(id,business_id,location_id);
ALTER TABLE supplier_bills ADD FOREIGN KEY(location_id,business_id) REFERENCES locations(id,business_id);
ALTER TABLE supplier_payments ADD FOREIGN KEY(location_id,business_id) REFERENCES locations(id,business_id);
ALTER TABLE supplier_payments ADD FOREIGN KEY(bill_id,business_id,location_id) REFERENCES supplier_bills(id,business_id,location_id);
ALTER TABLE supplier_payments ADD FOREIGN KEY(record_id,business_id,location_id) REFERENCES financial_records(id,business_id,location_id);
ALTER TABLE whatsapp_challenges ADD FOREIGN KEY(location_id,business_id) REFERENCES locations(id,business_id);
ALTER TABLE whatsapp_senders ADD FOREIGN KEY(location_id,business_id) REFERENCES locations(id,business_id);
ALTER TABLE whatsapp_messages ADD FOREIGN KEY(location_id,business_id) REFERENCES locations(id,business_id);
REVOKE ALL ON supplier_bills,supplier_payments,whatsapp_challenges,whatsapp_senders,whatsapp_messages FROM PUBLIC;
GRANT SELECT,INSERT ON supplier_bills,supplier_payments,whatsapp_challenges,whatsapp_senders,whatsapp_messages TO loamy_enterprise_app;
GRANT UPDATE(status,void_reason,voided_at) ON supplier_bills TO loamy_enterprise_app;
GRANT UPDATE(reversed_at,reversed_by,reverse_reason) ON supplier_payments TO loamy_enterprise_app;
GRANT UPDATE(used_at) ON whatsapp_challenges TO loamy_enterprise_app;
GRANT UPDATE(actor_id,location_id,linked_at,revoked_at) ON whatsapp_senders TO loamy_enterprise_app;
GRANT UPDATE(status,attempts,lease_until,receipt,mime,extension,receipt_hash,error,expense_id,discard_reason) ON whatsapp_messages TO loamy_enterprise_app;
CREATE FUNCTION preserve_whatsapp_evidence() RETURNS trigger LANGUAGE plpgsql SET search_path=enterprise,pg_catalog AS $guard$
BEGIN
  IF OLD.receipt IS NOT NULL AND (NEW.receipt IS DISTINCT FROM OLD.receipt OR NEW.receipt_hash IS DISTINCT FROM OLD.receipt_hash OR NEW.mime IS DISTINCT FROM OLD.mime OR NEW.extension IS DISTINCT FROM OLD.extension) THEN
    RAISE EXCEPTION 'WhatsApp receipt evidence is immutable';
  END IF;
  RETURN NEW;
END $guard$;
CREATE TRIGGER whatsapp_evidence_immutable BEFORE UPDATE ON whatsapp_messages FOR EACH ROW EXECUTE FUNCTION preserve_whatsapp_evidence();
INSERT INTO schema_migrations(version) VALUES ('003_supplier_whatsapp');
COMMIT;
