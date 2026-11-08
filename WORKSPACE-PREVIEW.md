# Local business workspace

## Customer messages, invoice links and financial reports (8 November 2026)

Open **Customer messages** for current partial-payment/overdue invoice candidates. Prepare a draft, review its text/recipient and explicitly confirm local delivery. The preview captures the message; it sends no email. Changed balances require a fresh draft, and uncertain attempts are never automatically repeated. Production SMTP acceptance still needs real staging verification.

Open an issued invoice under **Services & orders** to create an expiring customer link. Preview it, copy it or hand it to the device share menu; no external message is sent automatically. Anyone holding the link can view that invoice and its current balance until expiry/revocation, so use fictional customers locally and share privately in production. The customer page exposes no workspace access. Manage/revoke links from the invoice panel.

Open **Insights & reports** to download a ZIP report for the selected dates/location with summary/ledger CSVs, current invoice balances, evidence references and optional original invoice/linked receipt files. Start with dates covering your fictional fixtures. A report keeps current balances separate from historical cash movements and excludes unposted receipts/private inbox messages. Read README/manifest coverage and keep spreadsheet escaping intact.

Owners also see completed-day cash burn, current debtors, recurring candidates and tracked subscriptions. Enter a verified cash amount and explicitly confirm observation coverage to model runway when recorded net burn is positive. The cash input and tracked subscriptions create no financial entries; cancelling tracking does not cancel a supplier's real service. These are deterministic recorded insights, not a live bank feed or generative financial advice.

## Supplier bills and WhatsApp receipts (7 November 2026)

Open **Supplier bills**, choose a location and import a fictional invoice (JPEG/PNG/PDF, 2 MB max). Extract optional suggestions, confirm supplier/reference/description/category/total/issue/due dates, then Save unpaid bill. This changes bills owed only. Record or confirm the matching expense debit in **Financial records**, then link all/part of that debit to the bill; no second expense is created. Payment corrections retain reversal history. Owner overview shows current supplier payables separately from cash flow and customer balances.

Under **Expenses & receipts**, expand **WhatsApp receipt inbox**. Real provider access is off until Samuel configures it. In the local preview, expand **Simulate an incoming receipt locally**, choose a fictional receipt and add its caption. Open its draft, optionally extract fields, confirm/edit them and submit for independent review. The source stays labelled as a simulation and the original file stays attached. No message is sent or real sender verified. Generate distinct ignored fixtures with `python scripts/create_receipt_test_fixture.py` (`fictional-supplier-invoice.png` and `fictional-whatsapp-receipt.png` under `.local-data/`).

For real signed WhatsApp events, sender linking and a supervised receipt worker, follow `deploy/ENTERPRISE-RUNBOOK.md`. Do not expose this loopback preview publicly. Group capture is disabled. Supplier imports, WhatsApp delivery, expense approval and paid ledger posting are separate actions.

## Owner overview and offline receipt reading (7 November 2026)

Owners can open **Owner overview** for combined/per-location recorded activity and current invoice balances. Date filters affect posted cash movement and orders; receivables and review queues are current across dates. Recorded account credits are not live bank balances.

For receipt reading, install Tesseract plus English data and Poppler on the host, or use the local Windows Docker fallback:

```powershell
docker build -f Dockerfile.receipt-ocr -t loamy-receipt-ocr:local .
$env:LOAMY_RECEIPT_OCR_DOCKER_IMAGE='loamy-receipt-ocr:local'
npm run dev:workspace
```

In **Expenses & receipts**, choose a receipt then select **Extract receipt details**. Confirm/edit vendor, NGN amount and purchase date; enter purpose/category and submit for a different reviewer. Neither extraction nor approval posts money. The same receipt hash and extraction provenance stay with each submitted version. Manual entry remains available when the reader is unavailable. No receipt is sent to a cloud OCR service. Extraction supports JPEG/PNG and PDFs of up to three pages, with the existing 2 MB upload cap. Generate an ignored fictional fixture with `python scripts/create_receipt_test_fixture.py` for local QA.

