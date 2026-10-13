# Sapiens-authored local lead workflow

`sapiens-lead-flow.json` is a native n8n development artifact authored by the
`N8nComposer` Sapi after Chief created that specialist and delegated a task through
the Sapiens CLI. The parent operator supplies input and runs the artifact using
AutoWFBench's existing `N8nRuntime`. The production Composer's generation command
and the scored challenge remain separate from this local proof.

The flow creates a fictional contact, reads and verifies it, updates its job title
and lifecycle stage, then reads and verifies the saved record before submitting
its result. Lead values come from runtime input. The server supplies the contact
ID. HTTP or comparison failures stop execution; writes are not automatically
retried. Message and task replay keys are available in the newer mock flow below.

## Authoring through Chief

Start a Sapiens host using its documented Windows source startup or desktop app.
For a dedicated test workspace, from the Sapiens checkout:

```powershell
python -m sapiens --port 4174 --data-dir ../runtime-tools/sapiens-composer
```

In another terminal in that checkout:

```powershell
python sapiens4 status --url http://127.0.0.1:4174 --format json
python sapiens4 show --url http://127.0.0.1:4174 --format json
python sapiens4 chat 'Select or create an n8n Composer specialist and delegate the SimSpot lead workflow task described in the supplied repository and output path.' --sapi chief --url http://127.0.0.1:4174
```

Supply the absolute repository and output paths, this objective, and the exact
public contracts from `server.py`, `contracts.py`, and the contact return shape in
`state.py`. Successful create/read/update responses are the contact object
directly, with `contact_id`; there is no `id` alias or `contact`/`data` wrapper.
Restrict specialist writes to the workflow artifact and let the parent own live
execution. Then use `conversation watch <accepted-turn-id> --sapi chief` to observe
the delegated task. An accepted turn is not proof of a completed workflow.

Only Chief creates Sapis. No separate agent-creation CLI command is required.
The workflow's Context node is populated by the runner with `run_id`,
`environment.base_url`, `limits`, `ui_origin`, `lead`, and `updates`. The existing
runner also supplies an unused token placeholder; it is not sent to this UI API
or included in the submission.

## Run on Windows with Docker Desktop

From the AutoWFBench repository root, with the Linux Docker engine running:

```powershell
docker build -t autowfbench-simspot-ui:local development/simspot_ui
python -m development.tools.smoke_simspot_sapiens
```

The smoke runner reuses pinned n8n 2.42.3, starts a fresh SimSpot container on a
private internal Docker network, without publishing any host port. A separate
HTTP client inside the server container reads the before/after state. Trusted HTTP
nodes send the server's expected Host and Origin values while connecting through
the private Docker service name. These headers are browser request guards, not
authentication. This setup is only for local fictional test data.

The runner independently checks that exactly one matching lead was added, the
requested field values were saved, and the original contacts remain unchanged.
`runs/sapiens-ui-<id>/` retains the submission, before/after CRM snapshots, n8n
logs/timings, workflow digest, and a summary of those checks. Temporary containers
and their network are removed after the run. The native demo's database is not
used. No judge or scored benchmark is invoked.

This artifact uses the UI's GET/POST/PATCH API, so it does not pass through the
production graph compiler, which targets authenticated benchmark POST operations.
There is no new Sapiens callback or public relay interface. This demonstrates
CLI orchestration, real workflow authoring, and local execution. The optional
Composer provider adapter is documented in
`documentation/sapiens-simspot-integration.md`; it authors typed graphs for the
benchmark API and does not connect this UI database to benchmark state.

## Ten-lead mock-source exercise

`sapiens-mock-leads-flow.json` was authored by N8nComposer after Chief delegated
the business objective in `mock-authoring.md`. `mock-plan.md` records its plan.
The parent operator made two transport-only corrections after review: a bounded
GET/POST/PATCH expression and literal `sendBody: true`. n8n import dropped the
JSON body when `sendBody` was an expression. Business decisions remain in the
specialist-authored workflow, not the harness.

