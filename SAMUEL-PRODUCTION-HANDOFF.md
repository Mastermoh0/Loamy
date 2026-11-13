# Samuel's production handoff: Loamy business features

> **Living handoff for Samuel, his team and his AI agents.** Update this file after each meaningful feature or integration change. It is an implementation map and release checklist, not evidence that a live deployment has happened.

Last updated: **13 November 2026, Africa/Lagos**.

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

The recorded test cases and release rehearsal validate the stated paths. They are not a certification of the original application's entire security, mobile builds or unknown production configuration. See section 16 for taxes/discounts and QR navigation, and section 14 for customer-message, insight and export changes; earlier counts are historical.

## 2. What is implemented

“Implemented” below means working code exists and has the recorded local/rehearsal validation. It does not mean enabled on Samuel's live website.

| Feature | Behavior delivered | Production integration still required |
|---|---|---|
| Business and locations | Create a business, first/additional locations, business switching and scoped membership | Decide how existing businesses/locations are mapped without exposing or duplicating records |
| Team permissions | Owner, manager, finance, front desk and staff; one assigned location for non-owners; expiring one-use invitations; revocation and audit history | Decide identity/account linking; invitation links are generated but not automatically emailed |
| Email verification | Expiring one-use links, resend cooldown, matching signed-in recipient, session rotation | Configure real sender and test arrival; local capture is not mailbox-ownership proof |
| Location financial records | Exact NGN income/expenses, scoped totals, retry protection and reasoned voids preserving history | Connect existing canonical transactions/imports; do not sum independent copies of the same money |
| Service catalogue | Per-location service names, descriptions, prices and availability; editable order/invoice business details | Confirm pilot services, exclusive-tax rates and discount policy; inventory/room availability remain separate |
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
| Customer notices | Reviewed partial-payment updates and overdue email drafts, current-balance recheck, capture/SMTP delivery history and uncertainty/duplicate guards | Real staging mail acceptance and recipient/policy checks; no automatic reminder scheduler or unreviewed sends |
| Customer invoice links | Expiring/revocable bearer link, customer invoice/PDF view and current balance, native share/copy handoff | Approve bearer-link privacy and public HTTPS hosting; no automatic WhatsApp/SMS delivery |
| Financial insights | Owner cash-burn/runway scenario, invoice-level debtors, evidence-backed recurring candidates and tracked subscriptions | Confirm data completeness/cash input and operating assumptions; no live bank balance or automatic external cancellation |
| Financial history exports | Scoped ZIP with CSV summary/ledger/current balances/allocations/evidence references, manifest/checksums and optional originals | Accept report scope/retention, client download limits and spreadsheet handling in staging |
| Taxes and discounts | Per-location exclusive tax, order-level fixed/percentage discount, immutable breakdown in orders/invoices/PDFs/exports and adjusted balances | Approve actual rates and discount policy; no filing/remittance or inclusive/per-item tax engine |
| Location QR links | Downloadable locally generated QR, business/location navigation after sign-in, existing membership checks | HTTPS hosting and phone/printed-code acceptance; QR grants no access or public customer ordering |
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
| `workspace_notifications.py`, `src/WorkspaceNotifications.jsx`, `src/WorkspaceInvoiceShare.jsx`, `src/CustomerInvoice.jsx` | Reviewed transactional notices and revocable customer-facing invoice links |
| `workspace_reports.py`, `src/WorkspaceReports.jsx`, `src/services/workspaceDownloads.js` | Cash scenarios, debtors/recurrence/subscription tracking, bounded report/evidence downloads |
| `scripts/sql/enterprise/004_reports_notifications.sql` | Additive notice/share/recurring-commitment tables and restricted update grants |
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

