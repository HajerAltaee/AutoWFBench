# Local lead-import and follow-up authoring contract

This development exercise uses `mock-leads.json` in place of the live Google Sheet.
Chief owns the plan and delegation. The parent test harness supplies inputs, runs
the authored artifact, and independently reads CRM state; it does not implement
the workflow's import or follow-up decisions.

## Business objective

Import the ten fictional leads, matching existing contacts by case-insensitive
email. Preserve existing identities, lifecycle stages and company associations;
update their job titles from the source. Keep each source's company and discovery
context in one contact-only note without duplicates. Bootstrap supplied customer
message fixtures as inbound messages, then use actual CRM message history for
follow-up decisions. Only a last inbound customer message older than 48 hours is
overdue. Exactly 48 hours, recent messages, and no customer message are skipped.
Schedule a personalized follow-up task for overdue contacts, without duplicates
on later runs. Task text should address the latest customer's topic and use their
name and available CRM context. Do not send emails. Preserve unrelated contacts.

The task describes a future 24-hour recurring run; first deliver one executable
flow and verify a repeat against the same persistent CRM. Chief chooses the
specialists and plan. The source fixture does not contain workflow instructions.

## Existing public app contracts

Read `../server.py`, `../contracts.py`, and `../state.py` for authoritative details.
The local experimental server returns contacts and activities directly, with
`contact_id` and `activity_id`. It does not return an `id` alias or a data wrapper.
Use GET `/api/contacts`, POST `/api/contacts`, PATCH `/api/contacts/<contact_id>`,
GET `/api/contacts/<contact_id>/activities`, GET/POST
`/api/contacts/<contact_id>/messages`, POST `/notes`, and POST `/tasks` on the same
contact. Message `source_id` and task `idempotency_key` must remain stable on replay.
Tasks with a reused key but changed content are rejected; read existing tasks
before creating another on a later day. Notes have no key; compare existing notes.
There is no arbitrary company-association write endpoint.

## Existing n8n execution contract

Produce `sapiens-mock-leads-flow.json` here, native n8n 2.42.3 JSON. Use the existing
`sapiens-lead-flow.json` and `../../tools/smoke_simspot_sapiens.py` as runtime examples.
The Start manual trigger feeds Context (Set v3.4). The harness replaces Context
with this request:

```
{run_id, environment:{base_url,access_token}, limits:{wall_clock_seconds},
 ui_origin, now, source:{source_name,leads:[...rows from mock-leads.json...]}}
```

`now` is an ISO timestamp supplied by the harness. Use it for the strict 48-hour
comparison and scheduling date; no wall-clock or fixed dates inside the artifact.
The source file's `as_of` is used only as a reproducible default by the harness.
All HTTP nodes use `Context.environment.base_url` plus the documented contacts
path. For Docker, send Host equal to `Context.ui_origin` without `http://` and
Origin equal to `Context.ui_origin`; writes use JSON. The unused access_token
placeholder must not be copied to outputs or transmitted to this app.

Use native HTTP Request nodes for I/O. Code nodes transform their inputs only;
no filesystem, network helpers, credentials, environment reads, or shell calls.
Use supported built-in nodes, no automatic retries or error continuation.
HTTP errors and mismatched readbacks must stop execution.

Submit is terminal and emits one submission matching
`../../../benchmark/schemas/submission.schema.json`: protocol_version `1.0`,
run_id, status, final_answer, artifacts and trace. Include per-lead outcomes and
CRM IDs in an artifact and trace enough decisions for review. Preserve a path to
Submit when all contacts/messages/tasks already exist and no writes are needed.

Only author the workflow and `mock-plan.md` in this examples directory. The parent
owns fixtures, harness, app code, tests, live execution and git. Do not edit other
files, run Docker, create a live recurring schedule or perform scored attempts
during authoring. Other concurrent repository edits belong to the parent.
