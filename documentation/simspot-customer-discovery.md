# SimSpot customer-discovery MVP

## Boundaries

SimSpot is an AutoWFBench SimApp and the authoritative CRM system of record. It uses
the existing run-scoped SimApp transport: authenticated `GET /apps`, then typed
`POST /apps/{app}/{operation}` calls returning `{ok,value}` or `{ok:false,error}`.
Every benchmark run receives fresh state and is frozen before scoring.

Sapiens4 is the customer-behaviour runtime. On Sapiens4 `main` at `71e93cb`, a
Scheduled Routine is an agent-owned persisted schedule, not a webhook or simulator
callback. Its existing host-control operations are:

- `routines()`
- `routine_create(minutes,prompt)`
- `routine_update(id,minutes,prompt)`
- `routine_pause(id)`
- `routine_resume(id)`

The loopback HTTP API accepts those operations at
`POST /api/agents/<agent-id>/control` with JSON and `X-Sapiens-Local: 1`. A routine
injects its saved prompt into its owner Sapi when due. The five case fixtures include
repeatable routine prompts, but AutoWFBench does not copy Sapiens scheduling code or
invent a callback API.

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
calls. A live end-to-end customer Sapi still needs an owner decision about the bridge:
either the Sapi directly calls authenticated SimSpot operations during a benchmark
run, or an adapter relays Sapiens turn output into `customer.ask`. Sapiens currently
documents neither a routine callback nor a stable customer-response adapter, so this
MVP does not fabricate one.

The uncommitted design options and security constraints are recorded in
`documentation/sapiens-simspot-relay-proposal.md`.

The pinned `docker.n8n.io/n8nio/n8n:2.42.3` image was verified on Windows with
Docker Desktop. A disposable, non-scored workflow ran n8n in Linux, reached a
Windows-hosted SimSpot environment through `host.docker.internal`, authenticated
with a smoke-only run token, read the seeded inquiry and completed its `Submit` node.
No Composer generation, judge, benchmark lock update or scored run was involved.

Docker avoids the direct Windows installation mismatch: `n8n@2.42.3` declares Node
`>=24`, while this repository's README currently says Node 22, and its `isolated-vm`
dependency may require Visual Studio C++ build tools when installed natively. No
system-wide compiler or unsupported npm workaround was installed. A full benchmark
runner still needs an agreed Docker wrapper for mapping per-run files and rewriting
the environment URL from host loopback to `host.docker.internal`; the smoke test
proves the container-to-SimSpot transport, not the still-unapproved live Sapiens
relay.
