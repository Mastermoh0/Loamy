# Business workspace release runbook

This runbook is prepared for Samuel's staging/production operators. It is not evidence that a public release occurred. Read `PRODUCTION-READINESS.md` and resolve its owner-side gates first.

## Stage and provision

Use an isolated Supabase/PostgreSQL staging database first. Keep production data/keys out of developer machines and CI. The personal app's existing schema/users are not migrated automatically.

As the database owner, provision a strong-password LOGIN role named `loamy_enterprise_app`, without superuser, database-creation, role-creation or replication privileges. For a Supabase connection pooler, its username may include the provider's project suffix; the base role must remain `loamy_enterprise_app`.

Review and apply `scripts/sql/enterprise/001_enterprise.sql` as the migration owner. It creates the `enterprise` schema atomically and intentionally fails if that schema already exists. Stop and inspect an unexpected existing schema; do not drop it or rerun a destructive test helper. Record the migration artifact/version. Future releases require separate forward migrations, not edits to an already applied migration.

Runtime connects only as the dedicated application role, using `sslmode=verify-full` and the provider's trusted CA. Keep the schema private and outside the Data API. Verify ordinary browser roles cannot read it. Keep administrative/migration credentials out of the application environment.

For the owner overview/receipt release, apply `002_receipt_extraction.sql` after 001. For an existing 001 installation, back up first and apply only 002; do not regenerate/drop the initial schema. Runtime requires `002_receipt_extraction`. Include both new tables in backup, retention and access reviews.

The release image installs Tesseract (executable plus English data) and Poppler. If packaging without this Dockerfile, install `tesseract-ocr`, `tesseract-ocr-eng` and `poppler-utils` from the OS repository. OCR uses temporary files and fixed subprocess commands; provide writable private `/tmp`, memory/CPU limits and process isolation. No cloud OCR credential or outbound service is required. Extraction accepts up to 2 MB, 20 megapixels for images and three PDF pages. Each external tool has a 20-second timeout; one extraction runs per worker, with ten uncached attempts per user/hour. A failed/unavailable reader leaves manual submission available. Keep OS parser packages updated; test resource limits and representative receipts in staging. Do not add the Docker socket to production: the optional Docker fallback is for guarded local preview only.

## Configure and build

Use `enterprise.env.example` as a list of required settings; populate a secret manager, not a committed file. Configure identical public web/API origins when using the combined container. Configure real SMTP and a test recipient before testing mail. Never set `LOAMY_LOCAL_PREVIEW=1` on this service.

Build `Dockerfile.enterprise` from the reviewed commit. Record the resulting image digest. The container serves the business-only compiled frontend and `/enterprise-api` from one origin. Its runtime dependencies are fixed in `requirements-production.lock`; the original `main.py`/Gmail backend is not packaged or started.

Run as the image's non-root user with a read-only root filesystem, a bounded writable `/tmp`, no added Linux capabilities and `no-new-privileges`. Provide the database CA read-only. No persistent application filesystem volume is needed: canonical records, receipt bytes and issued PDFs live in PostgreSQL.

Terminate public TLS at the approved proxy/load balancer. Limit direct backend access to that proxy and health monitoring. Set `FORWARDED_ALLOW_IPS` to the proxy's exact IP/network, never `*`, so Uvicorn recognizes only trusted forwarded HTTPS/client-address headers. Apply a 3 MB request limit and timeouts at the proxy as well as in the API. Respect the container's concurrency limit when sizing connection-pool capacity.

## Staging acceptance

- `/health/live` returns liveness; `/health/ready` returns readiness only when the database can be read. Responses reveal no database credentials. Wire an alert to readiness failures and server error rates.
- `/business` loads the compiled app. Unknown `/enterprise-api/...` paths return 404, not the SPA HTML. Original personal-app routes are not enabled in the business-only build.
- Plain HTTP to authenticated application paths is rejected once it reaches the API. Host and mutation Origin checks accept only configured origins. A real browser retains an HttpOnly/Secure/SameSite session and cannot use a captured verification link to upgrade a production account.
- Real verification mail arrives, verifies the matching signed-in account and rotates the session. Test a fresh browser, expiration and a replaced link. Confirm the account-recovery/support policy before inviting real users.
- Test separate businesses and every role, revocation, private receipt downloads and financial access boundaries. The database role cannot run DDL, alter issued financial amounts or overwrite audit/receipt history.
- Issue one invoice, retry generation, download its PDF and send exactly one test email with the original attachment. Verify actual recipient arrival and failure/uncertainty handling. Do not confuse provider acceptance with delivery.
- Allocate a partial payment, show the correct outstanding balance, retry, split another payment and attempt simultaneous over-allocation. Verify no duplicate income. Reverse with a reason and recheck cancellation/void guards. Connect real bank/Gmail sources only after account ownership/source uniqueness are established.
- Submit a staff receipt, request clarification, resubmit a new version, reject stale/self review, approve independently and post/link the matching debit once. Category totals must reconcile to the posted ledger and exclude voids.
- Back up and restore the private schema into another staging database. Compare financial rows and receipt/PDF bytes, check application-role permissions and agree recovery targets. Enable the provider's managed backup/retention policy before launch.

## Release and recovery

Obtain owner approval after staging acceptance. Deploy the same tested image digest, configuration and reviewed migration. Begin with a small pilot. No script in this work changes a live alias, deploys publicly or migrates Samuel's database automatically.

Keep the prior application image available. Roll back application traffic to that image when its schema compatibility is established; do not reverse a financial migration by deleting rows or dropping the schema. If rollback would lose compatibility, stop writes and use the reviewed forward-fix/recovery procedure. Restoring a backup requires an owner-approved recovery point and validation before traffic resumes.

The existing SQLite preview is development data only. There is deliberately no script that copies its passwords, sessions, test receipts or fictional bank credits into production.
