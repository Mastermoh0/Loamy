# Business workspace: production rehearsal

Status: **production candidate for owner-controlled staging; not approved for live customer data yet**.

This work prepares the new business workflows without accessing Samuel's database, sending customer messages, changing DNS or deploying to a public host. It does not certify the original personal/Gmail backend or Android build as production-ready.

## What changed

- Added `enterprise_production:create_app`, separate from the guarded SQLite preview. Production requires PostgreSQL, explicit HTTPS origins, a least-privilege application role, verified database TLS and SMTP. Captured verification cannot enable production accounts.
- Added an additive migration in `scripts/sql/enterprise/001_enterprise.sql`. It creates a private `enterprise` schema rather than modifying the original public users/financial tables. Browser/API roles are denied schema access; only the server's dedicated application role receives the required permissions. Runtime cannot create tables, alter financial amounts or rewrite audit/receipt/line-item history.
- Ported the existing workflow queries to PostgreSQL with SERIALIZABLE transactions. A concurrent conflict returns a retryable 409 rather than silently allocating the same income twice. Money remains integer kobo with BIGINT storage; displayed server decimal strings avoid an unnecessary floating-point conversion.
- Added secure/HttpOnly/SameSite session cookies, strict Host/Origin/HTTPS checks, bounded request bodies including chunked bodies, HSTS, non-cached API responses, generic health checks and non-root/read-only container operation.
- Added a business-only production frontend build, served from the same origin as its API. It does not activate the original personal-app routes, Gmail scheduler or localStorage identity. Production verification links use the configured public origin; local preview wording is not printed on newly issued production invoices.
- Added a repeatable container build, explicit dependency lock, release CI and scripts for local TLS/database/container/restore rehearsal. Database migrations are never run by the application at startup.
- Updated vulnerable web tooling/framework packages. The production npm dependency audit and pinned Python runtime audit report zero known advisories at this rehearsal's audit time. This is not a guarantee against undiscovered vulnerabilities.

## Evidence

| Check | Result |
|---|---|
| Existing business/order/invoice/payment/expense regression cases | 34 passed |
| Production configuration, TLS PostgreSQL, permissions, compiled routes and concurrent allocation cases | 5 passed |
| Total final backend tests | 39 passed |
| Business-only production build and targeted frontend lint | Passed |
| PostgreSQL server-certificate verification | Passed using an isolated local test CA |
| Simultaneous allocations against one income record | One succeeds; competing request rejected; no duplicated income |
| Database owner/public-schema separation | Original test sentinel unchanged; anon/authenticated/service roles denied enterprise schema access |
| Runtime role immutability | DDL, audit rewrite and financial-amount update rejected |
| Container | Non-root UID 10001, read-only filesystem, capability drops, readiness and compiled frontend checked |
| HTTP/Host/missing configuration rejection | Passed |
| Backup/restore | All 26 tables compared, including original receipt/PDF bytes and financial rows; source unchanged |
| npm production dependency audit | Zero known advisories |
| Pinned Python production dependency audit | Zero known advisories |

Rehearsal files live under the ignored `.local-data/` directory. The sanitized container result is also saved at `../output/loamy-study/production-container-rehearsal.json`. Tests use fictional identities and data. SMTP is mocked in workflow tests: no real customer or provider delivery was claimed.

The container test emulates an approved reverse proxy's HTTPS header over loopback. It **does not** prove a public TLS certificate, public DNS, real proxy forwarding rules or real email deliverability. The database connection itself uses actual TLS with `verify-full` and a test certificate.

The original Capacitor/iOS asset-generation dependency chain still has four moderate development-tool advisories. They are outside the deployed business web runtime. No forced downgrade was applied to the mobile toolchain; an Android/iOS release needs its own follow-up and device/build checks. The original repository's broad lint backlog is also outside the targeted business-module checks.

## What Samuel must supply or approve before go-live

1. **A separate staging database and deployment target.** Provision the migration owner and dedicated application role; apply/review the migration there. Do not copy the local test database, test CA or test credentials. Confirm the private schema is not exposed through the Supabase Data API.
2. **Identity policy.** This candidate has verified business accounts separate from the old personal accounts. Decide whether that is the intended pilot or whether shared sign-in/account recovery must be integrated with the existing identity provider before launch. No unsafe automatic mapping by email or legacy browser user ID has been added.
3. **A real sender and test mailbox.** Configure SMTP secrets and sender identity, then test verification, invoice attachment, refusal, timeout and recipient arrival in staging. Acceptance by a mail server is not an inbox-delivery guarantee.
4. **The actual HTTPS host/reverse proxy.** Confirm exact allowed origins and trusted proxy IPs. Exercise Secure cookies, CSRF/Host rejection, same-origin `/business` routing and unauthorized access from a real browser on the staging domain.
5. **Backup, retention and monitoring policy.** Enable managed database backups/encryption, choose recovery targets and repeat restore validation with staging data. Wire alerts to readiness/runtime failures. Receipt/PDF bytes are durable private database data; there is no production dependence on a container's writable local disk.
6. **Bank/Gmail scope.** Manual recorded payments and reviewed allocations work. A real bank/Gmail connector and source/account ownership must be integrated and tested separately before claiming live matching. Automatic settlement, moving/refunding money, WhatsApp capture and receipt OCR are not part of this candidate.
7. **A controlled pilot and release approval.** Exercise owner, manager, finance, front desk and staff accounts across two businesses/locations, with anonymized representative receipts/alerts. Approve the application image and a rollback window after the real staging checks pass.

## Reproduce the rehearsal

The implementation is published on the fork's `mohammeds-branch` (initial feature commit `3294da8`). The CI workflow is prepared, but no remote GitHub Actions run was triggered/verified by this work. It is configured for pull requests/manual dispatch rather than this branch push alone. The checks described above were executed locally; see `SAMUEL-PRODUCTION-HANDOFF.md` for publication and later validation records.

Use Docker Desktop/Engine, Node 22 and Python 3.14. Install `requirements-rehearsal.txt` into an isolated environment and run `npm ci`. Generate a random `POSTGRES_TEST_PASSWORD` into `.local-data/postgres-test.env`; never commit it. Then:

```text
python scripts/create_enterprise_test_certs.py
python scripts/generate_enterprise_migration.py
docker compose --env-file .local-data/postgres-test.env -f compose.enterprise-test.yml -p loamy-enterprise-test up -d --wait
```

Build with `VITE_ENTERPRISE_ENABLED=true` and `VITE_ENTERPRISE_ONLY=true`, then set `LOAMY_RUN_POSTGRES_TESTS=1` for:

```text
python -m unittest test_workspace_features test_workspace_orders test_workspace_invoices test_workspace_payments test_workspace_expenses test_enterprise_production -v
python scripts/rehearse_enterprise_restore.py
docker build -f Dockerfile.enterprise -t loamy-enterprise:rehearsal .
python scripts/rehearse_enterprise_container.py
npm audit --omit=dev
python -m pip_audit -r requirements-production.lock --no-deps --disable-pip
```

The rehearsal tests deliberately reset only `enterprise_test` on loopback; do not repurpose their helpers for another database. The compose database is disposable tmpfs. The local CA is short-lived test material. CI repeats this process without production secrets through `.github/workflows/enterprise-release-rehearsal.yml`.

See `deploy/ENTERPRISE-RUNBOOK.md` for staging/release steps. The local SQLite preview and its fictional records remain available through `npm run dev:workspace`.

Technical references: [Supabase database connections and certificate verification](https://supabase.com/docs/guides/database/connecting-to-postgres), [Psycopg transaction handling and serializable conflicts](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).