The PostgreSQL schema contains 36 tables including migration tracking (26 from 001, two from 002, five from 003 and three from 004):

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
- Reporting/communication: `customer_notices`, `invoice_shares`, `recurring_commitments`.
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
5. **Review/apply the private migrations.** On a new schema apply `scripts/sql/enterprise/001_enterprise.sql`, then `002_receipt_extraction.sql`, `003_supplier_whatsapp.sql` and `004_reports_notifications.sql` as the migration owner. On a previously migrated database apply only missing forward migrations after backup/review. Runtime now requires `004_reports_notifications`. An unexpected existing schema requires inspection, not a `DROP SCHEMA` shortcut. Keep it out of the Supabase Data API. Add forward migrations rather than editing applied history.
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
python -m unittest test_workspace_features test_workspace_orders test_workspace_invoices test_workspace_payments test_workspace_expenses test_workspace_owner test_workspace_receipts test_workspace_suppliers test_workspace_whatsapp test_workspace_notifications test_workspace_reports -v
```

For the full release rehearsal, follow `PRODUCTION-READINESS.md` and `.github/workflows/enterprise-release-rehearsal.yml`: install `requirements-rehearsal.txt` and native OCR tools (or the explicitly configured local Docker reader), generate ignored random test credentials/certificates, start the disposable TLS PostgreSQL service, build the business-only frontend and set `LOAMY_RUN_POSTGRES_TESTS=1` and `LOAMY_RUN_OCR_TESTS=1` before:

```text
python -m unittest test_workspace_features test_workspace_orders test_workspace_invoices test_workspace_payments test_workspace_expenses test_workspace_owner test_workspace_receipts test_workspace_suppliers test_workspace_whatsapp test_workspace_notifications test_workspace_reports test_enterprise_production -v
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
- Automatic settlement, real bank refunds/transfers and unattended reminder campaigns.
- Live WhatsApp account/provider acceptance and group capture (disabled); broader receipt formats/languages, supplier credits/refunds and accrual-accounting integration.
- Generative AI advice, automatic reminder scheduling, direct outbound WhatsApp/SMS and historical period-end receivables snapshots. Deterministic recorded insights, reviewed email notices, customer invoice links and financial-history exports are now implemented.
- Service inventory/room availability, POS integration and broader currency/bank support. Basic exclusive taxes, order discounts and authenticated location QR navigation are implemented in section 16.
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
| 8 November 2026 | Added reviewed customer notices, expiring invoice links/customer page, recorded owner insights/subscription tracking and scoped financial-history/evidence ZIP exports; forward migration 004 | 76 backend tests passed with real OCR/PostgreSQL; 36-table recovery, restricted image rehearsal, lint/build and desktop/mobile browser flows passed. SMTP was mocked/captured; no customer messages or live deployment. |

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

## 14. Customer notices, insights and history exports — 8 November 2026

### Customer notices and additional invoice delivery

`Customer messages` is scoped to verified owner/manager/finance membership; non-owners remain at their assigned location. GET `/businesses/{business_id}/locations/{location_id}/customer-notifications` lists current partial-payment/overdue candidates and the latest 100 private drafts/delivery attempts (5,000 issued-invoice view limit). Partial updates require a positive remaining balance and a partial allocation; overdue requires a due date before Lagos today. Fully paid, overpaid and cancelled invoices are ineligible. This release is **review-and-confirm**, not a background scheduler or automatic message on every allocation.

POST prepares an immutable subject/body with exact invoice total, allocated and remaining amounts, due date, payment instructions and timestamp. Recipient validation reuses the single-email validator. Draft creation sends nothing. Request keys and per-day/kind/recipient/balance deduplication recover retries. The explicit `/{notice_id}/send` action rechecks current eligibility and an allocation fingerprint; changed balances require a fresh draft. Notice emails are capped at one per invoice/24 hours, with 30 new drafts per actor/hour. A definitely failed send needs explicit retry and a one-minute wait. Accepted, sending, captured or uncertain attempts are never blindly repeated. Local capture sends no email; production SMTP acceptance does not establish inbox arrival.

An SMTP attempt reserves `sending` in a committed transaction before network work. Invoice allocation/reversal and cancellation APIs refuse conflicting changes during its 120-second send window. Interrupted/stale sends become `unknown` when history is refreshed; investigate before any later new notice. Exactly-once delivery cannot be guaranteed across a process/network interruption. Review recipients and real payment evidence in staging. No real customer email was sent during this implementation.

Owners/managers/front desk can create invoice share links from the existing order/invoice panel. `/invoices/{invoice_id}/shares` returns a new random 256-bit token once; only its SHA-256 is stored. Links expire after 1–30 days and can be revoked. The URL uses `/customer-invoice#token=...`; the token stays out of ordinary HTTP URL/query logs and is posted in the request body. The customer view exposes only that invoice's issued details/PDF and current payment totals; no internal allocation notes, staff IDs, other invoices, receipts or workspace access. Invalid/expired/revoked tokens fail, and cancelled invoices refuse access/PDF download. The static customer page bypasses legacy personal-app activity syncing/navigation and uses the configured same-origin API.

**Bearer-link privacy:** anyone with the complete link can view the invoice's customer details and recorded balance without a customer login. Staff must share privately and get the recipient right. Revocation cannot recall files/screenshots already downloaded. App/server origins remain validated; public token POSTs retain the approved Origin/Host/HTTPS checks. Tokens are never returned in link history, and production access logging remains disabled; ensure proxy/error/analytics logs do not record tokens/bodies. Native device sharing or copying hands the link to the operator's chosen channel; it does not prove delivery or implement direct outbound WhatsApp/SMS.

### Recorded financial insights and subscriptions

`POST /businesses/{business_id}/financial-insights` is owner-only and supports one/all owned locations with 30–366 completed calendar days, ending yesterday in Lagos time. It uses posted canonical ledger movements only; voids, open orders, allocations and unpaid supplier invoices do not become extra cash entries.

