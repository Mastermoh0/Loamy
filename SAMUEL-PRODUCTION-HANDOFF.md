# Samuel's production handoff: Loamy business features

> **Living handoff for Samuel, his team and his AI agents.** Update this file after each meaningful feature or integration change. It is an implementation map and release checklist, not evidence that a live deployment has happened.

Last updated: **7 November 2026, Africa/Lagos**.

| Item | Current position |
|---|---|
| Product/repository | Loamy; called “Lumi” in the development conversation |
| Original repository | https://github.com/Sammythe-King/Loamy |
| Development fork | https://github.com/Mastermoh0/Loamy |
| Working branch | `mohammeds-branch` |
| Base commit inspected | `cd6d768`; this identifies the base, **not a commit containing the new implementation** |
| Implementation location at this update | Published to `Mastermoh0/Loamy:mohammeds-branch`; feature commit `3294da82ab452052969ff4a9ba32f7ea6225d469` was verified against the remote branch. Later handoff updates follow in the branch history. No upstream merge or deployment has been performed. |
| Current readiness | New business workflows implemented; local production rehearsal passed. Real staging integration and owner release approval remain. |
| Access used | Local development and disposable rehearsal infrastructure only; no access to Samuel's production backend/database. |

Published implementation: [feature commit 3294da8](https://github.com/Mastermoh0/Loamy/commit/3294da82ab452052969ff4a9ba32f7ea6225d469). Current handoff: [SAMUEL-PRODUCTION-HANDOFF.md on the development branch](https://github.com/Mastermoh0/Loamy/blob/mohammeds-branch/SAMUEL-PRODUCTION-HANDOFF.md). Review later branch commits as well as the initial feature commit.

## 1. Read this first

The branch adds a business/location workspace to the existing React/Vite project. It includes authenticated roles, financial records, services/orders, invoices, reviewed payment allocations and receipt-based staff expenses.

There are **two distinct execution modes**:

- **Local preview:** `npm run dev:workspace`, SQLite, fictional accounts/data and captured email by default. Never deploy this launcher as production.
- **Production candidate:** `enterprise_production:create_app`, a private PostgreSQL schema, real SMTP configuration, secure sessions, strict HTTPS/origin checks and a business-only compiled frontend. This was rehearsed locally, not released publicly.

The candidate intentionally keeps business accounts separate from the original personal-app accounts. It does not import the original `main.py`/Gmail backend or trust a personal-app `localStorage` user ID. Merging the code alone does **not** unify identity, financial records or bank connections.

The recorded test cases and release rehearsal validate the stated paths. They are not a certification of the original application's entire security, mobile builds or unknown production configuration. See section 13 for the newest supplier/WhatsApp changes and validation; earlier counts are historical.

## 2. What is implemented

“Implemented” below means working code exists and has the recorded local/rehearsal validation. It does not mean enabled on Samuel's live website.

| Feature | Behavior delivered | Production integration still required |
|---|---|---|
| Business and locations | Create a business, first/additional locations, business switching and scoped membership | Decide how existing businesses/locations are mapped without exposing or duplicating records |
| Team permissions | Owner, manager, finance, front desk and staff; one assigned location for non-owners; expiring one-use invitations; revocation and audit history | Decide identity/account linking; invitation links are generated but not automatically emailed |
| Email verification | Expiring one-use links, resend cooldown, matching signed-in recipient, session rotation | Configure real sender and test arrival; local capture is not mailbox-ownership proof |
| Location financial records | Exact NGN income/expenses, scoped totals, retry protection and reasoned voids preserving history | Connect existing canonical transactions/imports; do not sum independent copies of the same money |
| Service catalogue | Per-location service names, descriptions, prices and availability; editable order/invoice business details | Confirm pilot services and pricing rules; no inventory, room-availability, tax or discount engine |
| Front-desk orders | Customer full name plus phone/email, quantities, exact totals, unique IDs/references, immutable price snapshots, today/history lists and cancellation history | Confirm operating rules and how existing customers/orders should be linked |
| Invoices | One stable invoice per order, optional due date, issued snapshot/PDF, preview/download and cancellation marking | Configure actual issuer/payment instructions; shared invoice numbering/migration policy if existing invoices must coexist |
| Invoice email | PDF attachment, captured test mailbox, SMTP path, delivery history, retry deduplication and explicit resend | Actual sender/recipient checks, deliverability and operational email monitoring |
| Payment review | Receiving accounts, recorded cash/test-credit evidence, account/reference suggestions and manual confirmation | Real Gmail/bank adapter, source/account ownership and representative alert fixtures |
| Partial/split payments | Multiple payments per invoice, one credit split across invoices, paid/part-paid/unpaid/overpaid state and outstanding/excess amounts | Validate against the pilot's real payment evidence; no automatic settlement or bank transfers |
| Payment corrections | Reasoned allocation reversals; guards on cancelling allocated invoices or voiding allocated income | Define operational correction/refund responsibilities; reversal never moves/refunds money |
| Staff expenses | Private JPEG/PNG/PDF receipt, submitter identity, clarification/rejection/resubmission, immutable versions and independent approval | Confirm expense policy, retention, account recovery and staff onboarding |
| Posting and categories | Explicit posting or linking an existing matching debit, duplicate guards, canonical category totals and evidence drill-down | Reconcile future real bank debits to receipts rather than posting the same expense again |
| Owner overview | Combined/per-location recorded cash movements, current receivables, order value, receiving-account credits and expense review counts | Connect real bank ingestion separately; no bank balance, profit calculation or historical receivables reconstruction is inferred |
| Offline receipt extraction | JPEG/PNG, text PDF and scanned PDF suggestions for vendor, total and date; editable draft, exact-file provenance and independent approval | Install native OCR tools; assess representative receipts in staging and agree retention/resource limits |
| Supplier invoices/payables | Private original invoice imports, exact liabilities/due dates, duplicate guards, partial/split allocations to existing expense debits, reversals and reasoned voids; current owner payables | Confirm real supplier references, payment evidence and operating policy; no funds transfer or full accrual accounting |
| WhatsApp receipt intake | Operator-scoped signed incoming webhooks, verified-account sender linking, durable media queue/worker, private inbox and editable expense drafts with original evidence | Configure Meta app/business number/token/version/routing, supervise worker, validate real provider receipts; group capture remains disabled |
| Production foundation | Private PostgreSQL migration, least-privilege role, serializable writes, secure configuration, container/health checks, dependency lock and release CI definition | Actual staging deployment, provider configuration, backups/alerts and release approval |

### Role boundaries

| Role | Location scope | Catalogue/profile | Orders/invoice issue/email | Credit review/allocation/ledger | Receipt expenses |
|---|---|---|---|---|---|
| Owner | All locations in owned business | Manage | Manage | Manage | Submit; review others; post/link |
| Manager | Assigned location | Manage | Manage | Manage | Submit; review others; post/link |
| Finance | Assigned location | Read | Read/download; cannot issue/send | Manage | Submit; review others; post/link |
| Front desk | Assigned location | Read | Create/cancel orders; issue/send invoices | No credit queue, allocation or ledger access; can see invoice balances | Own submissions only |
| Staff | Assigned location | No | No | No | Own submissions only |

Only the owner manages locations/team membership. **Nobody may approve their own expense**, including the owner. Backend authorization must remain authoritative when navigation or identity is integrated.

## 3. Rules that must survive integration

1. Derive the actor from a verified server-side session/provider assertion. Do not accept a caller-supplied user ID as authentication.
2. Scope every record/query/download to its business and location. Revoked members must lose access. A receipt URL is not public authorization.
3. Store money as integer minor units and return decimal strings. This implementation supports NGN; do not mix currencies or add implicit FX conversion.
4. Keep order line prices/descriptions and issued invoice snapshots immutable. Catalogue edits must not rewrite historical amounts.
5. Treat an order/invoice as an obligation, not money received. Count canonical income once; allocations change receivables, not income totals.
6. Preserve source uniqueness. A repeated alert/source reference must recover the same credit, not create another transaction. Renaming the reference does not make the same payment new money.
7. Match the expected receiving account as well as evidence/reference. Names and amounts alone are not proof. Missing/ambiguous matches remain for review; suggestions never silently settle an invoice.
8. Never allocate more than a credit's remaining available amount, including simultaneous requests. Retain idempotency keys across uncertain save retries.
9. Reversals/cancellations/voids retain actor, reason and time. They do not transfer money, issue refunds, recall email or automatically notify customers.
10. Approval does not post an expense. Link an already recorded debit for the same purchase; only create another entry after checking duplication. Post actual expenditure, not an unpaid supplier obligation.
11. Preserve receipt versions and independent review. A stale revision cannot be approved; receipts, pending approvals and imported debits cannot be added together as separate spending for the same purchase.
12. Separate invoice status, payment status and email-delivery status. SMTP acceptance is not proof of recipient arrival; an uncertain attempt must not be blindly resent.

Example: a NGN 50,000 invoice with NGN 45,000 allocated has NGN 5,000 outstanding. Allocating the same credit again must fail/recover its original save, not create another NGN 45,000 income entry. The fractional-value browser example used a NGN 50,000.20 invoice and correctly left NGN 5,000.20 outstanding.

## 4. Architecture and file map

All paths in this document are repository-relative, so the handoff works on another computer.

| Files | Responsibility |
|---|---|
| `enterprise_preview.py` | Shared workspace API construction, preview database/authentication, sessions, business/location/membership/invitations and authorization dependencies |
| `enterprise_production.py`, `workspace_runtime.py` | Validated production entry point; HTTPS/PostgreSQL/SMTP configuration gates |
| `workspace_postgres.py` | PostgreSQL adapter for the workflow queries, private schema, SERIALIZABLE transactions and controlled conflict behavior |
| `workspace_email.py` | Verification token lifecycle; captured local inbox; shared TLS SMTP transport |
| `workspace_finances.py` | Canonical income/expense records, totals and void guards |
| `workspace_orders.py` | Location catalogue/profile, order creation, historical line items and cancellation |
| `workspace_invoices.py` | Issued invoice/PDF snapshots, downloads and deduplicated email attempts |
| `workspace_payments.py` | Receiving accounts, evidence, candidate review, allocations, reversals and balance calculations |
| `workspace_expenses.py` | Private receipt versions, independent review, posting/linking and category drill-down |
| `workspace_owner.py`, `src/WorkspaceOwner.jsx` | Owner-only consolidation and responsive overview |
| `workspace_receipt_reader.py`, `Dockerfile.receipt-ocr` | Offline receipt OCR/parsing; optional isolated Docker reader for local Windows preview |
| `workspace_suppliers.py`, `src/WorkspaceSuppliers.jsx` | Supplier invoice snapshots, liabilities and existing-debit payment allocation UI/API |
| `workspace_whatsapp.py`, `src/WorkspaceWhatsApp.jsx`, `scripts/process_whatsapp_inbox.py` | Sender identity, signed intake, durable private receipt queue/inbox, bounded media transport and separately supervised worker |
| `scripts/sql/enterprise/003_supplier_whatsapp.sql` | Five additive private intake/payables tables, restricted grants and retrieved-evidence immutability trigger |
| `scripts/sql/enterprise/002_receipt_extraction.sql` | Additive extraction/provenance tables and restricted grants, following unchanged migration 001 |
| `src/BusinessWorkspace.jsx`, `src/BusinessWorkspace.css` | Workspace shell, business switching and role navigation |
| `src/WorkspaceVerification.jsx`, `src/WorkspaceFinances.jsx` | Verification and location ledger UI |
| `src/WorkspaceOrders.jsx`, `src/WorkspaceInvoice.jsx` | Catalogue/order/invoice UI |
| `src/WorkspacePayments.jsx`, `src/WorkspaceExpenses.jsx` | Payment review and receipt/review/category UI |
| `src/services/workspaceService.js` | Same-origin workspace requests with the server session cookie |
| `src/App.jsx`, `src/Login.jsx`, `src/components/MobileNav.jsx`, `vite.config.js` | Route/build flags, local entry link, navigation and development API proxy |
| `enterprise_static.py` | Same-origin compiled frontend; unknown API/health paths stay 404 rather than returning SPA HTML |
| `scripts/sql/enterprise/001_enterprise.sql` | Initial private production schema and permissions; apply out of band as migration owner |
| `scripts/generate_enterprise_migration.py` | Reproducible schema generation from an empty database, never preview user data |
| `Dockerfile.enterprise`, `.dockerignore`, `enterprise.env.example` | Business-only runtime packaging, secret exclusions and required configuration names |
| `requirements-production.lock`, `requirements-production.txt`, `requirements-preview.txt`, `requirements-rehearsal.txt` | Linux release dependency lock, direct requirements, preview and rehearsal dependencies |
| `compose.enterprise-test.yml`, `scripts/create_enterprise_test_certs.py` | Disposable local TLS database and test certificates |
| `scripts/rehearse_enterprise_container.py`, `scripts/rehearse_enterprise_restore.py` | Loopback container smoke test and separate-database recovery verification |
| `.github/workflows/enterprise-release-rehearsal.yml` | Prepared automated release checks without production secrets |

### API surface

The root is `/enterprise-api`. Exact request models and status handling are in the listed Python modules; read those before writing an adapter.

- Authentication/configuration: `/config`, `/register`, `/login`, `/logout`, `/me`, `/email/request`, `/email/verify`, `/email/inbox` (capture mode only).
- Business/team: `/businesses`, `/businesses/{business}`, its `/locations`, `/invitations`, `/members/{member}` and `/invitations/accept`.
- Ledger: `/businesses/{business}/financial-records` and `/{record}/void`.
- Location base: `/businesses/{business}/locations/{location}`.
- Catalogue/orders under the location base: `/catalogue`, `/profile`, `/services`, `/services/{service}`, `/orders`, `/orders/{order}`, `/orders/{order}/cancel`.
- Invoice under `/orders/{order}/invoice`: read/issue, `/pdf`, `/email`, `/email/{delivery}/attachment`.
- Payments under the location base: `/payments`, `/payments/accounts`, `/payments/invoice-account`, `/payments/credits`, `/payments/allocations`, `/payments/allocations/{allocation}/reverse`.
- Expenses under the location base: `/expenses`, `/expenses/{expense}`, `/expenses/{expense}/review`, `/expenses/{expense}/post`, `/expenses/{expense}/receipt/{revision}`, `/expenses/categories/{category}`.
- Operational endpoints outside the API root: `/health/live` and `/health/ready`.

### Data ownership

The PostgreSQL schema contains 33 tables including migration tracking (26 from 001, two from 002 and five from 003):

- Identity/access: `users`, `sessions`, `businesses`, `locations`, `memberships`, `invitations`, `audit_events`, `login_attempts`.
- Verification: `email_verifications`, `mail_outbox`.
- Canonical money: `financial_records`.
- Catalogue/orders: `location_profiles`, `services`, `orders`, `order_lines`.
- Invoices: `invoices`, `invoice_deliveries`.
- Payments: `payment_accounts`, `payment_evidence`, `invoice_accounts`, `payment_allocations`.
- Expenses: `expense_submissions`, `expense_versions`, `expense_events`, `expense_creation_keys`.
- Extraction/provenance: `receipt_extractions`, `expense_extractions`.
- Supplier payables: `supplier_bills`, `supplier_payments`.
- WhatsApp intake: `whatsapp_challenges`, `whatsapp_senders`, `whatsapp_messages`.
- Release tracking: `schema_migrations`.

Receipts and original PDFs are private durable database bytes. The runtime does not depend on writable container disk. Backups, retention, encryption and connection capacity still need the actual provider's operating policy.

## 5. Decisions Samuel must make

### Identity and existing users

Choose between a deliberately separate verified business-account pilot and shared sign-in with the existing identity provider. If shared sign-in is required, implement a reviewed mapping/claim-validation path and preserve membership authorization. Account recovery/support must be agreed before inviting real users. Do not auto-grant business membership just because email strings match.

### Data and bank connections

Identify the canonical production transaction/account model and how existing personal/business data should coexist. The private migration intentionally does not rewrite public tables. Do not attach the old financial/Gmail APIs without business/location ownership checks and an explicit source-ID mapping.

The current bank-credit screen accepts manually entered evidence, labelled as local/test evidence. It is not a live or authenticated bank feed. For a real connector, ingest only into authorized receiving accounts, retain the original source ID, normalize dates/money, deduplicate in the canonical ledger, preserve evidence and validate whether references survive in actual bank narration. Keep ambiguous credits in review.

### Hosting and sender

Choose the staging database, server/container host, public domain/proxy and verified sender. The combined container is the tested starting point. If incorporating it into the existing website/backend instead, preserve the same-origin cookie/API arrangement, validate shared dependency versions and rerun all affected original-app tests. The business container does not start the old Gmail scheduler.

Real email configuration and a controlled mailbox are required for verification/invoice arrival tests. The simulation mocked SMTP. Invitation sharing is still manual; automatic invitation mail is a separate missing integration.

## 6. Merge and production integration order

1. **Review the published implementation.** The feature code, migration, lockfiles, tests and handoff are included in the published feature commit linked above. Review the complete branch diff and any later commits before opening a PR from `Mastermoh0/Loamy:mohammeds-branch` to the original repo. Inspect `git status --short` for new unpublished changes before adding further work. No PR has been opened by this publication.
2. **Refresh against upstream in an isolated review branch/worktree.** Review both sides of changes to `package.json`/lockfile, routing, sign-in entry points, mobile navigation, Vite configuration, framework requirements and CI. Do not overwrite upstream improvements wholesale.
3. **Choose identity and canonical-data integration.** Resolve the decisions above before wiring real memberships, transactions or Gmail connections into these screens. Keep the original personal flows working.
4. **Provision separate staging.** Create a migration owner and a strong-secret `loamy_enterprise_app` LOGIN role without admin privileges. The application must not use the owner or a browser/service-role key as a substitute.
5. **Review/apply the private migrations.** On a new schema apply `scripts/sql/enterprise/001_enterprise.sql`, then `002_receipt_extraction.sql` and `003_supplier_whatsapp.sql` as the migration owner. On a previously migrated database apply only missing forward migrations after backup/review. Runtime now requires `003_supplier_whatsapp`. An unexpected existing schema requires inspection, not a `DROP SCHEMA` shortcut. Keep it out of the Supabase Data API. Add forward migrations rather than editing applied history.
6. **Configure secrets and build.** Follow `enterprise.env.example` and `deploy/ENTERPRISE-RUNBOOK.md`. Use real provider certificate verification and SMTP. Enable `VITE_ENTERPRISE_ENABLED=true`; the separate candidate also uses `VITE_ENTERPRISE_ONLY=true`. Never deploy `npm run dev:workspace` or use captured verification in production.
7. **Run the complete checks in staging.** Repeat the automated suite and test real browser HTTPS/cookies, provider mail arrival, representative receipts, receiving-account/source ownership and cross-business isolation. A merge/build alone is not acceptance.
8. **Pilot and release.** Agree backup/recovery/monitoring, approve the same tested image digest and release a small pilot. Keep a schema-compatible prior image available. Application rollback must not delete financial history; agree a forward-fix/recovery procedure if the previous image is incompatible.
9. **Update this handoff.** Record the actual merged commit/PR, migration versions, staging results, remaining blockers and production release date only when verified.

**Never copy** `.local-data/`, `.venv/`, populated environment files, database passwords, local CA/private keys, sessions, captured emails, fictional credits/receipts or developer machine paths into production. The rehearsal reset helpers are restricted to a disposable named local database; they are not migration tools for Samuel's database.

## 7. Configuration contract

| Setting | Purpose |
|---|---|
| `LOAMY_WORKSPACE_WEB_ORIGIN` | Approved public HTTPS frontend origin and verification-link origin |
| `LOAMY_WORKSPACE_API_ORIGIN` | Approved public HTTPS API origin; use the same origin for the combined container |
| `LOAMY_WORKSPACE_DATABASE_URL` | Private PostgreSQL application-role URL with `sslmode=verify-full` and provider CA where required |
| `LOAMY_MAIL_TRANSPORT=smtp` | Mandatory production transport; capture is rejected |
| `LOAMY_SMTP_HOST`, `LOAMY_SMTP_PORT` | Sender service endpoint |
| `LOAMY_SMTP_SECURITY` | `starttls` or `ssl` |
| `LOAMY_SMTP_FROM`, `LOAMY_SMTP_USERNAME`, `LOAMY_SMTP_PASSWORD` | Sender identity and secrets, stored outside source control |
| `LOAMY_WORKSPACE_SERVE_DIST=1` | Serve the business frontend from the API container |
| `FORWARDED_ALLOW_IPS` | Exact trusted proxy IP/network; never blindly trust `*` |
| `VITE_ENTERPRISE_ENABLED=true` | Include the workspace in an opted-in production frontend build |
| `VITE_ENTERPRISE_ONLY=true` | Build the isolated business-only candidate, excluding personal-app routes |
| `LOAMY_LOCAL_PREVIEW=1` | Development only; explicitly rejected by the production entry point |

Use Node 22/Python 3.14 for the recorded rehearsal. The business dependency files are intentionally separate from the original backend's `requirements.txt`. If consolidating environments, resolve and test that integration rather than installing conflicting pins together.

## 8. Validation evidence and how to repeat it

Last recorded successful run: **7 November 2026**. This document records earlier executed checks; it does not claim they were rerun merely because the handoff was edited.

| Evidence | Recorded result | Important boundary |
|---|---|---|
| Business workflow regressions | 34 cases passed | Targeted new workspace paths, not every legacy subsystem |
| Production/rehearsal cases | 5 cases passed | Includes real PostgreSQL TLS/permissions/concurrent allocation and simulated SMTP |
| Combined suite | 39 cases passed | Counts test cases, not a guarantee of exhaustive coverage |
| Business-only build/targeted lint | Passed | Repository-wide legacy lint backlog remains |
| Candidate container | Non-root UID 10001, read-only filesystem, readiness/routes/configuration rejection passed | Loopback smoke test, not public deployment |
| Backup/restore | All 26 tables matched, including receipt/PDF bytes and financial rows | Disposable local databases; actual provider backups still need configuration |
| Production dependency audits | No known advisories reported after patches | Time-specific audit; rerun before release |
| Mobile tooling audit | Four moderate development-tool advisories remain documented | Original Capacitor/iOS asset-generation chain; not deployed in the business web runtime |
| Real provider email, public DNS/TLS, real bank/Gmail integration | Not verified | Requires Samuel's environment/access and representative data |
| GitHub Actions | Workflow prepared; remote execution not triggered/verified by this work | Branch pushed; no PR, upstream merge or release created. The release workflow runs on pull requests/manual dispatch, not this branch push alone. |

Local preview:

```text
npm ci
python -m venv .venv
# Activate that environment using your platform's normal command.
python -m pip install -r requirements-preview.txt
npm run dev:workspace
```

Open `http://127.0.0.1:5173/business`. This is local test data, not production.

Basic workflow checks, after installing the appropriate isolated dependencies:

```text
python -m unittest test_workspace_features test_workspace_orders test_workspace_invoices test_workspace_payments test_workspace_expenses test_workspace_owner test_workspace_receipts test_workspace_suppliers test_workspace_whatsapp -v
```

For the full release rehearsal, follow `PRODUCTION-READINESS.md` and `.github/workflows/enterprise-release-rehearsal.yml`: install `requirements-rehearsal.txt` and native OCR tools (or the explicitly configured local Docker reader), generate ignored random test credentials/certificates, start the disposable TLS PostgreSQL service, build the business-only frontend and set `LOAMY_RUN_POSTGRES_TESTS=1` and `LOAMY_RUN_OCR_TESTS=1` before:

```text
python -m unittest test_workspace_features test_workspace_orders test_workspace_invoices test_workspace_payments test_workspace_expenses test_workspace_owner test_workspace_receipts test_workspace_suppliers test_workspace_whatsapp test_enterprise_production -v
python scripts/rehearse_enterprise_restore.py
docker build -f Dockerfile.enterprise -t loamy-enterprise:rehearsal .
python scripts/rehearse_enterprise_container.py
npm audit --omit=dev
python -m pip_audit -r requirements-production.lock --no-deps --disable-pip
```

Without the PostgreSQL opt-in flag, production-database tests skip; a skipped test is not a passed production check. Local test CA material and simulated proxy headers are not substitutes for testing Samuel's actual public TLS/proxy configuration.

## 9. Remaining and future work

Do not mark these as implemented merely because related legacy code exists elsewhere in the repository:

- Real identity linking/account recovery as chosen by Samuel; existing-user/business/financial-data migration.
- Automatic invitation email and verified real provider delivery/monitoring.
- Authorized Gmail/bank ingestion into the scoped canonical ledger, with source uniqueness and real matching fixtures.
- Automatic settlement, real bank refunds/transfers and customer payment reminders.
- Live WhatsApp account/provider acceptance and group capture (disabled); broader receipt formats/languages, supplier credits/refunds and accrual-accounting integration.
- Source-backed AI insights, financial-history exports and historical receivables snapshots. The consolidated owner overview is implemented; these additional reporting capabilities are not.
- Service inventory/room availability, tax/discount rules, POS integration, QR linking and broader currency/bank support unless separately implemented later.
- Mobile release/tooling follow-up and full regression/security review of the original personal backend when integrated.

## 10. Instructions for the receiving AI agent

Suggested starting task for Samuel's agent:

> Read this handoff, `PRODUCTION-READINESS.md`, `deploy/ENTERPRISE-RUNBOOK.md` and the actual incoming diff. Verify that every referenced source/migration/test file is present. Separate implemented workflows from simulated services and owner-side release gates. Inspect the current production identity, canonical ledger, deployment and database before changing integration code. Reuse the delivered workflows; do not recreate a parallel ledger or trust browser-supplied identity. Propose/implement the smallest reviewed staging integration that preserves existing records and personal-app behavior. Run the checks, report actual results/skips, and update this handoff. Do not treat this document, a successful merge or old test results as permission/evidence to operate on live data.

## 11. Keeping this file current

The user has requested that completed, tested feature work be committed and pushed to `Mastermoh0/Loamy:mohammeds-branch`, with this handoff updated alongside it. Verify the destination and remote result each time. This is not authorization to merge into Samuel's main branch or deploy production.

## 12. Owner overview and offline receipt extraction — 7 November 2026

### Owner overview

`GET /enterprise-api/businesses/{business_id}/owner-dashboard` requires a verified owner membership. Managers, finance and staff are denied; outsiders and foreign locations are not exposed. Optional `location_id`, `start`, `end` filters select one/all locations and an inclusive date range, defaulting to the last 30 days in Lagos time; maximum 366 days, no future end date.

- Posted canonical ledger records determine money in/out/net. Voids are excluded. Order totals, allocations and approved-but-unposted receipts do not create additional cash movement.
- Orders use `order_date` in the period; cancelled orders are counted separately and excluded from open order value.
- Receivables use all currently issued invoices and active allocations backed by posted income, regardless of date filters. Outstanding and excess are clamped separately per invoice; overdue means due date strictly before today. This is a current position, not historical ageing at the selected end date.
- Receiving accounts show recorded credits within the dates, current allocations from those credits, and unallocated amounts. `bank_balance` is explicitly null and `bank_feed_connected` false. No opening balance/live feed is invented.
- Pending review/approved-unposted expenses are current queue counts. The response includes per-location rows, matching totals, source counts and generation time. It writes nothing and creates no reporting ledger.
- UI: owner-only **Owner overview**, location/date form, loading/error/empty states, per-location breakdown and explanations of scope. Returning to the tab or selecting Update overview refreshes it; no live-push subscription.

### Receipt extraction and provenance

`POST /enterprise-api/businesses/{business_id}/locations/{location_id}/expenses/extract` accepts `receipt_base64`, under the existing verified session/business/location scope. Any member can read their own selected receipt for their assigned location; owners can select any business location. It does not create an expense or financial record.

1. Validate JPEG/PNG/PDF bytes with the existing upload checks: 2 MB, image verification and 20 megapixels. A PDF must have no more than three pages for extraction.
2. Tesseract English reads images. Poppler extracts a text PDF directly; otherwise bounded-size page rendering is read by Tesseract. Fixed subprocess arguments, temporary private files, no shell interpolation and no cloud model/service. Receipt content is data, never executable instructions.
3. Conservative parsing suggests the first plausible vendor line, one unambiguous labelled total with two decimal places, and one ISO or day-first numeric date. Multiple totals/dates, unreadable/foreign-currency totals and future dates require manual entry. No item, VAT, exchange-rate, category or purpose inference is presented as fact. Every suggestion requires human confirmation.
4. The UI prefills editable fields and displays warnings/extracted text. Purpose/category remain manual. Replacing the selected file clears extraction provenance. The server binds any submitted `extraction_id` to the exact receipt hash, actor, business and location; forged/mismatched links fail. Submitted values can differ from suggestions and both remain visible in version history.
5. Existing independent review, immutable versions, clarification/resubmission, duplicate receipt checks and explicit posting/linking remain in force. Extraction never approves or posts money.

New migration **002_receipt_extraction** adds `receipt_extractions` (actor-scoped attempts, receipt SHA-256, timestamp, pending/success/failed state, engine and bounded JSON suggestions/warnings/text) and immutable `expense_extractions` links to exact expense revisions. The app role may insert/read links but not rewrite/delete them; extraction result/status updates are limited to the attempt lifecycle. Existing migration 001 is unchanged and remains reproducible. A same-user/location/hash successful read is reused; uncached attempts are capped at ten per user/hour and extraction concurrency is one per worker. Failed reads allow manual submission. Unlinked attempts contain private receipt text; Samuel must set a retention/cleanup policy before staging acceptance without deleting linked audit evidence. A process crash may leave a pending attempt; retry can create another attempt within the limit.

Production packaging: native OS tools in `Dockerfile.enterprise`. Local Windows preview may explicitly set `LOAMY_RECEIPT_OCR_DOCKER_IMAGE=loamy-receipt-ocr:local` after building `Dockerfile.receipt-ocr`. That fallback is allowed only with `LOAMY_LOCAL_PREVIEW=1`; its temporary reader container is non-root, read-only, network-disabled and resource-limited. Never mount a Docker socket into production. See the runbook for native setup and resource/patching gates.

### Validation and release limits

- Final complete backend run: **47 passed, no skips**, with PostgreSQL and real OCR both enabled. Actual OCR covered PNG, scanned PDF and text PDF, and rejected a four-page PDF. Dashboard checks included nonempty combined/per-location exact totals, cancellation, voids, reversals and current receivables outside the activity period. API workflow tests use deterministic OCR fixtures where noted; the real reader case and packaged reader check use the actual tools.
- PostgreSQL checks exercised both migrations, extraction metadata/immutable version linkage, independent approval/posting and dashboard queries/owner permissions. Backup/restore compared all **28 tables**, including receipt/PDF bytes, without changing the source database.
- Targeted frontend lint and business-only build passed. Browser testing showed NGN 12,500.50 income once; real receipt extraction suggested NGN 1,000.10, corrected to NGN 1,000.20 on submission, retained original suggestions and left the expense pending independent review. The owner overview showed one awaiting review and zero extra posted expense.
- Desktop 1280px and mobile 390px were inspected; dashboard and receipt screens had no horizontal document overflow. Evidence is local under `../output/loamy-study/owner-dashboard-*.png` and `receipt-extraction-*.png`; screenshots contain fictional test data only.
- Rebuilt production image passed non-root/read-only runtime, TLS database/readiness, compiled UI, Host/HTTP/config rejection and **actual packaged OCR** checks. The initial OCR packaging omission and transient package-download failure were corrected/retried before this passing rehearsal.
- Remaining release gates: Samuel's real staging identity/data mapping, migration backup/review, deployment configuration, representative receipt quality, retention policy, parser resource limits/OS patching and owner approval. No live deployment, bank feed, cloud OCR, automatic categorization, WhatsApp capture or automatic financial approval was performed.

### Continuing handoff maintenance

After a meaningful feature, migration or deployment change:

1. Update the date and repository/PR/commit/release status with verified identifiers.
2. Update the feature table, role boundaries, invariant rules and file/API map where behavior changed.
3. Move work from “remaining” to “implemented” only after code and appropriate validation exist. State clearly whether proof came from a local fixture, rehearsal, real staging or production.
4. Record exact checks/results/skips and update risks/owner dependencies. Do not carry forward old results as if newly executed.
5. Record new migration/configuration requirements and compatibility/rollback notes. Never rewrite an applied migration to hide history.
6. Exclude secrets, personal/customer data, raw bank emails, receipt images and credentials. Use anonymized examples and repository-relative paths.

The root `AGENTS.md` reinforces this maintenance requirement for future work in this repository. Supporting guides remain useful, but this file is the primary cross-team handoff and should remain understandable when shared on its own.

### Update history

| Date | Change | Validation represented |
|---|---|---|
| 7 November 2026 | Initial consolidated handoff: business/roles/verification, ledger, catalogue/orders, invoices/email, payment allocations, staff receipts/review/categories and production candidate | Documents prior 39-case release rehearsal, build/audits/container/restore results; no new runtime tests required for this documentation-only addition |
| 7 November 2026 | Published the complete implementation to the fork's `mohammeds-branch` in feature commit `3294da8`; added detailed feature/validation commit notes and ongoing publication instructions | Fresh pre-push run: 35 workflow/configuration cases, targeted frontend lint and business-only build passed. The PostgreSQL-specific rehearsal cases were not rerun for this publication; their prior results remain recorded above. Remote feature-commit SHA verified. |
| 7 November 2026 | Added consolidated owner overview and offline receipt extraction with version-bound suggestions; additive migration 002 and deployment/CI documentation | 47 backend tests passed with real OCR and PostgreSQL enabled; lint/build, real desktop/mobile workflow, 28-table restore and updated restricted production container/OCR rehearsal passed. Publication is represented by this feature/handoff commit in branch history. |
| 7 November 2026 | Added supplier invoice liabilities/payment allocations and WhatsApp private receipt intake/worker, simulation and sender linking; forward migration 003 and operator setup notes | 60 backend tests passed with no skips; real OCR, PostgreSQL concurrency/evidence/upgrade checks, 33-table restore and restricted container rehearsal passed. Actual WhatsApp transport remains mocked and requires owner-side acceptance. |

## 13. Supplier invoices and WhatsApp receipt intake — 7 November 2026

### Supplier bills: how they work

`workspace_suppliers.py` adds `/enterprise-api/businesses/{business_id}/locations/{location_id}/supplier-bills` under verified owner/manager/finance authorization; non-owners stay at their assigned location. Staff/front desk cannot view/import supplier liabilities or download their original invoices.

- **Import:** POST confirmed vendor, supplier reference, description/category, exact NGN amount, invoice date/due date, original JPEG/PNG/PDF (2 MB max), optional matching extraction ID and idempotency key. Issue date cannot be future; due date cannot precede it. Active supplier/reference keys are case-insensitive and active receipt SHA-256 is unique per business. Reusing a request key with changed content is rejected. Original bytes/details are immutable; corrections retain a reasoned void and a new import/key. After voiding, the same original file/reference can be re-imported with corrected fields while the old snapshot remains available. Active duplicate guards still apply.
- **OCR:** the UI reuses the existing location-scoped offline receipt reader. Vendor/total/date are editable suggestions, never proof of correctness or payment. Supplier reference, purpose/category and due date require human confirmation. Suggestions are bound to actor/business/location/exact file and remain visible beside the confirmed invoice.
- **Liability only:** importing an invoice creates no financial record or paid expense. GET returns exact current outstanding/overdue totals across all bills even though the displayed list is capped at 100. Overdue means an unpaid amount with due date before Lagos today. Owner overview now includes current combined/per-location supplier payables separately from customer receivables and recorded cash outflow.
- **Payment matching:** POST `/{bill_id}/payments` links an already posted expense debit from the same business/location. It supports partial/split payments but cannot exceed either unallocated debit funds or the bill balance; income, foreign-location debits and debits before the invoice date are rejected. A reviewed advance-payment model is not implemented. This allocation never creates another cash entry or initiates a bank transfer.
- **Corrections:** POST `/{bill_id}/payments/{payment_id}/reverse` retains the original association/reason and records the reversal. POST `/{bill_id}/void` retains invoice evidence but requires no active allocations. Existing financial-record voiding is also blocked while supplier allocations remain. Posting a staff receipt and importing its supplier bill do not automatically imply two different purchases; reconcile the existing canonical debit.
- **Not included:** supplier tax/credit notes, FX, automatic settlement, payment execution, full accrual/expense recognition, automatic supplier email imports or exports. This release imports a confirmed document through the workspace, with optional offline extraction.

### WhatsApp: how staff identity and evidence work

This implements inbound private-message receipt intake, with **live access disabled by default**. It adds no outbound acknowledgment/template messages and does not scrape WhatsApp Web. The guarded preview has an explicitly labelled local simulation that sends no WhatsApp traffic and does not verify a real phone. Production refuses the simulation endpoint.

1. An operator maps an approved provider phone-number ID to an existing Loamy business in `LOAMY_WHATSAPP_ROUTES`, with app-secret, handshake token, media-access token and an explicitly supported Graph version. These are server/worker secrets; browser users cannot reroute a number or supply arbitrary download URLs. See `enterprise.env.example` and the runbook's staged setup procedure.
2. Verified staff selects their location and requests a one-use link code. Only a hash is stored; code lasts ten minutes, replaces previous unused codes and is limited to ten requests per account/hour. They privately send `LINK <code>` to the operator-confirmed business WhatsApp number. A valid provider-signed message binds its numeric sender to that account/location. Display/contact names are not identity. Active sender ownership cannot be taken by another account; unlinking or membership removal blocks new intake. Tokens are never sent to a WhatsApp recipient by this codebase.
3. `/enterprise-api/integrations/whatsapp/webhook` handles the GET verification challenge and HMAC-SHA256 signed raw POST body. It alone is exempt from browser Origin, while Host, HTTPS and bounded body checks remain. Unknown numbers, unlinked/stale senders, unsupported message types and explicit group contexts are ignored. Supported images/documents carry immutable provider message ID, sender/account/location, timestamp, caption, media ID and expected SHA-256. Duplicate deliveries do not enqueue twice. Thirty receipts per staff/hour is the intake limit; a 429 rolls the batch back for provider retry rather than silently acknowledging a dropped receipt.
4. Webhook acknowledgment follows durable queue commit. Run `python scripts/process_whatsapp_inbox.py` as a separately supervised worker with the same image/config/database; `--once` is available for scheduling. It claims one item with a 180-second recoverable lease, checks current membership/link, fetches media metadata from fixed Graph API and downloads only HTTPS `lookaside.fbsbx.com` without redirects. It checks streamed size (2 MB), actual JPEG/PNG/PDF bytes and expected media hash, with bounded timeouts. Media failures are visible for explicit retry; attempts max out at five. Current authorization is checked again before saving. No provider data/credentials were used during development tests; transport was mocked.
5. The staff member's private inbox shows queued/ready/failed/submitted/discarded receipts. They can retry a failed retrieval, download the original, dismiss unsubmitted evidence with retained history, or open an editable expense draft. OCR is optional; original file, sender metadata and caption stay attached. Server submission verifies actor/business/location/hash and consumes the ready message atomically. A different staff member cannot claim it. Submitting follows the existing independent reviewer and explicit post/link workflow; it never auto-approves or posts money.
6. Submitted expenses expose their evidence source to authorized reviewers. Inbox receipt contents remain private to their submitter. Captions/extracted text are untrusted plain text; no instructions in them are executed. A PostgreSQL trigger prevents rewriting already retrieved receipt bytes/hash/type; the app role cannot rewrite provider identity/message fields or supplier invoice amounts. Financial history and evidence are not deleted to correct errors.

**Provider acceptance gate:** actual sender identifiers, supported media hosts, permissions, subscriptions and payloads must be tested with Samuel's Meta account. Group support is disabled/unverified, including existing staff groups. Native Meta docs returned access/rate-limit errors during research; primary references consulted were [WhatsApp's receiving-message guide](https://github.com/WhatsApp/WhatsApp-Nodejs-SDK/blob/main/website/docs/receivingMessages.md) and [Meta's official Postman collection](https://www.postman.com/meta/whatsapp-business-platform/collection/wlk6lh4/whatsapp-cloud-api). Their examples are not evidence of current group eligibility or a live integration. Record representative sanitized private-message fixtures before enabling production intake; do not relax signature, sender, tenant or URL checks to accommodate an unverified format.

### Migration, operation and validation

- Apply additive **003_supplier_whatsapp** after 002. Prior 001/002 artifacts remain unchanged. Runtime now requires 003; do not start the new image before its migration is reviewed/applied. Five new tables bring the private schema to **33**. The schema generator reproduces both 001 and 003 from empty schemas; it never migrates user data automatically.
- Agree retention for unsubmitted WhatsApp files/captions/identifiers, failed jobs and expired challenges while retaining linked evidence and financial history. The worker must be supervised separately and monitored for queue age/failures; no cron/hosting provider or live WhatsApp setup has been provisioned. Restart on serialization/process failure; leases recover incomplete claims. User-visible manual upload remains available.
- **60 backend tests passed, no skips**, with real OCR and isolated TLS PostgreSQL enabled. New tests cover exact supplier liabilities/no extra cash, duplicate imports, partial/split payments/reversals, roles/locations, invalid amounts/dates, signed sender linking, replay/unsupported/group rejection, private drafts, revocation, failed retrieval/retry/discard, evidence mismatch and credential-safe media downloads. PostgreSQL tests include concurrent supplier allocations, retained pre-migration data and evidence immutability. Provider transport is simulated; actual offline OCR still uses real tools.
- Backup/restore compared all **33 tables** including private bytes and financial rows; source unchanged. Rebuilt non-root/read-only production image passed TLS database, readiness/frontend, Host/HTTP/config rejection and actual packaged OCR checks. Targeted UI lint/build passed; the UI detector reported no findings. Browser imported a fictional NGN 1,000.10 invoice, matched its existing NGN 450.05 expense debit and showed NGN 550.05 owed without another cash entry. The simulated WhatsApp inbox preserved receipt/caption through OCR and expense submission, stayed explicitly labelled as simulated and required a different reviewer. Both screens were inspected at desktop/mobile widths with no horizontal document overflow; local evidence lives under `../output/loamy-study/supplier-bills-*.png` and `whatsapp-inbox-*.png`. The preview was restarted after final backend changes with fictional evidence retained.
- No real WhatsApp connection/message, bank transfer, live customer data, production migration/deployment or upstream merge was performed. Samuel's staging/provider setup, retention, worker operations and owner acceptance remain release gates.

## 14. Release acceptance record — fill only after verification

- Implementation commit: **Published and verified: `3294da82ab452052969ff4a9ba32f7ea6225d469`**; inspect subsequent branch history for documentation/future updates.
- Incoming upstream PR: **Not opened**.
- Identity/account-recovery decision: **Pending Samuel**.
- Staging host/database and applied migration version: **Pending**.
- Real verification/invoice mailbox checks: **Pending**.
- Real bank/Gmail source/account validation: **Pending if enabling that integration**.
- Role/isolation/financial/receipt staging acceptance: **Pending**.
- Backup/restore, retention, monitoring and rollback sign-off: **Pending**.
- Approved image digest and owner approval: **Pending**.
- Production deployment/date and pilot result: **Not performed**.
