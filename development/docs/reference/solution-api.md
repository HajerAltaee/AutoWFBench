# Solution API v1.0

An n8n workflow export alone is not an execution API. Supply a small adapter that
accepts a run request, invokes the workflow, tracks completion, and returns the
submission. The adapter may be implemented with n8n webhooks plus durable state or
a separate HTTP service. The provided Python example is a reference for the protocol.

## Manifest

See `benchmark/schemas/solution.schema.json` and `benchmark/examples/solutions/`. Required fields:
`id`, `name`, `version`, `endpoint`, `runtime`, `description`, `auth_env`.
Use an empty `auth_env` for an unauthenticated local example. Otherwise it names
an environment variable on the engine containing the bearer token for your API.
Never embed a secret in the manifest or workflow export.

## Start

`POST {solution.endpoint}/runs`

```json
{
  "protocol_version": "1.0",
  "run_id": "run-example",
  "challenge": {
    "id": "crm-lead-qualification",
    "version": "1.0.0",
    "name": "CRM Lead Qualification",
    "task": "...",
    "capabilities": ["inquiry.read", "crm.update"],
    "limits": {"wall_clock_seconds": 120, "tool_calls": 40},
    "completion": "..."
  },
  "environment": {
    "base_url": "http://127.0.0.1:49152",
    "access_token": "RUN_SCOPED_SECRET"
  },
  "limits": {"wall_clock_seconds": 120, "tool_calls": 40}
}
```

Return promptly (within 15 seconds) with HTTP 202 and
`{"execution_id":"your-unique-id","status":"running"}`. Start work asynchronously.
Treat `run_id` as an idempotency key in a production adapter. Keep concurrent runs'
inputs and environment credentials separate. Do not reuse prior run state.

## Observe and finish

`GET {solution.endpoint}/runs/{execution_id}` returns:

- `{"status":"queued"}` or `{"status":"running"}` while active;
- `{"status":"completed","submission":{...}}` when finished;
- `{"status":"failed","submission":{...}}` when execution failed.

The terminal status and `submission.status` must agree. Both return the original
benchmark `run_id`. The engine records terminal receipt time, not a claimed finish
timestamp. Polling adds up to roughly 0.15 seconds plus transport overhead.

`POST /runs/{execution_id}/cancel` requests termination. Stop your workflow and its
background jobs. Even if cancellation fails, the frozen environment rejects further
actions. The engine cannot kill arbitrary processes on a remote solution host.

## Environment tools

Call `POST {environment.base_url}/tools` with bearer `access_token` and:

```json
{"operation":"crm.read","arguments":{}}
```

Success: `{"ok":true,"value":{...}}`.
Failure: `{"ok":false,"error":{"code":"...","message":"...","retryable":true}}`.
Tool failures use HTTP 200 so the workflow can inspect and react to the observation.
Authentication/protocol failures use HTTP error codes.

### CRM Lead Qualification

| Operation | Arguments | Result |
|---|---|---|
| `inquiry.read` | `{}` | Customer inquiry, lead ID, authorized contact |
| `documents.read` | `{}` | Service capabilities, qualification and communication policies |
| `research.read` | `{}` | Company profile and contact authority |
| `customer.ask` | `{"questions":["..."]}` | Customer qualification facts; outbound question and inbound reply recorded |
| `crm.read` | `{}` | Current lead snapshot |
| `crm.update` | `{"changes":{...}}` | Updated lead, or retryable injected failure |
| `followup.create` | `{"lead_id":"...","type":"discovery_call","status":"pending_scheduling"}` | Created follow-up ID |
| `customer.send` | `{"recipient":"...","body":"..."}` | Recorded final customer message |

Writable CRM fields: `status`, `budget_aed`, `timeline_weeks`, `volume`, `languages`,
`crm`, `channel`, `human_handoff`, `next_action`, `owner`. Use facts observed in the
run; seed changes budget and volume. Protected identity fields cannot be changed.
The mock customer returns a fixed fact set when asked; semantic assessment judges
the relevance of the questions. This is not a generative customer simulator.

### Production Checkout Recovery

| Operation | Arguments | Result |
|---|---|---|
| `incident.read` | `{}` | Failed orders, deployment evidence, patch restrictions |
| `source.read` | `{}` | `checkout.py` content |
| `checkout.patch` | `{"old":"exact existing fragment","new":"replacement"}` | Patch result; old fragment must occur exactly once |
| `tests.run` | `{}` | Actual public simulator test results |

Submit `incident-summary.md` as an inline artifact. The source grammar permits one
`checkout(amount,currency)` function, an optional EUR/USD branch, and return calls
to `charge_card` using input variable arguments. Imports and arbitrary execution
are rejected. Protected verification also checks different values after the run.

## n8n wiring

Use a start webhook → save run request → respond with execution ID → invoke your
workflow. Pass environment URL/token through per-run context. Every business tool
call uses that environment. Save terminal submission in adapter state and expose
it through a status webhook. Avoid global static workflow variables for concurrent
runs. Environment/scorecard initialization and judging must not be candidate nodes.

The solution is free to implement one agent, several agents, deterministic steps,
or a hybrid. Its internal choices must not require benchmark-engine changes.