For the separate PostgreSQL production candidate and its verified rehearsal, read `PRODUCTION-READINESS.md` and `deploy/ENTERPRISE-RUNBOOK.md`. This document describes the SQLite local preview only; do not deploy its launcher.

Enterprise feature work on `mohammeds-branch`: businesses/locations, team permissions, email verification, location finances, service catalogues, front-desk orders and invoice/PDF/email delivery.

## Start

From this repository in PowerShell, first install dependencies:

```powershell
npm ci
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-preview.txt
```

Then run both servers with one command:

```powershell
npm run dev:workspace
```

Or start them individually. In one terminal:

```powershell
$env:LOAMY_LOCAL_PREVIEW='1'
./.venv/Scripts/python.exe -m uvicorn enterprise_preview:create_app --factory --host 127.0.0.1 --port 8001
```

In another:

```powershell
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open http://127.0.0.1:5173/business. The original app sign-in remains at `/` and includes a development-only business workspace link. Vite proxies the new same-origin API to port 8001; backend also checks local Host and Origin. Do not expose these servers to the internet.

Create a test business account, verify it using the private local inbox, then create your business and first location. Data persists in `.local-data/workspace.sqlite3`, excluded from version control. New business-account credentials are separate from existing Loamy accounts. Passwords use per-user salts and PBKDF2-SHA256; the server stores hashed opaque session tokens and sends HttpOnly/SameSite cookies with eight-hour expiry. Logout invalidates the stored session.

Owners can add locations and create one-use invitations (72-hour expiry) for manager, finance, front desk and staff roles. A non-owner can only read their assigned location and cannot manage locations/team access or see the owner team/audit list. To test an invitation locally, copy its link, sign out and create/sign in as the invited email, then open the link and accept. The owner's browser cannot impersonate that member. Owners can remove members, immediately revoking access; the owner cannot be removed. Another invitation for the same email replaces any unused earlier link.

## Test

```powershell
./.venv/Scripts/python.exe -m unittest test_workspace_features test_workspace_orders test_workspace_invoices test_workspace_payments test_workspace_expenses -v
npx eslint src/BusinessWorkspace.jsx src/WorkspaceOrders.jsx src/WorkspaceInvoice.jsx src/WorkspacePayments.jsx src/WorkspaceExpenses.jsx src/WorkspaceVerification.jsx src/WorkspaceFinances.jsx src/services/workspaceService.js src/App.jsx
npm run build
```

Tests use temporary databases, never this preview's persisted records. They cover setup/session persistence, cross-business isolation, all non-owner roles, invalid cross-business location assignment, invitation identity/replay/expiry, access revocation, validation and cross-origin rejection.

## Scope and next integration

This is functional local feature work, not a production authentication migration. The route exists only in Vite development mode. The backend refuses to start without the explicit local-preview flag, uses no production credentials and imports none of the existing Gmail/AI modules. Its default email transport captures messages locally and sends nothing externally. Captured-link verification is explicitly a simulation and does not prove mailbox ownership. Do not use captured verification to grant access to real financial data.

Before production: migrate the schema/authentication to the shared production identity/database, configure real verified-email invitation delivery, secure HTTPS cookies/origins and operational abuse controls, and apply business/location scope to the existing financial APIs. SQLite is deliberately confined to local development. Existing preview accounts must verify; their businesses and memberships are preserved. No production user or financial rows were migrated or edited.

Next integration: a scoped, tested real bank/Gmail import adapter and shared production identity/database. The local payments and expense flows below are functional; legacy financial endpoints still require their server-side authorization migration before integration.

## Email verification

Registration and resend issue a single-use link valid for 30 minutes, with a 60-second resend cooldown. Tokens are hashed in storage; resending replaces previous links. Confirmation requires the signed-in account to match the recipient. Verification rotates the session and blocks business, invitation and financial access until complete. Each account can see only its own captured messages.

For actual delivery while still running locally, set these environment variables in the terminal before restarting `npm run dev:workspace`: `LOAMY_MAIL_TRANSPORT=smtp`, `LOAMY_SMTP_HOST`, `LOAMY_SMTP_FROM`, `LOAMY_SMTP_USERNAME` and `LOAMY_SMTP_PASSWORD`. Optional `LOAMY_SMTP_SECURITY` is `starttls` (default, port 587) or `ssl` (port 465); `LOAMY_SMTP_PORT` overrides the port. Keep credentials out of source control. SMTP disables the local inbox, does not retain message bodies/links in the outbox, and requires real SMTP verification even for previously capture-verified users. Delivery failures appear in the UI. Links target this computer's loopback preview: open them on this same computer. Real delivery has not been configured or exercised; tests mock the SMTP connection.

## Location-specific financial records

Open **Financial records** or a location's **View financial records** button. Owners can filter all locations or one location; managers and finance members can read and record only their assigned location. Front desk and staff cannot access the ledger. The server enforces these boundaries independently of the UI.

Manual income and expense entries include location, date, description, category and recorded-by identity. Amounts are positive NGN values with at most two decimal places, stored as integer kobo. Future dates are rejected using the Lagos date. Totals include all posted entries in the selected scope; the list shows the latest 100. Net cash flow is income minus expenses, not a bank balance. Retried saves use an idempotency key to prevent duplicates. Void an incorrect entry with a reason: the original record remains visible and is excluded from totals, with an audit entry. Gmail imports and the legacy financial tables are not connected to this local manual ledger.

## Additional verification on 7 November 2026

- All 11 isolated backend tests passed, including verification identity/expiry/replay, SMTP failure and capture separation, exact monetary totals, duplicate protection, record void history and financial role/location/business boundaries.
- Targeted frontend lint and production build passed; the existing large-chunk warning remains. UI detector reported no findings on the changed workspace components/styles.
- Browser: verified the existing fictional owner, preserved the existing business and locations, saved a fictional NGN 50,000 Lekki income record, and confirmed Ikeja remained empty while the owner's all-location view included the record. The 390px layout had no horizontal overflow.

## Service catalogue and front-desk orders

Open **Services & orders**, choose a location, then **Service catalogue**. Owners and managers can add/edit a service name, description, positive NGN unit price and availability. Each location has its own catalogue. Services are deactivated rather than deleted, preserving historical orders. Under **Business details for orders**, edit the invoice business name, address and optional payment instructions. These details are copied into each new order; editing them later does not rewrite history.

Switch to **Orders → New order**. Select one or more services (up to 20 distinct items), enter positive whole-number quantities (up to 10,000 each), customer full name and phone or email. Email is not mandatory. The server calculates the exact total in integer kobo from its catalogue, checks the displayed prices against current prices, and rejects changed or unavailable items for review. It never trusts a client-supplied total, status or actor. Each saved order has a stable internal ID and a database-unique `ORD-date-randomID` reference. A save-retry key recovers the original order instead of creating a duplicate, including after catalogue changes. Prices, descriptions and quantities on saved orders are immutable snapshots.

The default list shows today's orders using the Lagos calendar date. **All dates** shows history. Counts cover the whole selected period/location; the list shows the latest 100. **View order** reopens saved customer, items, totals and business details. Status is **Open** or **Cancelled**: open does not mean paid. Cancellation requires a reason and is blocked while the invoice has active payment allocations or a current email attempt. Reverse incorrect allocations first; this does not refund money. Cancellation preserves the original order and records actor/time/reason; repeating it leaves the first cancellation intact.

| Role | Read catalogue/orders | Edit catalogue/business details | Create/cancel orders |
|---|---|---|---|
| Owner | Any location in their business | Any location in their business | Any location in their business |
| Manager | Assigned location | Assigned location | Assigned location |
| Finance | Assigned location | No | No |
| Front desk | Assigned location | No | Assigned location |
| Staff | No | No | No |

Front desk cannot read financial records. All boundaries are checked by the API on every request, including detail/cancel routes, and membership removal revokes access. Nonmembers and foreign locations/orders are not disclosed. Unverified accounts cannot use these endpoints.

The implementation is in `workspace_orders.py` and `src/WorkspaceOrders.jsx`, registered in the existing local API factory/workspace. SQLite schema creation is additive and preserves the existing preview records. API paths are `/enterprise-api/businesses/{business}/locations/{location}/catalogue`, `/profile`, `/services`, `/services/{id}`, `/orders`, `/orders/{id}` and `/orders/{id}/cancel`.

### Validation of this feature

- 20 backend cases passed in the combined regression run; an additional case passed for multiple-item exact totals, rollback on an invalid later item and the unverified-account gate. These include persistence, catalogue/profile snapshots, stale prices, idempotent retries, cancellation history, date filters, all roles, cross-location/business isolation and revocation.
- Targeted frontend lint passed; the production build passed with the existing large-chunk warning. The UI detector reported no findings.
- Browser walkthrough added the fictional **Test room night** service at NGN 25,000.10, saved two nights for **Preview Guest** at NGN 50,000.20, and cancelled with a test reason. All original details remained visible. Desktop and 390px mobile order entry were inspected; mobile had no horizontal overflow.

This remains a local preview. Orders themselves do not move money, issue refunds or post income into the ledger. Payments are recorded separately and allocated as described below. Tax, discounts and stock/room availability management are outside this slice.

## Invoice generation and email delivery

From **Services & orders → View order**, scroll to **Invoice**. Check the customer, items and business/payment details saved on the order, optionally set a due date, and choose **Generate invoice**. This issues version 1, stores an immutable snapshot and PDF, and assigns a database-unique invoice number linked one-to-one to the order. Repeating generation with the same due date returns the existing invoice. An issued due date cannot be silently changed. Catalogue/profile edits never rewrite an issued PDF. Orders without customer email can still generate/download an invoice.

The page previews the document and provides **Download invoice PDF**. The PDF includes business/location identity, customer/contact, invoice number/version, order reference, dates, quantities, exact prices, total and any saved payment instructions. It uses NGN labels, wraps long text and repeats table headers over multiple pages. Generation and download do not send email. The preview is explicitly a local development invoice, not a payment receipt.

Owners, managers and front desk can generate and request email delivery for their authorized locations; finance can read/download but cannot issue or send; staff cannot access invoices. All routes reuse authenticated order/location permissions. The API is `/enterprise-api/businesses/{business}/locations/{location}/orders/{order}/invoice`, plus `/pdf`, `/email`, and `/email/{delivery}/attachment` for a captured attachment. The captured attachment is the exact original PDF, including after a later cancellation; its historical nature is clearly labelled.

### Local email testing and real delivery

Default `capture` mode provides **Test invoice email**. Enter/review one customer email address; the message and original PDF attachment are captured locally and visible under that invoice's **Email history → View captured email**. No external email is sent. This is separate from the private account-verification inbox.

The existing `LOAMY_MAIL_TRANSPORT=smtp` configuration above also enables actual invoice delivery through the shared TLS SMTP transport. It needs no Gmail write permission. Test with an address you control after configuring the sender; SMTP-mode accounts must complete real email verification. The button becomes **Send invoice email**. No real provider/account has been configured or exercised in this work; SMTP tests are mocked. Provider acceptance is not proof of arrival in the recipient inbox, and there is no bounce/webhook tracking yet.

Delivery states are separate from invoice state: `captured`, `sending`, `accepted`, `failed` (definite configuration/authentication/recipient failure), or `unknown` (an interruption/SMTP error where acceptance cannot be established). A stale `sending` attempt becomes `unknown` when invoice status is refreshed after two minutes. Repeating an email request with its same save key recovers that attempt without sending again. An uncertain result must be checked before deliberately sending another copy. **Prepare another copy** makes that a separate explicit action; the server enforces a one-minute invoice cooldown and 30 requests per actor per hour. SMTP history stores recipient, subject, status and times, but not the message body or credentials. The original invoice PDF remains stored for downloads/attachments.

Cancelling an order also cancels its invoice atomically. A current PDF download is prominently marked **CANCELLED INVOICE**; the original issued PDF remains preserved. New email requests are rejected after cancellation. Cancellation is blocked during an active email attempt or while payment allocations remain; it never recalls a sent email, notifies the customer, issues a refund or changes the ledger. Repeated cancellation preserves the first reason/actor/time. Invoice revisions and credit notes belong to later work.

## Payment matching, partial payments and outstanding balances

Open **Payments & balances** and select a location. Owners can use their locations; managers/finance only their assigned location. Front desk cannot browse the credit queue or allocate money, but can see current payment status/balances when reopening an invoice. Staff cannot access payments. All checks are enforced server-side.

The canonical money source is `financial_records`: an existing posted NGN income entry can be allocated directly, without creating another income. Alternatively record a cash payment or **test** bank credit here, using its original receipt/source reference. A repeated source reference within its receiving account (or the location's cash group) returns the same record; a conflicting replay is rejected. The date must be today or earlier. The bank-credit path is manually entered local evidence, not a verified live feed. Never re-enter an existing ledger payment under a different source reference.

Add receiving accounts per location. Bind each bank-paid invoice to its expected receiving account in **Receiving account and allocation history**. This is audited matching metadata and does not rewrite the issued invoice PDF; check that the printed instructions agree. The API rejects bank-credit allocations with a missing/different expected account. Cash/manual income can be explicitly allocated without bank binding.

The review queue shows the latest 100 posted income records, available amounts and suggested candidates. Reference matching uses complete invoice/order reference boundaries and receiving-account scope. Full-name plus amount is only supporting evidence. Several candidates are labelled ambiguous; missing evidence remains unmatched. No suggestion allocates automatically. A reviewer selects the existing income, invoice, amount and evidence note, then **Confirm allocation**.

Allocations use integer kobo and independent history rows. Several payments can settle one invoice and one income record can be split across invoices, but allocations can never exceed that record's unallocated amount. Current invoice state is unpaid, part-paid, paid or overpaid; outstanding is max(invoice total minus active allocations, zero), and overpayment is shown separately. Issued PDF bytes remain historical; current balances appear in-app. Selecting **Refresh balances and delivery** reloads an open invoice's state.

Save retries recover the same allocation using their key. Finance can reverse an allocation with a reason; actor/time/original amount are retained and the available balance reopens. Reversal does not refund or delete the actual income. An allocated income cannot be voided, and a paid/part-paid invoice cannot be cancelled, until its active allocations are reversed. Changing a receiving account is likewise blocked while active allocations remain.

Implementation: `workspace_payments.py`, `src/WorkspacePayments.jsx`; location API `/payments`, `/payments/accounts`, `/payments/invoice-account`, `/payments/credits`, `/payments/allocations` and `/payments/allocations/{id}/reverse`.

## Staff expenses, receipts, approval and categories

Open **Expenses & receipts**. Any member can submit an expense with vendor, purpose, category, exact NGN amount, date and JPEG/PNG/PDF receipt (2 MB maximum). File signatures are checked; images are validated and limited to 20 million pixels. Receipt bytes are stored privately in SQLite, never as public URLs, with a content hash per immutable version. Download requires current business/location membership and expense access. Non-finance staff/front desk can see only their own submissions; owners/managers/finance can review their authorized location's submissions. Receipt data is entered manually; OCR, WhatsApp and supplier-mail ingestion are not connected.

States are submitted → approved / rejected / needs clarification. A different owner, manager or finance member must review the expense: self-review is blocked, including for the owner. Review records require a reason and the version number, rejecting stale or repeated decisions. The submitter can revise and resubmit rejected/clarification-needed entries with receipt evidence; old values and receipts remain available. A receipt already submitted in the same business cannot be silently submitted again under another save key. Submission/revision retries are idempotent.

Approval does not post money. Finance must explicitly **Post or link expense** with a reason. Post only an actual expenditure; approval/receipt submission alone is not proof of payment. Link a previously recorded debit for the same purchase when available. It must match business/location, positive NGN amount, date and category, and cannot already be linked to another receipt submission. Otherwise create one canonical expense entry. Similar existing debits block a new entry unless the reviewer explicitly confirms this is a separate purchase. Repeated posting recovers the same ledger link rather than adding another expense.

**Posted expense categories** totals the canonical posted expense ledger (including existing manual records), excluding pending approvals and voids. Category details show each record, source/date, recorder and submitter, with an authorized receipt link when present. A linked debit counts once. Voiding an incorrect ledger entry preserves the submission/history and displays the linked ledger's void status/reason; it does not silently post the receipt again. Further corrections require deliberate ledger handling.

Implementation: `workspace_expenses.py`, `src/WorkspaceExpenses.jsx`; location API `/expenses` for list/submit, `/{id}` for resubmit, `/{id}/review`, `/{id}/post`, `/{id}/receipt/{revision}`, and `/categories/{category}`. All schema changes are additive to the existing ignored local database.

### Combined validation

- All 34 workspace/order/invoice/payment/expense backend cases passed in the final combined run, including money precision, duplicate prevention, split/partial/overpayments, reversals, ambiguity/account/location checks, receipt privacy, revisions, self-review/stale-review rejection, debit linking and category totals.
- Targeted lint and production build passed; the pre-existing large-bundle warning remains. The UI detector reported no findings.
- Browser allocated fictional NGN 45,000 from the existing NGN 50,000 income to the NGN 50,000.20 invoice: NGN 5,000.20 remains outstanding and the original income still counts once. A complete server restart retained the allocation.
- Browser uploaded a fictional PNG receipt and submitted an NGN 1,000.10 Supplies expense as Preview Owner. It remains submitted, with self-review correctly unavailable. Independent staff review/post/link/category behavior was verified by authenticated API tests using temporary databases.
- Desktop and mobile inspection evidence is saved under `../output/loamy-study/`. No real bank connection, money transfer, refund, production data or external customer message was used. Real Gmail import, automatic settlement, receipt extraction and WhatsApp capture remain separate integrations.

### Validation of invoices

- All 27 backend cases in the combined workspace/order/invoice run passed: stable invoice identity/PDF snapshots, due-date rules, exact totals, retries, captured attachments, mocked SMTP with the PDF, refusal/failure/uncertainty, role/location/business isolation, cancellation and in-flight protection.
- Targeted frontend lint and production build passed. The existing large-bundle warning remains. The UI detector reported no findings.
- Browser generated fictional invoices, captured their test emails, and displayed a saved due date of 14 November 2026. The date form was corrected after browser testing. Desktop and 390px mobile invoice layouts were inspected with no horizontal overflow.
- PDF downloads and original attachments were verified by authenticated API tests. The browser's automated download-event check stalled, so OS-level browser file saving was not confirmed. The persisted one-page dated invoice and a six-page long-content PDF were rendered and inspected successfully.
- Sample dated invoice: `../output/pdf/dated-invoice-preview.pdf`; it contains fictional preview data only. No customer message or production data was used.

## Verified on 7 November 2026

- Six isolated backend test cases passed, including all four non-owner roles and the access/identity boundaries listed above.
- Targeted lint for the new workspace UI/service, app routing and launcher passed; frontend production build passed with the pre-existing large-chunk warning. The repository-wide legacy lint backlog was not repaired.
- Browser walkthrough: register local owner, create fictional Palm House test business, save Lekki and Ikeja locations, create an invitation, register its test recipient, accept and see only the assigned Lekki location, sign out and return to the owner. Reload and a complete two-server restart retained records and session.
- Desktop and 390px mobile layouts inspected; mobile document/main width matched the viewport without horizontal overflow. No production API or financial service was used.
- Preview test accounts use fictional example.test addresses. The browser is left signed into Preview Owner; sign out to create your own test account/business. This test data remains only in the ignored local database.
