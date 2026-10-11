# SimSpot customer-discovery MVP

## Boundaries

SimSpot is an AutoWFBench SimApp and the authoritative CRM system of record. It uses
the existing run-scoped SimApp transport: authenticated `GET /apps`, then typed
`POST /apps/{app}/{operation}` calls returning `{ok,value}` or `{ok:false,error}`.
Every benchmark run receives fresh state and is frozen before scoring.

Sapiens4 is the customer-behaviour runtime. On Sapiens4 `main` at `71e93cb`, a
Scheduled Routine is an agent-owned persisted schedule that delivers its saved
objective through the existing Sapiens turn behavior. Its host-control operations are:

- `routines()`
- `routine_create(minutes,prompt)`
- `routine_update(id,minutes,prompt)`
- `routine_pause(id)`
- `routine_resume(id)`

The loopback HTTP API accepts those operations at
`POST /api/agents/<agent-id>/control` with JSON and `X-Sapiens-Local: 1`. A routine
injects its saved objective into its owner Sapi when due. The workflow-authored
objective is therefore the integration boundary; no separate completed-turn relay or
callback is required. The five case fixtures include repeatable Routine objectives,
and AutoWFBench does not copy Sapiens scheduling code.

## MVP flow

1. AutoWFBench starts a fresh `simspot` environment and supplies the workflow with
   its run-scoped URL and bearer token.
2. The workflow reads the inquiry and discovery guide.
3. It searches SimSpot by email/company before selecting a record.
4. It asks the required discovery topics, then performs a separate requirements
   confirmation round. The deterministic customer fixture behaves like the saved
   Sapiens persona prompt without requiring a model call in local tests.
5. It applies the documented route and consent scope, updates the selected contact,
   and reads it back.
6. Only after verified readback does it create and verify one follow-up, then send
   one customer summary.
7. AutoWFBench freezes events/state and evaluates deterministic checks before any
   optional LLM judging.

The case definitions are in
`benchmark/challenges/simspot-customer-discovery/environment.json`. Each contains
starting CRM contacts, the initial and confirmed customer revelations, example
questions, required topics, allowed fields, expected updates, a completion checklist,
and the exact Sapiens routine prompt.

## Windows

Both projects use native loopback HTTP and Python/PowerShell on Windows; WSL is not
required. AutoWFBench now uses a bounded pipe-reader thread on Windows when waiting
for its environment child process because Python's Windows selector accepts sockets,
not `subprocess.PIPE` handles. POSIX keeps the prior selector path.

Local verification:

```powershell
python -m pip install -e .
python -m unittest development.tests.test_simspot -v
python -m unittest discover -s development/tests -v
python development/tools/verify_lock.py
```

In Sapiens4's checkout, the relevant contract tests are:

```powershell
$env:PYTHONUTF8 = '1'
python -m unittest discover -s tests -p 'test_routines.py' -v
python -m unittest tests.test_windows -v
```

The deterministic AutoWFBench fixture deliberately runs without Sapiens/Codex model
calls. It mirrors the same case facts and topic gating so benchmark runs stay
repeatable, while the Sapiens suites verify real Routine scheduling and delivery.
The confirmed responsibility and security boundaries are recorded in
`documentation/sapiens-simspot-integration.md`.

The pinned `docker.n8n.io/n8nio/n8n:2.42.3` image was verified on Windows with
Docker Desktop. A disposable, non-scored workflow ran n8n in Linux, reached a
Windows-hosted SimSpot environment through `host.docker.internal`, authenticated
with a smoke-only run token, read the seeded inquiry and completed its `Submit` node.
No Composer generation, judge, benchmark lock update or scored run was involved.

Docker avoids the direct Windows installation mismatch: `n8n@2.42.3` declares Node
`>=24`, and its `isolated-vm` dependency may require Visual Studio C++ build tools
when installed natively. No
system-wide compiler or unsupported npm workaround was installed.

The full AutoWFBench n8n adapter now supports the pinned image when
`N8N_DOCKER_IMAGE=docker.n8n.io/n8nio/n8n:2.42.3` is set. It creates a fresh mounted
workspace per run, maps host loopback URLs to `host.docker.internal`, preserves log
redaction and removes a named container on cancellation. A non-scored Windows run
completed all five SimSpot cases with every deterministic check passing (8/8 points)
and exactly ten business calls per case. This verifies AutoWFBench -> Docker n8n ->
SimSpot. Sapiens uses the workflow-authored Routine objective; no additional relay is
part of the design.