```powershell
docker build -t autowfbench-simspot-ui:local development/simspot_ui
python -m development.tools.smoke_sapiens_mock_leads
python -m unittest development.tests.test_mock_leads development.tests.test_simspot_ui -q
```

The default clock comes from `mock-leads.json`, making the baseline reproducible:
ten rows, two existing matches, eight new contacts, six overdue follow-ups, three
recent messages and one no-message lead. Four unrelated seeded contacts are left
untouched, so the final CRM contains fourteen contacts. Company/context is stored
in contact-only notes; this flow does not create company associations. Follow-up
text is a template incorporating the latest inbound message and discovery context,
not a new model-generated conversation during each execution.

The runner executes twice and restarts the server in between. Independent HTTP
readback checks stored values, task selection and exact repeat-state equality.
The source snapshot, per-lead submission artifact, n8n logs and independent checks
are retained in `runs/sapiens-mock-workspace/sapiens-mock-<id>/`. The persistent
SQLite file is `runs/sapiens-mock-workspace/state/mock.sqlite3`. This is separate
from the browser demo database. Containers/networks are temporary and expose no
Windows port; a workspace lock rejects overlapping runs.

Use `--workspace <new-directory>` for a fresh fixture, `--repeat 1` for one cycle,
`--now <timezone-aware-ISO-time>` for a boundary check, or `--current-time` for a
real-clock occurrence. Do not move the clock backwards in a populated workspace:
historical tasks are retained. This narrow oracle assumes the fixed ten-row source;
reply-after-follow-up cancellation, completed-task reopening, changing source rows,
and new-message follow-up lifecycles are not covered.

### Sapiens-owned recurrence

After verifying the flow, use the existing Sapiens CLI Scheduled Routine template
in Chief's conversation (replace the checkout path for the local installation):

```text
Add New Scheduled Routine:
Frequency: every 1440 minutes
Execute: Coordinate one local mock lead-import and follow-up cycle in <absolute AutoWFBench checkout>. Select an appropriate Sapi to run python -m development.tools.smoke_sapiens_mock_leads --current-time --repeat 1 from that checkout, using the existing persistent workspace. Inspect the generated summary and report actual failures or CRM changes. Do not rewrite the workflow, reset state, send emails, change Sheet sharing or run scored benchmarks. If Docker or the provider is unavailable, report the blocker without repeated retries.
```

This schedules a prompt for Chief; it is not a permanently running n8n service.
Pin the absolute Python interpreter path in the installed routine after checking
that it imports `fastjsonschema` and the checkout. The specialist's default
`python` may differ from the operator terminal's interpreter on Windows. Install
project dependencies into a chosen environment beforehand; do not silently
install packages or substitute interpreters during a scheduled occurrence.
The Windows machine must be awake, Docker Desktop's Linux engine running, and the
Sapiens host/provider available. Routine creation is not proof that a 24-hour
occurrence has executed. Pause via `Pause Scheduled Routine:` followed on the next
line by `@routine_sch_<id>`, sent through `python sapiens4 chat ... --sapi chief`.

This mock stage does not read Google Sheets. Connecting and verifying all ten live
Sheet rows is the next stage. There is no scored benchmark or UI-to-benchmark state
adapter in this exercise.

The Oct 13 Windows test registered Chief-owned `routine_sch_00001` at 1440 minutes,
first due Oct 14 at 10:52 UTC (14:52 Dubai). Its registered run count was zero.
The separately requested real-clock run **was** executed by N8nComposer under
Chief's delegation: zero new contacts and one newly overdue task for Sofia,
bringing the total to seven tasks. See `mock-verification.json` for turn IDs,
digests, tested outcomes and the two resolved execution failures. Routine IDs are
local to that test Sapiens workspace, not portable configuration.
