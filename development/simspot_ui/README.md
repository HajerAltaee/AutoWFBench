# Experimental SimSpot UI

A local browser reconstruction of a narrow HubSpot contact workflow, based on
sanitized Blindly Windows UIA captures from a test account. It is **not scored
integration, a HubSpot API implementation, or proven same-action parity**.
The existing benchmark SimSpot API remains independent and unchanged.

From the repository root:

```powershell
python -m development.simspot_ui.server --port 8765
```

Open `http://127.0.0.1:8765/`. No external services or dependencies are required
for this native mode.
The default SQLite store is `%LOCALAPPDATA%/AutoWFBench/simspot-ui.sqlite3` on
Windows, or `~/.local/share/AutoWFBench/simspot-ui.sqlite3` elsewhere. Supply
`--store C:/path/to/demo.sqlite3` for a separate persistent workspace. A new path
seeds six fictional contacts; restarting with the same path preserves edits and
activities. Do not place real customer data in this experimental workspace.

## Implemented workflow

1. Use `Create Contact` on Contacts to add a fictional lead with email, first name,
   and last name. New leads start without a company and with lifecycle stage Lead.
2. Open the new lead, edit job title or other identity fields, add a discovery note
   and follow-up task, then refresh or restart and verify the saved information.
   An email already used by another contact is rejected, ignoring case.
3. Search Contacts by name, email, or company. `Aisha` returns two distinct records.
4. Open the Customer record, identified by `simspot.aisha.harbor@example.com`.
5. Use `Edit` to change First Name, Last Name, Job Title, or Email. Save and read back.
6. Use `Create a note` (visible `Note`) and save through `Create note`. Expand
   `Associated with 2 records` and uncheck the company for a contact-only note.
   Saved activity readback reports the actual association count and names.
7. Use `Create a task` (visible `Task`), enter a title/date/description, and `Create`.
   Tasks also support deselecting the company association. The initial time is
   08:00, matching the observed test-account task form.
8. Inspect Activities, refresh, or restart the process and read back saved values.
   The other Aisha record remains separate and unchanged.

`replay-example.json` records one deterministic local edit/note/task sequence.
It is a test fixture, not a claim that the sequence has been replayed in HubSpot.

## Evidence and intentional limits

Observed labels include `Create Contact`, `Email`, `First name`, `Last name`,
`Search ( / )`, `Edit`, `First Name`, `Last Name`,
`Job Title`, `Email`, `Create a note`, `Create a Note`, `Create note`,
`Create a task`, `Enter your task`, `Activity date`, `HH:MM`, `Task Type`,
`Priority`, `Activity assigned to`, `Task Description`, and `Create`.
Names, dates, layout, and values in this implementation use fictional local data.

The identity editor's Save interaction, complete dropdown choices, lifecycle editor,
task defaults, and activity presentation are reconstruction choices; the captures do
not establish complete fidelity. Notes use plain text; formatting, reminders,
recurrence, email sending, meetings, import, arbitrary association editing, and deal
creation are not implemented. Companies are a read-only fixture list. The local
three-business-day task default excludes weekends but not holidays.

## Customer-message and follow-up test seam

The experimental server now supports **inbound customer messages**, kept distinct
from internal notes and tasks. `GET /api/contacts/<id>/messages` returns only those
messages, newest `received_at` first. `POST /api/contacts/<id>/messages` accepts
JSON such as:

```json
{"source_id":"sheet-LEAD-001-message-1","body":"Could you explain the pilot?","received_at":"2026-10-10T07:00:00Z"}
```

`source_id` is stable across replays. Reposting an identical message returns the
existing record without adding an activity; reusing it for different text or time
is rejected. Timestamps must include a timezone and are normalized to UTC. Tasks
may optionally include an `idempotency_key`; reposting the same task and key on
the same contact returns the existing task, while changed task content requires a
new key. Browser write guards still apply to both endpoints.
Neither endpoint sends email or creates an external calendar event.

The [ten-row fictional Google Sheet](https://docs.google.com/spreadsheets/d/1CAMdkTUY8SaaPaeH7ZeI2n-B7TKuLbuhNbfOPUxl4P4/edit)
is today's lead-source fixture. Maya and Aisha already exist in the seeded CRM;
the other eight rows are new emails. The two `fixture_last_customer_message_*`
columns are **bootstrap data**, not the follow-up decision source. A runner must
first import those as inbound CRM messages and then determine 48-hour recency from
the CRM message endpoint. Internal notes and follow-up tasks cannot refresh that
clock. The no-message row must be skipped rather than treated as overdue.

This is a storage/API seam, **not a Google Sheets reader**. The
[mock-source exercise](examples/README.md#ten-lead-mock-source-exercise) now uses
Chief's delegated n8n artifact to import the same ten rows from a local file and
verify follow-ups, persistent state and idempotent replay.
The Codex Google Drive connection does not grant the separate Sapiens runtime
access to the Sheet. That runtime still needs a documented credentialed Sheets
access path (or an authorized browser session) before a 24-hour unattended flow
can be validated. A 24-hour schedule must be owned by Sapiens Routines; do not
substitute a local timer or claim a mock-source run proves live Sheet access.

Five intended company associations are seeded (OrbitOps, Northstar, Harbor,
MedAxis, Quantum). The captured real import instead autoassociated a contact with
example.com; real company setup was still in progress. Local associations therefore
must not be presented as verified real-account equivalence. Email validation is
deliberately narrow, includes the observed `.example` failure, and does not claim to
reproduce HubSpot's complete validation algorithm.

Native mode binds only to 127.0.0.1. Docker mode binds inside its container to
0.0.0.0 but publishes the port only to Windows loopback. Both reject non-loopback
Host headers, require
same-origin Origin and JSON on writes, limits body size, and emits no CORS headers.
There is no authentication: this is for a trusted local fictional-data session.
Content Security Policy blocks external resources and inline scripts; stored text
is rendered as text nodes rather than HTML. SQLite transactions persist writes.

## Verification and future adapter

### Docker on Windows

With Docker Desktop's Linux engine running, first stop any native server using
port 8765, then from this directory run:

```powershell
docker compose up --build -d
```

Visit `http://127.0.0.1:8765/` and follow the new-lead workflow above.
`docker compose down` stops the container; the named volume preserves test data.
The Compose service is an experimental UI server. It has no benchmark state
mapping or token-authenticated service interface. Host and Origin checks are
browser request guards, not authentication. Keep this fictional-data service
local. A Sapiens-authored workflow has now completed a create/read/update/read
flow against this server in Docker on Windows; the
[example and smoke runner](examples/README.md) describe the verified internal
Docker network configuration and retain its evidence. That run did not verify
Compose's published Windows port or connect the UI to scoring.

```powershell
python -m unittest development.tests.test_simspot_ui -v
```

Focused tests cover persistence, search, duplicate preservation, invalid inputs,
HTTP request boundaries, and inert rendering contracts. They do not replace a
browser replay or prove visual parity. No scored benchmark run is required.

`contracts.py` owns validation, `state.py` owns storage and fixtures, and
`server.py` owns HTTP transport; browser assets are under `static/`.
The next narrow integration step is an explicit adapter mapping selected contact
IDs, structured property writes, note bodies, and task outcomes into the benchmark's
run-scoped state and evidence events. It must define consent behavior, activity
associations, UI-versus-business call accounting, and readback verification before
being connected to scoring. The current synthetic customer response implementation
does not gate returned facts by requested topic; this UI makes no such claim.