- Net burn is `max(recorded expenses - recorded income, 0)` over the full selected day count. A runway scenario requires a nonnegative owner-entered available-cash amount plus explicit confirmation that history is complete. Positive burn yields `floor(entered cash minor units × days / net burn minor units)`. Without those inputs or positive net burn it is unavailable, not an invented bank balance or infinite runway. Zero entered cash yields zero days when burn is positive. The scenario is not persisted as a financial record.
- Current debtors are issued invoice-level outstanding balances across all dates, with contact/due/overdue information. Contacts/names are not automatically merged into a customer identity. These are current allocations, not historical ageing at a selected end date.
- Possible recurring expenses require matching location, normalized description/category and exact amount on at least three distinct dates. Gaps of 5–9 days suggest weekly; 25–35 suggest monthly. The UI shows dates and record IDs for review. These are unconfirmed patterns, not AI assertions or guaranteed subscriptions; changing amounts/descriptions and sparse history can prevent detection.
- Owner-confirmed `recurring_commitments` track vendor, description, location, exact NGN amount, weekly/monthly/quarterly/yearly cadence and manually maintained next-due date. Creation is idempotent; an active matching vendor/description is rejected. Corrections retain cancellation history and add a replacement. Approximate monthly cost uses weekly ×52/12, monthly ×1, quarterly ÷3, yearly ÷12, rounding the total to cents. Tracking never posts expenses, adds costs again to historical burn, advances dates automatically or cancels an external supplier subscription.

The UI explicitly labels the recorded-data/transfer/completeness limits. Owner-entered cash is not verified by a live bank feed. No generative model, investment advice, subscription billing API or live liquidity certification was added.

### Downloadable financial history and original evidence

`POST /businesses/{business_id}/financial-history/export` requires verified owner/manager/finance membership. Owners can choose one/all locations; non-owners are forced to their assigned location and cannot request another. Validate inclusive start/end dates (up to 366 days, no future end). ZIP downloads contain `summary.csv`, `ledger.csv`, current invoice balances, customer/supplier allocation histories, expense-version references, supplier-bill references, `README.txt` and a JSON manifest with coverage/totals/file SHA-256 checksums.

Ledger rows use `occurred_on` in the selected range, retain voids/corrections and sum only posted entries in the summary. Current invoice balances include scoped invoices across all dates and are explicitly labelled current, not historical period-end receivables. Cancelled invoice amounts owed are zero in this report. Allocation/reference IDs join the report back to canonical records. Optional original files include invoices issued/allocated in the range, supplier invoices issued or paid through period debits, and all immutable receipt versions linked to period ledger records. Original files keep their issued form: consult CSV status before relying on a cancelled/voided document. Evidence versions are not extra cash movement.

Unposted staff receipts, unrelated WhatsApp inbox contents, bank emails, credentials, sessions and identity tables are excluded. Bounds are 5,000 ledger records, 5,000 scoped invoice balances, 20,000 supporting metadata rows, 1,000 files and 25 MiB of originals, with one export per worker at a time. Oversized requests fail clearly instead of silently truncating; use fewer dates/one location or exclude original files. A private database transaction keeps metadata/files/totals consistent and audits the export without storing another report/ledger copy. Binary ZIP responses and API responses are non-cached. Files use generated IDs rather than customer filenames, unsafe archive paths are refused, and evidence lengths are checked before loading original bytes.

