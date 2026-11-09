-- Additive pricing upgrade after 004. Apply as migration owner after backup.
BEGIN;
SET LOCAL search_path TO enterprise, pg_catalog;
CREATE TABLE location_pricing (
  location_id TEXT PRIMARY KEY REFERENCES locations(id), tax_label TEXT NOT NULL,
  tax_rate_bps BIGINT NOT NULL CHECK(tax_rate_bps BETWEEN 0 AND 10000)
);
CREATE TABLE order_pricing (
  order_id TEXT PRIMARY KEY REFERENCES orders(id), subtotal_minor BIGINT NOT NULL CHECK(subtotal_minor>0),
  discount_type TEXT NOT NULL CHECK(discount_type IN ('none','fixed','percent')),
  discount_value_hundredths BIGINT NOT NULL CHECK(discount_value_hundredths>=0),
  discount_minor BIGINT NOT NULL CHECK(discount_minor>=0 AND discount_minor<subtotal_minor),
  discount_reason TEXT NOT NULL, tax_label TEXT NOT NULL,
  tax_rate_bps BIGINT NOT NULL CHECK(tax_rate_bps BETWEEN 0 AND 10000),
  tax_minor BIGINT NOT NULL CHECK(tax_minor>=0)
);
REVOKE ALL ON location_pricing,order_pricing FROM PUBLIC;
GRANT SELECT,INSERT ON location_pricing,order_pricing TO loamy_enterprise_app;
GRANT UPDATE(tax_label,tax_rate_bps) ON location_pricing TO loamy_enterprise_app;
INSERT INTO schema_migrations(version) VALUES ('005_pricing');
COMMIT;
