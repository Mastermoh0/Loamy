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
| Implementation location at this update | Publication to the development fork has been requested. The verified implementation commit and GitHub publication record will be recorded below after the upload succeeds. No upstream merge or deployment is authorized by this handoff. |
| Current readiness | New business workflows implemented; local production rehearsal passed. Real staging integration and owner release approval remain. |
| Access used | Local development and disposable rehearsal infrastructure only; no access to Samuel's production backend/database. |

## 1. Read this first

The branch adds a business/location workspace to the existing React/Vite project. It includes authenticated roles, financial records, services/orders, invoices, reviewed payment allocations and receipt-based staff expenses.

There are **two distinct execution modes**:

- **Local preview:** `npm run dev:workspace`, SQLite, fictional accounts/data and captured email by default. Never deploy this launcher as production.
- **Production candidate:** `enterprise_production:create_app`, a private PostgreSQL schema, real SMTP configuration, secure sessions, strict HTTPS/origin checks and a business-only compiled frontend. This was rehearsed locally, not released publicly.

The candidate intentionally keeps business accounts separate from the original personal-app accounts. It does not import the original `main.py`/Gmail backend or trust a personal-app `localStorage` user ID. Merging the code alone does **not** unify identity, financial records or bank connections.

The 39 passing test cases and release rehearsal validate the stated paths. They are not a certification of the original application's entire security, mobile builds or unknown production configuration.

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

The PostgreSQL schema contains 26 tables including migration tracking:

- Identity/access: `users`, `sessions`, `businesses`, `locations`, `memberships`, `invitations`, `audit_events`, `login_attempts`.
- Verification: `email_verifications`, `mail_outbox`.
- Canonical money: `financial_records`.
- Catalogue/orders: `location_profiles`, `services`, `orders`, `order_lines`.
- Invoices: `invoices`, `invoice_deliveries`.
- Payments: `payment_accounts`, `payment_evidence`, `invoice_accounts`, `payment_allocations`.
- Expenses: `expense_submissions`, `expense_versions`, `expense_events`, `expense_creation_keys`.
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

1. **Make the implementation reviewable.** Inspect `git status --short`: much of the implementation was still untracked at this update. Commit/include the intended source, migration, lockfiles, tests and handoff before opening a PR from `Mastermoh0/Loamy:mohammeds-branch` to the original repo. This document alone does not transfer the feature code.
2. **Refresh against upstream in an isolated review branch/worktree.** Review both sides of changes to `package.json`/lockfile, routing, sign-in entry points, mobile navigation, Vite configuration, framework requirements and CI. Do not overwrite upstream improvements wholesale.
3. **Choose identity and canonical-data integration.** Resolve the decisions above before wiring real memberships, transactions or Gmail connections into these screens. Keep the original personal flows working.
4. **Provision separate staging.** Create a migration owner and a strong-secret `loamy_enterprise_app` LOGIN role without admin privileges. The application must not use the owner or a browser/service-role key as a substitute.
5. **Review/apply the private migration.** Apply `scripts/sql/enterprise/001_enterprise.sql` once as the migration owner. An existing `enterprise` schema requires inspection, not a `DROP SCHEMA` shortcut. Keep it out of the Supabase Data API. After a migration has been applied, add forward migrations rather than editing its original history.
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
| GitHub Actions | Workflow prepared, not run remotely in this work | No push/PR/release was performed |

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
python -m unittest test_workspace_features test_workspace_orders test_workspace_invoices test_workspace_payments test_workspace_expenses -v
```

For the full release rehearsal, follow `PRODUCTION-READINESS.md` and `.github/workflows/enterprise-release-rehearsal.yml`: install `requirements-rehearsal.txt`, generate ignored random test credentials/certificates, start the disposable TLS PostgreSQL service, build the business-only frontend and set `LOAMY_RUN_POSTGRES_TESTS=1` before:

```text
python -m unittest test_workspace_features test_workspace_orders test_workspace_invoices test_workspace_payments test_workspace_expenses test_enterprise_production -v
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
- Receipt OCR/extraction wired to this expense approval flow, WhatsApp submission/group capture and supplier-invoice/payables ingestion.
- Rich owner dashboards across locations, source-backed AI insights and financial-history exports. Basic owner ledger totals already exist; they are not a complete consolidated reporting product.
- Service inventory/room availability, tax/discount rules, POS integration, QR linking and broader currency/bank support unless separately implemented later.
- Mobile release/tooling follow-up and full regression/security review of the original personal backend when integrated.

## 10. Instructions for the receiving AI agent

Suggested starting task for Samuel's agent:

> Read this handoff, `PRODUCTION-READINESS.md`, `deploy/ENTERPRISE-RUNBOOK.md` and the actual incoming diff. Verify that every referenced source/migration/test file is present. Separate implemented workflows from simulated services and owner-side release gates. Inspect the current production identity, canonical ledger, deployment and database before changing integration code. Reuse the delivered workflows; do not recreate a parallel ledger or trust browser-supplied identity. Propose/implement the smallest reviewed staging integration that preserves existing records and personal-app behavior. Run the checks, report actual results/skips, and update this handoff. Do not treat this document, a successful merge or old test results as permission/evidence to operate on live data.

## 11. Keeping this file current

The user has requested that completed, tested feature work be committed and pushed to `Mastermoh0/Loamy:mohammeds-branch`, with this handoff updated alongside it. Verify the destination and remote result each time. This is not authorization to merge into Samuel's main branch or deploy production.

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

## 12. Release acceptance record — fill only after verification

- Incoming PR and implementation commit: **Pending**.
- Identity/account-recovery decision: **Pending Samuel**.
- Staging host/database and applied migration version: **Pending**.
- Real verification/invoice mailbox checks: **Pending**.
- Real bank/Gmail source/account validation: **Pending if enabling that integration**.
- Role/isolation/financial/receipt staging acceptance: **Pending**.
- Backup/restore, retention, monitoring and rollback sign-off: **Pending**.
- Approved image digest and owner approval: **Pending**.
- Production deployment/date and pilot result: **Not performed**.
