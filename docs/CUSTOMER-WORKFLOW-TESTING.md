# Customer workflows: manual acceptance checks

Added 12 November 2026. These are instructions, not completed manual results. Use fictional data in local preview; Samuel must supervise live-provider staging tests. Existing checklist outcomes remain unchanged.

## Your checks

### T59 — Contacts: separate email and WhatsApp

**Sign in as:** Owner

**Before starting:** T06 service available. Use fictional contacts only. Keep this new invoice unpaid for T63–T64.

1. Create QA Channel Guest with primary email qa-channel@example.test and WhatsApp +2348012345678.
2. Add alternate email qa-alternate@example.test, select WhatsApp preference and record customer permission.
3. Save the order and generate an invoice due today.

**Expected:** Order saves both contacts and preference. Invoice still has exact saved pricing. Saving/generating sends no message.

### T60 — Contacts: invalid numbers and missing permission

**Sign in as:** Owner

**Before starting:** Use a separate disposable draft, not the saved T59 order.

1. Try WhatsApp number 08012345678 without a country code.
2. Try WhatsApp preference without recording permission, or a malformed email.
3. Correct the fields or discard the draft.

**Expected:** Invalid contact choices cannot be saved. A country-code number and permission are required for WhatsApp preference.

### T61 — Delivery: capture a WhatsApp invoice locally

**Sign in as:** Owner

**Before starting:** T59. Confirm the page says Local preview; no live credentials are needed.

1. Open T59 invoice and Customer delivery & follow-ups.
2. Choose WhatsApp, check the customer/destination confirmation and Capture invoice delivery locally.
3. Refresh communication history.

**Expected:** One whatsapp_capture entry shows captured and the intended number. No actual WhatsApp message is sent. The original invoice remains downloadable.

### T62 — Delivery: choose an alternate saved email

**Sign in as:** Owner

**Before starting:** T61. Wait at least one minute after that invoice’s last delivery, or use another saved-contact invoice.

1. In the same delivery panel choose Email and the saved alternate address.
2. Confirm the destination and capture the invoice locally.
3. Check channel history and try sending without the confirmation checkbox.

**Expected:** Only the selected saved address is used; other emails are not copied automatically. Confirmation is required. Local status is captured, not a real inbox delivery.

### T63 — Follow-ups: opt in to a bounded reminder plan

**Sign in as:** Owner or Finance

**Before starting:** T59 invoice has a due date and positive balance. Do not create competing plans for it.

1. Expand Schedule overdue follow-ups. Choose email or consented WhatsApp.
2. Leave first check blank for now; set interval 1 day and maximum 2. Confirm and Enable reminder plan.
3. Choose Run one due plan locally.

**Expected:** One active plan is saved. If the invoice is not overdue, the worker waits until overdue and displays its next check. Creating a plan does not send immediately.

### T64 — Follow-ups: next-day local reminder capture

**Sign in as:** Owner or Finance

**Before starting:** T63. Return after the due date AND the displayed next check time. Do not change the computer clock.

1. Refresh communication history for the still-unpaid invoice.
2. Run one due plan locally and open Customer messages history.
3. Run again immediately and check the plan count/history.

**Expected:** One current-balance reminder is captured. Count increases once, next check moves forward, and an immediate rerun does not create another send. Maximum remains 2.

### T65 — Follow-ups: paying stops the next due send

**Sign in as:** Owner or Finance

**Before starting:** Use an overdue unpaid test invoice. Cancel its previous plan before enabling a fresh plan with first check now.

1. Enable the fresh plan while the invoice still owes money.
2. Before running it, record/allocate the remaining fictional payment.
3. Run the due plan locally and inspect its history.

**Expected:** Due worker check marks the plan stopped and creates no new reminder. A paid invoice never receives a new automatic reminder. Existing messages are retained.

### T66 — Follow-ups: cancel a plan and an unpaid order

**Sign in as:** Owner or Finance

**Before starting:** Separate unpaid test invoice with no active payment allocations.

1. Enable a plan, then Cancel reminder plan.
2. Refresh and confirm cancelled status.
3. For another due plan, cancel its unallocated order before the worker check and run when due.

**Expected:** Explicit cancellation prevents later checks from sending. A due check on a cancelled invoice stops without delivery. History is retained; nothing is refunded.

### T67 — WhatsApp: withdraw customer permission

**Sign in as:** Owner or Manager

