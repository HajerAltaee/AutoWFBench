# Sapiens-authored local lead workflow

`sapiens-lead-flow.json` is a native n8n development artifact authored by the
`N8nComposer` Sapi after Chief created that specialist and delegated a task through
the Sapiens CLI. The parent operator supplies input and runs the artifact using
AutoWFBench's existing `N8nRuntime`. The production Composer's generation command
and the scored challenge remain separate from this local proof.

The flow creates a fictional contact, reads and verifies it, updates its job title
and lifecycle stage, then reads and verifies the saved record before submitting
its result. Lead values come from runtime input. The server supplies the contact
ID. HTTP or comparison failures stop execution; writes are not retried because
the UI API has no idempotency-key contract.

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
