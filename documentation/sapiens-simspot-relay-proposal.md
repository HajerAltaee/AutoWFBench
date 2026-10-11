# Sapiens-to-SimSpot relay proposal

Status: design draft; no new public interface is approved or implemented.

## Why a relay

Sapiens4 Scheduled Routines persist an owner, interval and execution prompt, then
inject that prompt into the owner's chat when due. The documented Sapiens contract
does not provide a routine callback that emits a structured customer reply to an
external simulator. AutoWFBench, meanwhile, gives each run a short-lived SimApp URL
and bearer token. Putting that token in a persona prompt would expose benchmark
credentials to the model and its transcript.

A local relay can hold the run credential, correlate one Sapiens turn with one
AutoWFBench discovery round, validate the returned customer facts, and call SimSpot.
The customer Sapi sees the case/persona and requested topics, but never the SimSpot
token or evaluator state.

## Existing contracts retained

- Sapiens routine ownership and scheduling continue to use `routines`,
  `routine_create`, `routine_update`, `routine_pause` and `routine_resume`.
- Sapiens writes continue to use loopback JSON with `X-Sapiens-Local: 1`.
- AutoWFBench continues to expose only `GET /apps` and authenticated typed
  `POST /apps/{app}/{operation}` calls to a run.
- SimSpot remains the authoritative CRM state; Sapiens does not grade itself or
  write evaluator state.

## Proposed responsibilities

The relay would:

1. Receive a run ID, case ID, Sapi ID and requested discovery topics from the local
   harness, not from the generated workflow.
2. Submit a customer-persona turn through a supported Sapiens message mechanism.
3. Wait with a bounded deadline for that exact turn to complete.
4. Convert the response into the already documented `customer.ask` result schema.
5. Reject unknown fields, invented topics, mismatched case/turn IDs and responses
   arriving after the run is frozen.
6. Forward the validated result to the run-scoped SimSpot environment while keeping
   its bearer token only in relay memory.
7. Record correlation IDs and outcome codes, with credentials redacted.

The relay would not schedule its own jobs, edit Sapiens persistence, expose AutoWFBench
admin finalization, retry non-retryable failures, or treat free-form prose as verified
CRM state.

## Owner decision required

Sapiens must designate a supported way to retrieve the completed result for one
submitted turn. The current `GET /api/state` projection may be suitable for UI state,
but this draft does not assume that it is a stable integration contract. The owner
should choose either:

- an explicitly supported completed-turn read contract; or
- an explicitly supported loopback callback from Sapiens to the relay.

Only after that choice should route names, request fields and response envelopes be
versioned in code.

## Security and privacy rules

- Bind relay, Sapiens and SimSpot to loopback by default.
- Never place bearer tokens, authorization headers or evaluator data in Routine
  prompts, chat history, artifacts or logs.
- Allowlist case IDs and discovery topics from the active challenge package.
- Carry only the consent-approved structured facts into SimSpot.
- Use one opaque correlation ID per discovery round and one bounded wait.
- Do not replay a completed Sapiens response into a different run.
- Redact secrets recursively using the benchmark's existing redaction behavior.

## Windows verification plan

1. Start Sapiens4 with its native PowerShell entry point and an empty temporary data
   directory.
2. Start an AutoWFBench SimSpot environment on loopback.
3. Create or inspect a customer Sapi's Routine using the existing host-control API.
4. Run one initial discovery round and one separate requirements-confirmation round.
5. Verify the relay never writes a token to the Sapiens data directory or captured
   request/response logs.
6. Freeze the AutoWFBench run and confirm late relay delivery is rejected.
7. Repeat the duplicate, summary-only privacy and changed-requirements cases.
8. Stop both native processes and verify no child process remains.

Unit tests should use deterministic Sapiens turn fixtures. A real model-backed smoke
test should be optional, unscored and run only after the interface is approved.