**Before starting:** An unpaid WhatsApp-contact invoice with recorded permission and an active WhatsApp reminder plan.

1. Choose Record withdrawn WhatsApp permission.
2. Refresh history and inspect the plan.
3. Try another WhatsApp delivery with a new confirmation.

**Expected:** Permission is withdrawn, active WhatsApp plans are cancelled, and new WhatsApp sends are refused. Email is not used as an automatic fallback. Messages already in flight cannot be recalled.

### T68 — Front desk: partial-payment alerts

**Sign in as:** Front desk

**Before starting:** T05 account assigned to the same location as a partly paid test invoice. Create a separate fictional partial allocation if needed.

1. Open Services & orders and Partial-payment & overdue alerts.
2. Refresh balance alerts or wait for the 30-second refresh.
3. Choose Open alerted order and compare the remaining amount.

**Expected:** Correct customer/invoice and current remaining amount are visible. Front desk can open its permitted order without gaining ledger or payment-allocation access.

### T69 — Unified owner view: order and invoice detail

**Sign in as:** Owner

**Before starting:** Saved invoices at your test locations; select an overview date range that includes them.

1. In Owner overview choose All locations and Update overview.
2. Choose View location orders & invoices for one location, then Explore orders & invoices.
3. Check status/current balance and download one invoice.

**Expected:** Details match the chosen scope and period. Current invoice balances are labelled separately from period orders. PDFs open; no other business appears. Long lists disclose the 250-row limit.

### T70 — Unified owner view: expense evidence

**Sign in as:** Owner

**Before starting:** T31/T33 posted receipt-backed expenses and an overview period covering them.

1. In Owner overview choose View location expense evidence.
2. Inspect category, amount, submitter/recorder and supporting receipt.
3. Switch locations and compare the records.

**Expected:** Posted expense details and original linked receipt agree. One location’s records do not appear as another’s; no duplicate cash entry is created by viewing evidence.

### T71 — Financial review PDF: month/week/day history

**Sign in as:** Owner

**Before starting:** An overview date range covering your test records; choose six calendar months if desired (up to 366 days).

1. Update overview dates/location, then Download financial review PDF.
2. Open the PDF and inspect monthly, weekly and daily cash totals, current receivables and due dates.
3. Compare it to a financial-history ZIP for the same scope.

**Expected:** PDF is readable and totals reconcile to posted records. Voids are excluded from cash totals. Receivables are clearly current; due dates are not predicted collection dates. No audit, profit or creditworthiness claim is made.

### T72 — Financial review: scoped and honest coverage

**Sign in as:** Owner, then Manager

**Before starting:** T71. Manager is not an owner.

1. Download separate per-location PDFs and compare scope/coverage notes.
2. Review a period with no recorded movements.
3. Sign in as Manager and check that owner-review/chat actions are unavailable.

**Expected:** Scope and missing-history limitations remain explicit. Empty history is not invented. Owner-only review/chat do not become accessible to Manager or other non-owner roles.

### T73 — Owner chat: recorded branch cash comparison

**Sign in as:** Owner

**Before starting:** Owner overview. No API key or AI provider is needed for this first recorded-data assistant.

1. Expand Ask about recorded cash, debtors or subscriptions.
2. Ask Which branch is losing money? Choose 30 completed days.
3. Open Evidence and assumptions, then try a single-location overview selection.

**Expected:** Answer compares recorded inflow/outflow for the authorized branches, identifies negative cash movement and states it is not profit. Today is excluded from completed-day observation.

### T74 — Owner chat: collection scenario and runway

**Sign in as:** Owner

**Before starting:** For an exact fixture use T42’s Ikeja QA with only 3,000.00 historical net burn over 30 days. Create an unpaid invoice there owing at least 1,000.00; order/invoice creation adds no cash.

1. Select Ikeja QA in the overview and Update overview.
2. Ask Who owes us?, observe 30 days, enter cash 6000.00 and immediate collection scenario 1000.00. Confirm history coverage.
3. Ask again without the coverage confirmation.

**Expected:** With the isolated fixture, modeled immediate-collection runway is 70 days (7,000 / 100 daily burn). Without complete-history confirmation the estimate is unavailable. No payment or allocation is created.

### T75 — Owner chat: subscriptions and unsupported topics

**Sign in as:** Owner

**Before starting:** Tracked commitments from T43, or add a distinct active fictional commitment for this test.

