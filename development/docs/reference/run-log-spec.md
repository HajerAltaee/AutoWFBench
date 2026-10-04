# ChallengeSolutionRunLog v1.0 — evidence contract

## The most important requirement

**A workflow must never author the authoritative `ChallengeSolutionRunLog`.**

The engine assembles it from four separately identified sources:

1. **Environment evidence:** tool calls, arguments, observed results, failures,
   and resulting state, collected by the benchmark-owned environment.
2. **Engine evidence:** start/end observations, enforced deadline, lifecycle,
   termination reason, and measured duration.
3. **Candidate evidence:** final answer, generated artifacts, optional reported
   workflow trace. These remain candidate claims even if they look like tool logs.
4. **Verification evidence:** protected before/after state checks and test results.

The judge cannot treat a candidate's “CRM updated” line as proof of an update.
The state snapshot and environment event must support it. Likewise, a candidate
cannot manufacture `verification` events by putting that word in its trace.

## What WF-specialists implement

Your side implements the solution API and returns a **SolutionSubmission**. This
is the candidate portion of the final log, not the full log. Its exact contract is
[`benchmark/schemas/submission.schema.json`](../../../benchmark/schemas/submission.schema.json).

```json
{
  "protocol_version": "1.0",
  "run_id": "run-IDENTIFIER-FROM-ENGINE",
  "status": "completed",
  "final_answer": "The temporary CRM failure was retried. Readback confirms ...",
  "artifacts": [
    {
      "name": "resolution.md",
      "media_type": "text/markdown",
      "content": "# Result\nObserved state and remaining actions ..."
    }
  ],
  "trace": [
    {
      "timestamp": "2026-10-04T12:00:00+00:00",
      "kind": "workflow_step",
      "data": {
        "step_id": "verify-crm",
        "actor": "sales-coordinator",
        "operation": "crm.read",
        "outcome": "succeeded"
      }
    }
  ]
}
```

All top-level fields are required. `artifacts` and `trace` may be empty. `status`
is `completed` or `failed`; completion is not a claim of benchmark success.
`final_answer` must describe the actual outcome and unresolved work. Do not include
hidden chain of thought; concise decisions, evidence pointers, and tool observations
are sufficient. Candidate timestamps are self-reported and never set the chart's X value.

Artifacts are inline text, at most 20 artifacts and 200,000 characters each, within
the overall 2 MB HTTP response limit. Binary/remote artifact fetching is intentionally
unsupported. Store external artifacts in your own system and describe them, but
do not expect unsubmitted evidence to be graded. Limit trace to 1,000 entries.
Never submit secrets, credentials, personal data beyond the synthetic fixture,
scores, or authoritative evidence fields.

Validate locally:

```bash
python -m autowfbench validate-submission benchmark/examples/submission.json
```

## What the engine creates

The canonical contract is [`benchmark/schemas/run-log.schema.json`](../../../benchmark/schemas/run-log.schema.json).
An executable example generated from a real reference run is in
[`benchmark/examples/run-log.json`](../../../benchmark/examples/run-log.json).

| Field | Owner / meaning |
|---|---|
| `schema_version`, `run_id` | Engine protocol version and unique attempt ID |
| `challenge` | ID/version and frozen definition, environment, scorecard digests |
| `solution` | Registration ID/name/version/runtime and manifest digest |
| `seed` | Benchmark-assigned case seed |
| `started_at`, `finished_at` | Engine-observed UTC timestamps |
| `duration_seconds` | Monotonic time from starting the solution API call to terminal receipt/deadline |
| `termination_reason` | completed, solution_failed, timeout, protocol_error, or engine_error |
| `events` | Evidence records with provenance assigned by trusted collector |
| `snapshots.initial`, `snapshots.final` | State collected directly from environment |
| `checks` | Protected verifier booleans |
| `submission` | Validated candidate envelope, or null if none was received |

Environment provisioning and judge time are excluded from execution duration.
Polling and transport overhead are included. Use consistent transport for timed
comparisons. The engine never uses candidate-reported duration for rankings.

Every event has:

```json
{
  "id": "env-0012",
  "source": "environment",
  "timestamp": "2026-10-04T12:00:00+00:00",
  "kind": "tool_call",
  "data": {
    "operation": "crm.update",
    "arguments": {"changes": {"status": "Qualified"}},
    "result": {
      "ok": false,
      "error": {
        "code": "CRM_TEMPORARILY_UNAVAILABLE",
        "message": "Retry this operation",
        "retryable": true
      }
    }
  }
}
```

IDs are unique within the run. Sources are exactly `engine`, `environment`,
`candidate`, `verification`. Events are collected by source; the array is **not a
global chronological sequence**. Environment event order is authoritative for tool
ordering. Candidate trace timestamps are nested in `data`; receipt timestamps are
assigned by the engine. Judge evidence references must name existing event IDs.

## Persistence, integrity, and failure semantics

Each run directory contains `package.json`, `solution.json`, `run-log.json`,
`scorecard-result.json`, `result.json`, and zero or more `judgement-*.json` records.
The run log is frozen before judging and its digest is checked on rescore. Stored
package hashes include the simulator implementation digest. This detects accidental
tampering; it is not a cryptographic attestation against the benchmark host owner.

If a workflow fails or times out, environment evidence is frozen and retained.
If the environment cannot be collected, the attempt is `engine_error` and cannot
receive a valid score. A model failure gives `judge_failed` with a null score.
Missing telemetry is not “maybe.” A complete trace proving omitted work can support
“no.” Keep partial credit distinct from incomplete evidence.

Run and administration credentials are redacted from collected logs. Specialists
are still responsible for avoiding unrelated secret values in submitted text.