CSV cells are quoted; formula-leading ASCII/full-width markers are prefixed for spreadsheet viewing and leading controls are escaped. See [OWASP CSV Injection](https://community.owasp.org/attacks/CSV_Injection): protection depends on spreadsheet/re-save behavior; preserve the guards and don't treat an edited CSV as authoritative ledger evidence. No claim of universally safe spreadsheet re-import or digitally notarized reports is made.

### Integration, validation and release gates

Apply forward migration **004_reports_notifications** after 003. Prior artifacts remain unchanged. It adds three private tables with immutable notice bodies/recipients, hashed share tokens and recurring amounts; the runtime role can update only delivery state, share revocation and tracked-cancellation state. The schema now has **36 tables**. Deploy the reviewed matching image only after migration acceptance; do not drop or overwrite Samuel's existing database. No new cloud provider/dependency is required beyond the existing SMTP service; use an HTTPS web/API origin that serves the customer page too.

**76 backend tests passed, no skips**, with real OCR and isolated TLS PostgreSQL enabled. New checks covered exact runway inputs/math, recurring evidence/commitment history, current debtors, scoped exports/totals/original checksums, cancelled invoices/old supplier evidence, CSV markers/controls, report size/busy limits, draft deduplication/changed balances/overdue rules, send locks/retry/uncertainty, expiring/revoked shares, public PDF and exclusion of private fields. Mocked production SMTP exercised accepted and uncertain delivery and a concurrent allocation attempt during sending. Backup/restore matched all 36 tables including bytes and financial rows; the rebuilt restricted production image passed readiness/frontend/TLS/Host/HTTP/config/worker/OCR checks. Frontend lint/build passed; the UI detector found no issues. The browser exported a fictional date-range report, created a NGN 250.10 monthly tracked commitment without posting cash, and captured a reviewed partial-payment message for NGN 1,000.10 allocated/NGN 2,000.20 remaining without sending email. The customer link refreshed to the same balance. Desktop and 390px mobile views were inspected; mobile document widths showed no horizontal overflow. Local screenshots include `customer-invoice-desktop.png`, `customer-notifications-desktop.png`, `customer-notifications-mobile.png` and `financial-reports-mobile.png` under `../output/loamy-study/`. The initial download-event test timed out/reset the browser tool before an export request; after restoring the test session, the export action completed and showed its download confirmation. Backend tests independently opened the ZIP and verified original bytes/checksums and totals. No physical mobile device, native share destination or live mail recipient was tested.

Remaining gates: real HTTPS/customer-link/recipient testing, actual SMTP arrival/uncertain-delivery operations, explicit approval of bearer-link privacy, ledger completeness/transfer classification, cash inputs, export/client limits, retention and owner release acceptance. No automatic reminder campaign, live bank access, external subscription cancellation, real customer message, upstream merge or production deployment was performed.

## 15. Release acceptance record — fill only after verification

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


## 16. Taxes, discounts and location QR links — 9 November 2026

### Pricing rules and use

Owners/managers configure the location's tax name (2–60 characters) and rate (0–100%, up to two decimals) in **Services & orders → Service catalogue → Edit tax settings**. Default zero assumes no statutory rate. Service prices are tax-exclusive. Setting changes are audited and affect new orders only; Samuel must approve actual rates/treatment before staging acceptance.

Owners/managers can apply one fixed NGN or percentage discount, with a required reason shown to the customer. Front desk can create taxed orders but cannot discount or edit tax settings. Finance/staff cannot create orders or edit pricing. Non-owners remain confined to their assigned location.

Calculation: sum exact line amounts; round percentage discount half-up to a kobo (fixed discounts are exact); subtract discount; calculate exclusive tax on that remainder, round half-up to a kobo; add tax. A discount must leave a positive taxable amount. Example: NGN 3,000.30 − NGN 300.03 (10%) + NGN 202.52 (7.50%) = **NGN 2,902.79**. The example rate is fictional. Browser adjustment arithmetic uses integers/BigInt; the server is authoritative. NaN/infinity, excess precision, negatives, total-erasing discounts and stale/missing tax expectations with nonzero tax are rejected.

`orders.total_minor` is the adjusted total; immutable `order_pricing` retains original subtotal, discount type/value/reason and tax name/rate/amount. Invoice issuance uses that saved breakdown even if location settings changed after order save. Existing issued snapshots/PDFs remain unchanged. Older orders without pricing rows retain their existing amount with zero adjustments; old retry hashes are preserved for the original input fields. Corrections use existing cancellation/allocation reversal guards and a replacement order, never edit-in-place financial history.

Order/invoice/customer views and generated/cancelled PDFs display the breakdown. Balances, notices, debtors and owner order totals use the adjusted order total. Current-invoice-balances CSV adds subtotal, discount type/value/reason/amount and tax name/rate/amount from the issued snapshot; legacy snapshots get an explicit zero-adjustment fallback. Pricing/order/invoice actions create no extra ledger entry. No tax returns/remittance, tax-inclusive pricing, per-line exemptions/multiple taxes, stacked coupons, free invoices, credit notes, retroactive discounts or profit/accrual accounting are included.

### QR navigation and authorization

Verified members open **Locations → Show location QR** to display/download a black-on-white SVG and select/copy the URL. Generation uses pinned `qrcode==8.2` locally; no external QR service receives it. Usage reference: https://pypi.org/project/qrcode/ (SVG path factory, white background, standard four-module quiet zone).

The encoded URL is `{approved web origin}/business?business={id}&location={id}`. IDs are navigation hints, never authorization; there are no credentials, invitations or customer invoice capabilities in it. Production uses configured HTTPS origin. Preview uses loopback with an explicit warning that a phone cannot open this computer through its own loopback address.

The link selects an accessible business and displays its authorized location/address, with an action to open location orders (or assigned staff expenses). Same-URL sign-in preserves context. Local verification links also preserve it; if a real verification email opens a separate URL/device, finish verification and reopen the QR. Foreign/unavailable links show recovery guidance; every subsequent API independently checks membership/location. Revocation immediately blocks APIs without needing QR-token revocation. This does not assign membership, accept an invitation, prove physical presence, expose a public catalogue or enable customer self-service. Existing customer invoice links remain separate.

### Source and migration

Sources: `workspace_pricing.py`, `workspace_location_links.py`, order/invoice/report modules and shared factory; `WorkspacePricing.jsx`, `WorkspaceLocationLink.jsx` and existing order/invoice/customer/workspace/verification components with scoped CSS. `qrcode==8.2` is pinned in preview requirements/production lock; its Windows-only `colorama==0.4.6` dependency is platform-locked. No npm dependency was added. CI includes new tests/components.

After backup/review, apply **`scripts/sql/enterprise/005_pricing.sql` after 004**, as migration owner. Existing installations apply only missing forward migrations. It adds `location_pricing` and immutable `order_pricing`, bringing the private schema to **38 tables**. Runtime requires `005_pricing`. The runtime can insert/read pricing snapshots but cannot update/delete them; only location tax fields are updatable. No existing amounts/evidence or prior applied migration are rewritten. QR needs no new table. The generator explicitly excludes pricing tables from 001; 005 is a separately reviewed handwritten forward migration. Restore tooling checks 005.

### Actual validation and remaining gates

- **81 tests passed, no skips**, in 113.069 seconds with temporary SQLite, TLS-verified disposable PostgreSQL and real offline OCR. Lint, business-only build and `pip check` passed. Tests cover exact rounding/fixed/percentage amounts, invalid/stale inputs, roles/location restrictions, legacy retry/order compatibility, immutable invoice/PDF, adjusted partial balances/export columns, QR payload/SVG/origin and anonymous/foreign/revoked access, plus PostgreSQL migration/runtime privileges. Backup/restore compared all **38 tables**, including receipt/PDF bytes and financial rows, with the source unchanged.
- Browser: a fictional owner configured a fictional 7.50% tax, saved a 10%-discounted NGN 3,000.30 order and generated the matching NGN 2,902.79 invoice/outstanding amount. QR opened the correct authorized location and its order workflow. Desktop and 390px invoice/QR layouts were inspected; mobile width equalled scroll width (no horizontal overflow). Screenshots are local QA outputs, not production data. No real message, customer sharing, bank connection, live deployment or upstream merge occurred. Physical phone scanning/printing is untested.
- The UI detector reported one pre-existing unrelated 3px receipt-warning border; new pricing/QR styles did not introduce it. The first full run's existing OCR test lacked the guarded fallback's `LOAMY_LOCAL_PREVIEW=1`; after correcting that environment, the isolated OCR check and complete 81-case rerun passed. No reader code was loosened.
- **Clean container build remains a release gate:** Debian package downloads failed/stalled on this machine across normal, host-network and HTTPS/timeout attempts. Those attempts were stopped; the production Dockerfile was left unchanged. To exercise the actual updated code, built a clearly local offline overlay from the previously verified runtime (`loamy-enterprise:before-pricing`), copying only current application modules, compiled frontend, worker and the installed pinned pure-Python QR package/metadata. No databases, environment files or credentials were copied. This local overlay is not a clean production build or a deployable release approval. CI/staging must complete the normal `Dockerfile.enterprise` build with a functioning package service. The restricted-container smoke outcome is recorded below.
- Release gates: Samuel must approve actual exclusive-tax rates, discount permissions and customer-visible reasons; apply only missing forward migrations in staging; reconcile legacy/new invoices, partial payments and exports; test real phones/printed QR codes and sign-in/revocation on the HTTPS host; complete recovery/release approval. A simulated test is not a live tax-compliance or production-readiness certification.

- **Offline overlay result:** restricted-container rehearsal passed (non-root/read-only filesystem, verified TLS database, frontend/health, fail-closed settings, worker refusal when unconfigured and packaged offline OCR). Linux QR dependency/version/SVG generation and exact adjustment arithmetic passed separately. This confirms the updated runtime on the cached base; it does not replace the pending clean production build.

## 17. Customer workflows and owner evidence — 12 November 2026

### Separate browser acceptance pass — 12 November 2026

`docs/BROWSER-QA-2026-11-12.md` records UI-only checks against app commit `01d606d`: initially 13 Pass, 1 Fail, 2 Blocked and 4 Not run; after continuation, **14 Pass, 1 Fail and 5 Blocked** across T59–T78. These are Codex browser observations, separate from the user's unchanged results and earlier automated tests. Fictional records and actual UI uploads/downloads were used; no direct API/database setup, live provider or production access. The exact 70-day collection scenario and positive/negative branch answers passed in an isolated second location. Per-location PDFs separated records correctly. Empty-period date entry remains unresolved, not a confirmed product defect. The reconciled original PDF/ZIP predates T65 and the second location.

**Approved role continuation:** after the automatic review stopped a Finance invitation, the user explicitly approved the four named local-only accounts and roles. All four joined through normal UI registration/local verification/invitations. Current browser result: **17 Pass, 1 Fail, 2 Blocked**. Front desk saw the correct 1,000.10 partial alert and captured an original invoice, with no reminder-management/ledger controls. Finance managed a plan without original-invoice send controls. Staff private invoice and Front desk other-location PDF navigation were refused. Manager had no owner dashboard/review PDF/chat UI. These are manual UI checks, not a replacement for forged-request or production security testing. No real email was sent; Owner sign-in was restored.

Manager independently requested clarification for a fictional receipt/submission amount mismatch; Owner corrected version 2, Finance approved/posted 1,000.10 once, and Owner drilled through to the unchanged receipt bytes. T70 passed. T64 still needs an actual next-day send; the replacement email plan on Fictional Channel Guest waits until **13 November 2026 14:56:23 Lagos**, interval 1 day/max 2, balance 1,000.10. T72's scoped PDFs and Manager UI denial passed, but its empty-period date entry remains unresolved and therefore Blocked. The cancelled-balance display issue T69 remains open. Local fixture mutations and evidence timing are listed in the report; saved earlier PDF balances are not final-state balances.

**Open issue T69:** a cancelled invoice still displays a nonzero Remaining/Outstanding amount in owner detail, invoice detail and Payments & balances. The PDF correctly says do not pay; reminder stop checks and aggregate debtor/report exclusion passed. Correct this display/semantics consistently before release, preserving original amounts/history. It is recorded, not fixed, in this testing-only pass. The exact runway fixture, independent receipt workflow and stated UI role checks are now completed; next-day T64 and the empty-period part of T72 remain incomplete. See the report for precise coverage and limits.

### Implemented scope and deliberate boundaries

- New orders save separate primary email, up to three alternative emails, international WhatsApp number, preferred channel and an explicit permission record. Email alternatives are individual destinations, never silent CCs. Legacy contacts/retries and issued invoice snapshots remain compatible. Contacts remain immutable; WhatsApp permission can be withdrawn. New channel controls sit beside the existing email workflow.
- Invoice delivery supports saved email or WhatsApp destinations, explicit confirmation, attached original PDF, idempotency, a sending reservation, per-invoice cooldown and actor rate limits. Local preview captures only. Production WhatsApp uses Meta media upload plus approved templates, never a browser share-link masquerading as delivery. Provider acceptance is distinct from arrival; signed callbacks can record delivered/read/failed status. A callback arriving before the provider identifier is persisted may leave an accepted status pending review; staging must verify receipt reconciliation. There is no automatic channel fallback.
- Explicit reminder plans check current outstanding amounts and due dates. Paid/cancelled invoices, withdrawn WhatsApp permission and revoked staff access stop sending. Failures/uncertain sends pause for human review. A stale running claim pauses rather than blindly retrying a potentially delivered message. Plans cannot be reactivated by a concurrent cancellation/withdrawal. In-flight payment edits are briefly guarded while delivery is reserved. Front desk sees scoped partial/overdue alerts refreshed every 30 seconds. This is an in-app alert, not an OS push notification.
- Owner overview drills into selected-location orders/invoices and posted expenses with authorized original invoice/receipt downloads. Detail lists disclose truncation after 250 rows. Existing dates scope activity; receivables remain current. No live bank connection or bank-balance claim was added.
- Supplier email imports accept a manually uploaded `.eml`, preview up to five validated PDF/JPEG/PNG attachments, and require review before adding a bill. Original email/attachment hashes and provenance are retained; imports create a payable, not a paid expense. Sender/subject are untrusted labels; HTML/remote links are not fetched. Bounds: 2 MB raw email and 40 MIME parts. This is **not automatic Gmail/IMAP polling or mailbox authorization**.
- The owner question panel answers bounded recorded-data topics: cash/runway, locations with negative recorded cash movement, debtors/collection scenarios and subscription candidates. Results include supporting records/limitations. This first version uses deterministic calculations, **not a generative model**. Negative cash movement is not profit/loss; scenarios do not change records or promise collections.
- Financial review PDF includes monthly, Monday-week and daily recorded cash summaries plus current receivables/due dates. Maximum 366 days and 5,000 movements/invoices; excessive requests fail visibly instead of silently dropping data. It is **not an audit, credit score, lending decision or assessment of an owner's commitments**. History completeness remains unknown unless separately established. Missing transactions/bank data remain a limitation.

### Source, migration and runtime setup

New modules: `workspace_contacts.py`, `workspace_followups.py`, `workspace_owner_tools.py`, `workspace_supplier_email.py`; new UI: `WorkspaceCommunications`, `WorkspaceOwnerTools`, `WorkspaceBalanceAlerts`. Existing orders, invoices, balances, supplier imports, reports and signed WhatsApp webhook integrate these modules. No dependency was added.

After backup and review, apply **`scripts/sql/enterprise/006_customer_workflows.sql` after 005**, as migration owner. It adds four tables, bringing the private schema to **42 tables**: immutable contact/evidence history (only WhatsApp consent may change), reminder plans and message receipts. Runtime column grants allow only the intended status/counter changes. Prior migrations and existing amounts/evidence are unchanged. Runtime and restore checks now require 006; CI checks generated migration reproducibility and the new tests.

Use `enterprise.env.example` for optional outbound configuration. `LOAMY_WHATSAPP_OUTBOUND` maps an existing business ID to approved `phone_id`, `invoice_template`, `reminder_template`, `language`. The phone ID must also match the trusted inbound routes and existing Meta credentials/version. Leave outbound unset to disable live WhatsApp delivery. Never put tokens in client code or the repository.

Meta template contract: approved **DOCUMENT header**, uploaded original invoice PDF, and six body text parameters in order: customer name, invoice number, total, allocated payment, current outstanding balance, due date. Approval/language/content must match both configured templates. Reference: https://www.postman.com/meta/whatsapp-business-platform/request/2qbotrb/send-message-template-media . Verify this against the actual approved account/templates in staging; mocked requests do not establish Meta approval or customer arrival.

Run `python scripts/process_invoice_followups.py` as a separately supervised worker with the same production settings/TLS database access; `--once` processes one eligible plan and exits. The Dockerfile packages it. It is not launched implicitly inside web workers. First checks are now/within 30 days, intervals 1–90 days, maximum 1–10 accepted/captured reminders. Existing limits also apply (30 actor requests/hour, 60-second initial invoice and 24-hour reminder cooldown). Review paused/uncertain sends before creating another plan; never automatically retry them. The preview-only Run one due plan control returns 404 in production.

### Validation, testing checklist and remaining release gates

- Complete rehearsal: **92 tests passed, no skips**, in 134.156 seconds, with disposable TLS PostgreSQL and real offline OCR. It covers contacts, saved destinations, scoped roles, idempotency, reminders/payment/cancellation/revocation, mocked Meta PDF/template transport and signed receipts, email provenance/deduplication, owner evidence/PDF/chat and least-privilege runtime grants. Focused checks follow final small changes. Backup/restore compared all **42 tables**, including evidence bytes and financial rows, with the source unchanged.
- Scoped frontend lint and business-only production build passed. Repository-wide lint still includes unrelated legacy components and ignored local generated bundles; use the explicit CI frontend list above for this release. The new UI style detector reported no findings. No real message, bank connection, deployment or upstream merge occurred.
- Manual instructions are tracked in `docs/CUSTOMER-WORKFLOW-TESTING.md`, with structured source `docs/customer-workflow-tests.json`: **T59–T78** and **S09–S12** were appended to the existing testing sheet. Its tables, status formatting and summary formulas were extended to **78 manual + 12 Samuel = 90 checks**. Existing results/notes were preserved; new manual outcomes remain Not run, independent of automated test results.
- Clean `Dockerfile.enterprise` build stalled again downloading Debian packages and was stopped. A clean build/normal CI run with functioning package services remains a release gate; a cached-base rehearsal is not clean-build approval.
- Final focused **10 tests passed** in 11.438 seconds, including the negative-branch cash comparison and final consent/email validation changes. A network-disabled overlay of current modules, compiled UI and workers on the cached runtime passed the non-root/read-only/TLS-database/frontend/health/fail-closed container rehearsal. No databases or credentials were copied into that image. The generated fictional financial PDF was rendered and visually checked. Browser checks covered new contact creation, captured WhatsApp delivery, an explicit plan waiting until overdue, owner invoice drill-down and recorded branch answers. Real-provider delivery remains untested.
- Samuel must configure and verify real SMTP, Meta credentials/approved templates/document delivery/status callbacks, customer consent and opt-out handling (withdrawal is currently recorded manually; automatic customer STOP handling is not included), worker supervision, monitoring and crash/duplicate recovery. Test paid/cancelled/revoked races, provider timeouts and real arrival in staging. Apply only missing migrations, complete backup/restore and approve rollout. Automatic supplier mailbox ingestion, generative owner chat, live bank integration and lending suitability assessments remain separate work, not implemented claims.


## T69 fix and browser retest — 12 November 2026

T69 is now Pass on retest; current manual outcome is **18 Pass, 0 Fail, 2 Blocked**. Earlier failures above remain historical observations. Root cause: payment_totals marked cancellation but still returned total minus allocated as outstanding. It now returns zero collectible outstanding for cancelled invoices, preserving total, allocations, overpayment and immutable snapshots. Owner detail explicitly says Cancelled — nothing to pay. No migration or ledger rewrite.

Added an endpoint regression covering cancelled invoice detail, payment list and owner detail, with snapshot/original-total preservation. **40 tests passed** in 48.108 seconds across customer workflows, payments, invoices, owner, reports, notifications and pricing. Scoped JSX lint and business build passed. Browser retest confirmed zero outstanding in Payments & balances and invoice detail, original NGN 1,075.11 total/history retained, and explicit cancellation wording in Owner overview. Local screenshot: T69-fixed-owner.png in the existing QA evidence directory. Real production remains untested. T64 and the empty-period portion of T72 remain Blocked.


## Mobile workspace refinement — 12 November 2026

Preserved the existing green/cream visual identity and role checks. BusinessWorkspace now uses a mobile-only Menu disclosure at 760px and below, naming the active section. All existing permitted destinations remain available. Selection closes the menu and returns keyboard focus to its button; Escape also closes it. The inline scrollable menu needs no modal focus trap. Desktop retains its existing visible section navigation. The mobile menu stays reachable while scrolling.

BusinessWorkspace.css adjusts mobile content/header spacing, full-width grouped actions and list buttons, location action placement, 16px form controls, 44–48px summary/navigation targets and overview filters. Metrics use two columns on phones with enough space and one below 381px. The attention callout's pre-existing 3px side accent is reduced to 1px. No dependency, backend, migration, financial or permission change.

Actual checks: scoped JSX lint and business-only production build passed. Browser verified 390px width with scroll width also 390, disclosure open/selection-close, active-section label, restored button focus, Escape close, order-form 16px inputs and discarded draft (no saved test order). Final confirmation included narrow 320px single-column metrics and the 804px desktop/tablet view with visible navigation and hidden menu button. Temporary viewport overrides/tabs were removed. Screenshot mobile-dashboard.png is in the existing local QA evidence directory. The detector ran once and reported the pre-existing 3px attention border; that finding was corrected. No real phone, iOS Safari, physical touch, landscape or screen-reader test was performed.

Manual acceptance: (1) at phone width open Menu, select each permitted section, confirm active label/closure and scrollable destinations; (2) use Tab/Enter/Escape, confirm focus returns to Menu; (3) open New order, inspect stacked controls/actions and discard without saving; (4) compare dashboard metrics at 320/390px and desktop, test long references, keyboard/input zoom and a physical phone before release. Existing financial acceptance results are unchanged.


## Desktop and tablet workspace refinement — 12 November 2026

BusinessWorkspace adds a layout wrapper/main panel while retaining the exact existing conditional role destinations and page actions. At 1100px and above: a 210px persistent left navigation rail, bounded 1360px workspace, aligned header/footer, compact business identity spacing, four overview metrics and a single aligned filter row. At 761–1099px: a two-column disclosure menu with 48px targets, two-column overview filters/forms, wrapped record actions and a single-column team/invite layout to avoid squeezing controls. The previous mobile layout remains below 761px. Selection focus return now uses the same 1099px disclosure breakpoint; Escape remains supported. Menu content is inline, not modal. No financial, backend, data, schema or permission change and no dependency added.

Actual validation: JSX lint and business-only build passed. The detector ran once and returned no findings. Browser checked 1440px desktop, 1100px rail boundary, 1024px and 768px tablets, and a 390px phone regression. Measured page/scroll widths matched at 1440/1100/1024/768/390 during their checks. Desktop rail/four metric placement and final header alignment were visually reviewed. Tablet disclosure opened in two columns, selection closed it, Escape restored button focus, and New order retained two-column fields; the empty draft was discarded without saving. Phone disclosure selection still worked. Viewport overrides were reset. Local evidence: desktop-refined.png and tablet-refined.png in the existing QA directory. No real-device, Safari, physical-touch or screen-reader test; role controls were preserved by source rather than rerunning all role logins for this layout-only change.

Acceptance: check desktop rail scrolling/current section and action alignment; compare tablet portrait/landscape menu and date filters; open/discard long forms; confirm role-specific destinations remain the same; check phone behavior when resizing across 760/1099/1100px. Existing financial checklist outcomes are untouched.

## Samuel's local setup and acceptance guide — 13 November 2026

Added `SAMUEL-LOCAL-SETUP-AND-TESTING.md`, linked from README, for a fresh checkout of the development fork's `mohammeds-branch`. It covers Windows and macOS/Linux dependency commands, the guarded SQLite/captured-mail preview, separate fictional account verification/team invitations, ordered acceptance scenarios, optional offline OCR and backend/build checks, persistence/updates and troubleshooting. It provides Samuel-specific result columns so the user's and Codex's existing manual results remain unchanged. No private spreadsheet URL, credentials, database or local test evidence is included.

Documentation-only change: verified commands/paths/test-module names and UI labels against current implementation, checked local document references and Git whitespace. No new machine installation, runtime suite, provider delivery, staging or production validation was performed. Prior results remain historical; next-day reminder and empty-period PDF acceptance still need their actual checks. No application behavior, schema, deployment configuration or release gate changed.
