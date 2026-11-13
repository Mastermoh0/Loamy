# Samuel: run and test Mohammed's Loamy branch

Prepared 13 November 2026. This guide is for Samuel and anyone helping him review the work. Loamy is also called Lumi in the project discussions.

**Goal:** run the new business workspace on your own computer, create fictional records, and check the features before deciding how to integrate them into the main application. You do not need the production database, Supabase keys, Google keys, SMTP credentials or Meta credentials for this first review.

## 1. Get the correct repository and branch

Use **https://github.com/Mastermoh0/Loamy**, branch **`mohammeds-branch`**. The new work is in this fork; cloning only `Sammythe-King/Loamy` will not necessarily include it. Accept the GitHub collaborator invitation if you want to push changes to the fork. The repository is public, so accepting is not necessary just to clone and run it.

Install Git, Node.js **22.12 or newer within Node 22**, and Python **3.14**. Python 3.14 is the version used in the existing local environment; other Python versions are not verified by this guide. Use your usual editor and a current browser. Docker is optional for receipt extraction and the separate production rehearsal.

Official installers: [Git](https://git-scm.com/downloads), [Node.js](https://nodejs.org/en/download), [Python](https://www.python.org/downloads/). On Windows, enable Python's PATH option if offered, then reopen PowerShell after installation.

Check the tools in a terminal:

```text
git --version
node --version
npm --version
python --version
```

From the folder where you keep projects:

```text
git clone --branch mohammeds-branch --single-branch https://github.com/Mastermoh0/Loamy.git Loamy-Mohammed
cd Loamy-Mohammed
git branch --show-current
git log -1 --oneline
```

The branch check should print `mohammeds-branch`. Record the displayed commit in your test results. A separate folder keeps this review apart from any existing upstream checkout. If using GitHub Desktop instead, clone this fork, choose `mohammeds-branch`, and open its folder in a terminal.

## 2. Install the local dependencies once

Run all commands from the folder containing `package.json` and `requirements-preview.txt`.

**Windows / PowerShell:**

```powershell
npm ci
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-preview.txt
```

If Windows has `py` instead of `python`, use `py -3.14 -m venv .venv` for the environment-creation line. Calling the environment's Python directly avoids needing to activate a PowerShell script.

**macOS / Linux:**

```sh
npm ci
python3.14 -m venv .venv
./.venv/bin/python -m pip install -r requirements-preview.txt
```

The macOS/Linux commands match the launcher's supported paths; a fresh setup on those systems has not been run for this document.

Do not copy a production `.env` into this checkout. `env.example` describes legacy integrations and `enterprise.env.example` describes production configuration; neither is required for this preview. Use a new terminal without inherited live SMTP/WhatsApp settings. To explicitly select captured email in PowerShell:

```powershell
$env:LOAMY_MAIL_TRANSPORT='capture'
```

On macOS/Linux use `export LOAMY_MAIL_TRANSPORT=capture`. Leave live WhatsApp integration settings unset. Captured messages stay in the test application instead of going to a real recipient.

## 3. Start and open the application

```text
npm run dev:workspace
```

Keep this terminal open. This command starts both the business API on port **8001** and the browser app on port **5173**, restricted to this computer. It also disables the legacy background scheduler.

Open **http://127.0.0.1:5173/business**. Use that exact address consistently. The root `/` is the original personal application; use `/business` to review the new work. `npm run dev` alone does not start the business API, and `npm run preview` is not a replacement for the combined launcher.

Expected: the business sign-in/registration screen loads, with local-preview messaging. A new checkout starts empty. Mohammed's local accounts, receipts and test records are not included in Git.

## 4. Create your test business and team

1. Register a fictional owner such as `samuel-owner@example.test` with a password used only for this test.
2. On **Verify your email**, open **Your local inbox → Open verification link → Verify test account**. This is simulated verification; do not wait for a real email. If expired, request a replacement and use the latest link; resend has a one-minute cooldown.
3. Create a business such as **Samuel Local QA**, with **Lekki** as its first location. Add **Ikeja** to test location separation.
4. From the owner's team controls, create invitations for fictional manager, finance, front-desk and staff accounts, assigning each to Lekki. Give each a different email, for example `samuel-finance@example.test`.
5. Copy each invitation privately. Sign out, register/verify the matching email, then open and accept that invitation while signed in as its recipient. Do not create a second business for each invited user.
6. Use separate browser profiles for simultaneous roles, or sign out before switching. Ordinary tabs in the same profile share the login. Keep your account/password notes private.

The owner sees all business locations. Other roles are assigned one location. Owner/manager/finance can independently review other people's expenses; **nobody can approve their own expense**. Front desk handles permitted order/invoice actions without ledger or allocation access. Staff sees their own expense submissions.

## 5. Test in this order

Use fictional contacts, receipt images and money. Enter dates relative to your actual testing date. These are new acceptance steps for your fresh database, not claims that these tests have already passed on your computer.

| Order | What to do yourself | Expected result |
|---|---|---|
| 1. Session and locations | Sign out/in. Switch Lekki/Ikeja. Create a service only in Lekki. | Account/business persist; the service does not appear in Ikeja. |
| 2. Catalogue and orders | In **Services & orders → Service catalogue**, add a service at NGN 1,000.00. Create an order for quantity 2 using a fictional customer. | Total is NGN 2,000.00; a stable order reference is shown. Editing the service later does not rewrite the saved order. |
| 3. Taxes and discounts | As owner/manager, configure a fictional 7.5% exclusive tax. Create a separate quantity-2 order with a 10% discount. | Subtotal 2,000.00; discount 200.00; tax 135.00; final total 1,935.00. Old orders keep their original pricing. |
| 4. Invoice and contact channels | Issue the first order's invoice with a due date. Download/open its PDF. On a separate order save primary/alternate email, a country-code WhatsApp number and permission; select each saved delivery channel and confirm local capture. | PDF matches saved details. History identifies the selected recipient/channel and says captured; no real email/WhatsApp arrival is expected. |
| 5. Partial/full payment | In **Payments & balances**, set up a fictional receiving account, record a supported fictional credit/cash evidence, and allocate NGN 750.00 to the first NGN 2,000.00 invoice. Then allocate another 1,250.00. | Remaining becomes 1,250.00, then 0.00/paid. Allocation does not add another copy of the income. A repeated allocation cannot exceed available credit. |
| 6. Cancellation | Create another unpaid order/invoice, cancel it with a reason and inspect invoice detail, payment list and owner detail. | Original amount/history remain; collectible outstanding is zero and cancellation is clear. No refund or transfer occurs. |
| 7. Staff receipts | Submit a fictional receipt as Staff. Try self-approval, then review as Finance/Manager; request clarification, resubmit and approve. Explicitly post/link the approved expense. | Self-approval refused. Original/corrected versions remain. Approval alone does not post money; final posting appears once in categories/ledger. |
| 8. Supplier bills | Import a different fictional invoice in **Supplier bills** and save it unpaid. Record its actual fictional expense debit, then link part/all of that existing debit to the bill. | Bill increases money owed without immediately increasing paid expenses. Linking reduces the payable without a second debit. Duplicate reference/file is refused. |
| 9. Receipt extraction and WhatsApp intake | If OCR is installed, extract receipt suggestions and correct them before submitting. In the WhatsApp receipt inbox, use **Simulate an incoming receipt locally** and open its expense draft. | Suggestions remain editable; original evidence is retained. Simulation is labelled; no real sender is verified and no actual WhatsApp message is received. Without OCR, test manual entry and record extraction as Blocked. |
| 10. Follow-ups and alerts | Enable a reminder plan for an unpaid due-dated invoice; use **Run one due plan locally** when eligible. Repeat immediately. Fully pay or cancel another planned invoice before its next check. Sign in as Front desk to inspect partial/overdue alerts. | Due capture/history are visible without duplicate immediate sends. Paid/cancelled invoices stop at worker check. A plan waiting until overdue is not a passed send test; return after its displayed next check without changing the clock. Front desk sees only allowed alerts/actions. |
| 11. Owner dashboard and chat | Compare combined/per-location overview against the records you entered. Drill into orders/invoices/posted receipt evidence. Ask a supported branch cash-flow or subscription question and inspect its evidence. | Totals reconcile once per posted cash entry. Unpaid invoices/payables remain separate from cash. Answers describe recorded data, not live bank balances or profit. Non-owners have no owner-only controls. |
| 12. Reports and invoice links | In **Insights & reports**, export a date/location ZIP including originals; open CSVs/manifest and compare your totals. Download the financial-review PDF. Repeat for one location and an empty period. Create an invoice customer link, open it signed out, then revoke it. | Export/PDF have the stated scope, matching amounts and supporting files. Current balances are labelled current. Customer link exposes only its invoice; revoked link stops working. Local links work only on this computer. |
| 13. Supplier email import | Upload a fictional `.eml` containing a small PDF/JPEG/PNG supplier invoice; review and confirm the selected attachment before saving. | Preview alone posts nothing. Saved bill retains provenance and original evidence; duplicate import fails. This is a file upload, not automatic Gmail polling. |
| 14. Layout and QR | Resize browser to 1440, 1024, 768 and 390px. Navigate, open/discard forms, scroll cards and try Tab/Enter/Escape. Under Locations, show/download QR and open its copied link while signed in with allowed/disallowed location access. | Desktop rail at 1100px+; disclosure menu below that, two columns on tablet; stacked phone controls. No sideways page overflow or hidden actions. QR selects only an authorized location and grants no membership. Physical phone scanning needs a suitable HTTPS test host, not loopback. |

Use a separate fictional document for each purchase/import scenario so duplicate-file protection does not interfere with unrelated tests. Receipt uploads support JPEG/PNG/PDF up to 2 MB; extraction supports PDFs up to three pages. Do not approve a receipt just because the reader suggested its amount.

For detailed T59–T78 steps, see [docs/CUSTOMER-WORKFLOW-TESTING.md](docs/CUSTOMER-WORKFLOW-TESTING.md). The shared manual checklist is **Loamy-manual-testing**: ask Mohammed to share it if you cannot open it. Add a **Samuel result** and **Samuel notes** column; leave Mohammed's results and Codex results unchanged. A missing test fixture on your fresh computer is not evidence of a defect.

Copy this result template for each issue or use the equivalent columns in the sheet:

| Test / feature | Commit | Browser + width | Role/location | Steps and fictional inputs | Expected | Actual | Samuel result | Screenshot / error |
|---|---|---|---|---|---|---|---|---|
| Example: partial payment | your commit | Chrome, 1440px | Finance / Lekki | Allocate 750.00 to a 2,000.00 invoice | 1,250.00 remaining | Fill in after testing | Pass / Fail / Blocked / Not run | Attach privately |

Current historical browser results are in [docs/BROWSER-QA-2026-11-12.md](docs/BROWSER-QA-2026-11-12.md), including the corrected cancellation issue. Last recorded outcome: **18 Pass, 0 Fail, 2 Blocked**. The next-day reminder and empty-period PDF/date-entry scenario still need completion; your fresh database needs its own fixtures. Automated results and browser results are separate evidence.

## 6. Optional: enable offline receipt extraction

Most flows work without OCR. For Windows with Docker Desktop running, stop the preview with Ctrl+C, then run:

```powershell
docker build -f Dockerfile.receipt-ocr -t loamy-receipt-ocr:local .
$env:LOAMY_RECEIPT_OCR_DOCKER_IMAGE='loamy-receipt-ocr:local'
$env:LOAMY_MAIL_TRANSPORT='capture'
npm run dev:workspace
```

The reader processes files offline in a restricted container. Alternatively install native Tesseract with English language data and Poppler tools on PATH, following [deploy/ENTERPRISE-RUNBOOK.md](deploy/ENTERPRISE-RUNBOOK.md). Do not treat a missing reader or failed image download as a successful OCR test. Manual receipt submission is still available.

## 7. Optional: run automated checks

Windows, from the repository folder:

```powershell
./.venv/Scripts/python.exe -m unittest test_workspace_features test_workspace_orders test_workspace_invoices test_workspace_payments test_workspace_expenses test_workspace_owner test_workspace_receipts test_workspace_suppliers test_workspace_whatsapp test_workspace_notifications test_workspace_reports test_workspace_pricing test_workspace_location_links test_workspace_customer_workflows -v
$env:VITE_ENTERPRISE_ENABLED='true'
$env:VITE_ENTERPRISE_ONLY='true'
npm run build
Remove-Item Env:VITE_ENTERPRISE_ENABLED
Remove-Item Env:VITE_ENTERPRISE_ONLY
```

On macOS/Linux replace the Python path with `./.venv/bin/python`; build with `VITE_ENTERPRISE_ENABLED=true VITE_ENTERPRISE_ONLY=true npm run build` instead of the PowerShell environment lines. The build checks compilation; restart `npm run dev:workspace` for interactive testing. Tests use temporary databases. The real OCR test is opt-in and may be skipped without its tools/flag; a skipped test is not a pass. Do not enable PostgreSQL test flags against a real database. For the full isolated TLS PostgreSQL/container/restore rehearsal, follow [PRODUCTION-READINESS.md](PRODUCTION-READINESS.md) and the runbook separately.

## 8. Stop, restart, update and troubleshoot

Stop both servers with **Ctrl+C** in the launcher terminal. Restart with `npm run dev:workspace`. Your local business records persist in **`.local-data/workspace.sqlite3`**; downloads are wherever your browser saved them. Neither `.local-data/` nor `.venv/` is shared through Git. Do not commit databases, credentials, invitation/verification links or private evidence.

For an update, first stop the app, check `git status`, and keep a private backup of the local database if those test records matter. With no uncommitted work that would conflict:

```text
git switch mohammeds-branch
git pull --ff-only origin mohammeds-branch
npm ci
```

Rerun the appropriate `.venv` pip-install line from section 2, then restart. If Git reports local changes or a conflict, keep the changes and ask for help rather than discarding them. Never replace an existing upstream database as part of this setup.

| Symptom | What to check |
|---|---|
| `npm` / Python not found, or `npm.ps1` blocked | Reopen terminal after installation. Windows can use `npm.cmd` in place of `npm` when PowerShell blocks its script; do not weaken system-wide execution policy. Verify Node/Python versions. |
| Launcher asks for Python setup | Confirm `.venv/Scripts/python.exe` on Windows or `.venv/bin/python` elsewhere exists in this checkout; repeat section 2. |
| Port 5173/8001 already in use | Stop your earlier Loamy launcher/known process, then retry. Do not change just one port: proxy/origin checks expect this pair. |
| Page loads but API fails | Confirm both servers are still running and open `/business` on `127.0.0.1:5173`, not port 8001 or a LAN address. Read the terminal error. |
| Login does not recognize an existing Loamy account | Business-preview identity is separate. Create a new fictional business account and complete local verification. |
| Real verification email never arrives | Default capture mode sends nothing externally. Use the signed-in account's local inbox. |
| No inbox / SMTP error | Check inherited `LOAMY_MAIL_TRANSPORT`; select `capture` and restart for local testing. |
| Empty dashboard or missing records | Fresh checkout is empty; confirm business/location/date filter and role, then create the fixtures above. |
| Same account in multiple tabs | Tabs share cookies. Use separate profiles or sign out before switching users. |
| OCR unavailable | Enable the optional reader; record extraction as Blocked and continue with manual entry. |
| Reminder says waiting | Check due date and displayed next check. Do not change the computer clock to force a result. |
| Phone cannot open QR/customer link | `127.0.0.1` on a phone means the phone itself. This preview is intentionally computer-only; use a separately configured HTTPS staging host for real-device tests. |

## 9. What this review cannot prove

Local success does not prove real email/WhatsApp arrival, Google/Gmail bank ingestion, production identity/database integration, automatic supplier mailbox ingestion, physical-device behavior or a clean production release. Owner chat is a deterministic recorded-data assistant, not a general AI model. No financial action here transfers real money.

When local acceptance is complete, use [SAMUEL-PRODUCTION-HANDOFF.md](SAMUEL-PRODUCTION-HANDOFF.md) for architecture, migrations 001–006, role boundaries, integrations and remaining release gates. Apply production changes only through the separately reviewed staging/backup/migration process. A clean production container build and live-provider acceptance remain separate gates.

**Validation of this guide:** setup commands, paths, versions and UI labels were checked against the current repository on 13 November 2026. A new machine installation and Samuel's acceptance tests were not run for this documentation-only change; record their actual results when performed.
