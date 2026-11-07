-- Additive upgrade: apply after 001 as the migration owner, never as the app role.
BEGIN;
SET LOCAL search_path TO enterprise, pg_catalog;
CREATE TABLE receipt_extractions (
  id TEXT PRIMARY KEY,business_id TEXT NOT NULL REFERENCES businesses(id),location_id TEXT NOT NULL REFERENCES locations(id),
  actor_id TEXT NOT NULL REFERENCES users(id),receipt_hash TEXT NOT NULL,created_at DOUBLE PRECISION NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','success','failed')),engine TEXT,result TEXT,
  FOREIGN KEY(location_id,business_id) REFERENCES locations(id,business_id)
);
CREATE INDEX receipt_extraction_actor_time ON receipt_extractions(actor_id,created_at);
CREATE TABLE expense_extractions (
  expense_id TEXT NOT NULL,revision BIGINT NOT NULL,extraction_id TEXT NOT NULL REFERENCES receipt_extractions(id),
  PRIMARY KEY(expense_id,revision),FOREIGN KEY(expense_id,revision) REFERENCES expense_versions(expense_id,revision)
);
REVOKE ALL ON receipt_extractions,expense_extractions FROM PUBLIC;
GRANT SELECT,INSERT ON receipt_extractions,expense_extractions TO loamy_enterprise_app;
GRANT UPDATE(status,engine,result) ON receipt_extractions TO loamy_enterprise_app;
INSERT INTO schema_migrations(version) VALUES ('002_receipt_extraction');
COMMIT;