1. Ask What subscriptions are we tracking? and inspect evidence.
2. Compare amounts/status to Insights & reports.
3. Ask an unrelated question such as Write a poem.

**Expected:** Tracked commitments/patterns agree with records. Chat does not cancel billing, post money or invent an answer for unsupported topics; it explains its supported recorded-data topics.

### T76 — Supplier email: review an .eml attachment

**Sign in as:** Owner or Finance

**Before starting:** Use a fictional supplier email exported as .eml (2 MB max), with 1–5 PDF/JPEG/PNG invoice attachments. No real mailbox connection is required.

1. Open Supplier bills and Import supplier invoice.
2. Expand Import an attachment from an email file and choose the .eml.
3. Review the unverified sender/subject and select the intended attachment; optionally extract its details.

**Expected:** Attachments are available for review. Email text/headers are not trusted instructions or proof of sender identity. Preview creates no bill or expense.

### T77 — Supplier email: import once with provenance

**Sign in as:** Owner or Finance

**Before starting:** T76. Choose a new fictional supplier reference/file not already imported into this business.

1. Confirm supplier/reference/category/amount/issue/due dates and Save unpaid bill.
2. Download/compare the original invoice and check supplier owed against Financial records.
3. Try importing the same email attachment/reference again.

**Expected:** One unpaid bill and email/attachment hash provenance are recorded. Original evidence is retained, duplicate import is refused/recovered, and no paid cash expense is posted automatically.

### T78 — Communications: role and location limits

**Sign in as:** Front desk, Finance, Staff

**Before starting:** T05 accounts and a saved-contact invoice assigned to their location.

1. As Front desk, inspect invoice delivery and try accessing reminder management.
2. As Finance, inspect reminder management and original invoice delivery restrictions.
3. As Staff, or through another location’s private URL, try the same communication screen.

**Expected:** Front desk may send invoices but cannot schedule reminders. Finance may schedule but cannot send original invoices. Staff and other-location accounts cannot access the private communications.

## Samuel staging checks

### S09 — Live WhatsApp invoice and delivery receipts

**Sign in as:** Samuel + you

**Before starting:** Staging only. Approved business number, permission, matching document-header templates, language and controlled recipient are configured by Samuel.

1. Apply migration 006 and configure outbound routing/templates from the handoff.
2. Explicitly send a fictional invoice to the controlled consented WhatsApp number.
3. Confirm phone arrival/PDF and inspect signed delivered/read status updates.

**Expected:** Actual PDF reaches the intended test number. Accepted is distinguished from delivered/read. Invalid signatures or another phone ID cannot update its history.

### S10 — Supervised follow-up worker and stop conditions

**Sign in as:** Samuel + you

**Before starting:** Staging mail/WhatsApp test destinations. A reviewed overdue plan is explicitly enabled; no real customer campaign.

1. Start the dedicated invoice follow-up worker using the reviewed image/database.
2. Exercise due email/WhatsApp plans and verify latest remaining balances.
3. Pay/cancel the invoice, withdraw WhatsApp permission or remove the plan creator, then observe the next due check.

**Expected:** Worker sends only explicitly enabled, eligible plans. Stop conditions prevent new sends. Interval/max counts and one-per-invoice/24-hour guards hold; no automatic channel fallback occurs.

### S11 — Uncertain delivery, worker restart and duplicate guard

**Sign in as:** Samuel + you

**Before starting:** Controlled staging provider/SMTP failure simulation and operator logs.

1. Interrupt a worker after claim or simulate an uncertain send result.
2. Restart and inspect plan/attempt history.
3. Exercise failed delivery receipts and investigate before replacing any plan.

**Expected:** Interrupted or uncertain attempts pause for review, rather than blindly retrying. Provider rejection/failure stays visible. A cancelled running plan is not reactivated after the send returns.

### S12 — Financial PDF and assistant staging reconciliation

**Sign in as:** Samuel + you

**Before starting:** Samuel’s representative staging records, reviewed coverage and retention rules.

1. Reconcile a six-month PDF and detailed ZIP against known posted records and invoice balances.
2. Exercise owner chat on branch flows, debtors, collection scenarios and subscriptions.
3. Review missing data, transfers and borrower-facing language with Samuel.

**Expected:** Report and assistant remain evidence-based and permission-scoped. Neither claims audited profit, bank balances, guaranteed collections, borrower ratings or automatic loan decisions. Automatic supplier mailbox polling and generative AI remain separate future integrations.
