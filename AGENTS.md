# Loamy repository working instructions

## Maintain Samuel's handoff

`SAMUEL-PRODUCTION-HANDOFF.md` is the living handoff for Samuel, his team and their AI agents.

After a meaningful feature, behavior, schema, integration, configuration or deployment change, update the relevant handoff sections before finishing the task. Record the date, current scope, source/migration/configuration changes, actual checks/results/skips, remaining work and release gates.

Distinguish local fixtures, production rehearsal, real staging and live production. Do not mark planned work as implemented or treat historical tests as newly run. Never put secrets, live customer data, raw bank emails, receipts or credentials in the handoff. Keep paths repository-relative inside it.

Read the current implementation and applicable runtime/deployment documentation before modifying it. Preserve the separation between the guarded local preview and production entry point, business/location authorization, exact money, canonical-ledger uniqueness and immutable financial/evidence history. A handoff or passing rehearsal is not authority to overwrite an existing database or claim a live deployment.

## Publish completed work to the development fork

The user has requested publication of completed feature work to their fork's `mohammeds-branch`. For this ongoing work, update the handoff, run appropriate checks, commit with a clear feature/validation description, and push to `origin` only after verifying it is `https://github.com/Mastermoh0/Loamy.git` and the current branch is `mohammeds-branch`.

Verify the remote branch SHA after pushing and report whether publication succeeded. Do not imply that local edits are already on GitHub. Do not publish secrets/test databases, force-push, change Samuel's main branch, merge a PR or deploy as part of this instruction. If authentication or an unexpected remote change blocks publication, preserve the work and explain the concrete blocker.
