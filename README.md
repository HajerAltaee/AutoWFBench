# AutoWFBench

A benchmark engine for replaceable automation workflows. The challenge, environment,
scorecard, solution runtime, and LLM judge have separate responsibilities.

**The engine collects the evidence. The solution does not grade itself.**

Each attempt uses a fresh environment process. The engine combines **environment
events, engine events, candidate output, and protected verification results** into
an immutable `ChallengeSolutionRunLog`. A separate Codex judge service fills the
semantic scorecard. Python computes the score: **yes = 1, maybe = 0.33, no = 0**.

## Try the dashboard

Python 3.11+ on macOS or Linux:

```bash
git clone https://github.com/aleski-green/AutoWFBench.git
cd AutoWFBench
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m autowfbench demo
```

Open **http://127.0.0.1:8080**. Four actual simulator runs are created, including
intentionally incomplete solutions. The judge is **explicitly simulated** and
always awards partial credit for semantic criteria. Demo scores are not LLM
evaluation results. The UI labels these points and can filter them out.

The scatter plot shows **Y = score / 10, X = seconds executing the solution**.
Each dot is one submission, with solution name/version and a linked evidence
inspector. Setup and judging time are excluded. Pending scores are never plotted
as zero. Comparison groups separate challenge/environment/scorecard hashes and
judge configurations; seeds remain visible for matched-case comparisons.

## Run with a real LLM judge

Authenticate the Codex CLI first using your normal setup. In the terminals below,
use the same private `AWB_JUDGE_TOKEN` and choose an available, explicit model ID.

Terminal 1 — independent judge service:

```bash
export AWB_JUDGE_TOKEN='replace-with-a-random-private-token'
export AWB_JUDGE_MODEL='YOUR_AVAILABLE_CODEX_MODEL'
python -m autowfbench judge --port 9100
```

This service actually executes `codex exec --model ... --output-schema ...` in a
fresh read-only judging session. It saves the exact prompt, raw response, execution
events, stderr, hashes, and provenance. No manually supplied score is accepted.

Terminal 2 — example solution API (replace with your own n8n adapter later):

```bash
python -m autowfbench example-solution --port 9201
```

Terminal 3 — engine and UI:

```bash
export AWB_JUDGE_TOKEN='replace-with-a-random-private-token'
python -m autowfbench serve --judge-url http://127.0.0.1:9100
```

Start a run from the UI using the control token printed by the engine. The example
API handles both challenges. Use endpoint `http://127.0.0.1:9201`, runtime
`scripted-reference`, a solution ID, and a version. Or submit from another terminal:

```bash
export AWB_JUDGE_TOKEN='replace-with-a-random-private-token'
python -m autowfbench run crm-lead-qualification \
  benchmark/examples/solutions/crm-reference.json \
  --judge-url http://127.0.0.1:9100
```

For the checkout manifest, either start an example API on port 9202 or change its
endpoint. The CLI and server share the default `runs/` results directory.

Without a judge URL, the engine runs and records deterministic checks but leaves
the total **null / awaiting_llm_judge**. A failed judge never becomes a zero or a
made-up score. `POST /api/runs/{run_id}/rescore` judges the original frozen log
without rerunning the solution; authenticate with the engine control token.

## The challenge packages

| Challenge | Environment | What the workflow must do |
|---|---|---|
| CRM Lead Qualification | Mock customer messages, research, policy, CRM, follow-ups | Gather facts, qualify the lead, recover from a transient CRM failure, update and verify state |
| Production Checkout Recovery | Constrained source-code checkout simulator | Diagnose swapped EUR arguments, apply a small patch, check regression behavior, submit an incident report |

Each challenge directory contains **exactly the three conceptual modules**:
`definition.json`, `environment.json`, `scorecard.json`. The simulator implementation
is in `autowfbench/runtime/environment.py`; its digest is included in the frozen environment
package. These are fresh implementations inspired by the reviewed submissions,
not copied third-party source code.

The checkout example intentionally accepts only a tiny validated source AST. It
does **not** execute arbitrary submitted Python. It is a protocol/evaluation
example, not a full software-repair sandbox. To benchmark unrestricted code repair,
implement a container/VM environment adapter with protected external verifiers.

## Contracts and specialist handoff

- [Architecture and ownership](development/docs/reference/architecture.md)
- [Solution API and tool contract](development/docs/reference/solution-api.md)
- [Run-log specification: what you submit vs what the engine records](development/docs/reference/run-log-spec.md)
- [Judge and scorecard contract](development/docs/reference/judging.md)
- [Operating limits and deployment](development/docs/reference/operations.md)
- [WF-specialist assignment](development/docs/assignment/README.md)
- [Submission checklist](development/docs/assignment/submission-checklist.md)
- [CRM benchmark feedback](development/docs/feedback/crm-lead-qualification.md)
- [Production benchmark feedback](development/docs/feedback/production-checkout-recovery.md)
- [JSON Schemas](benchmark/schemas)

## Repository organization

Three responsibility groups organize the checkout: `autowfbench/` (application),
`benchmark/` (specifications and examples), and `development/` (docs, tests, tools).
See the [rTernarity layout and reduction review](development/docs/reference/refactoring.md)
for the recursive structure, measurements, migration notes, and validation.

## Validation

```bash
python -m unittest discover -s development/tests -v
python -m autowfbench validate-submission benchmark/examples/submission.json
python development/tools/verify_lock.py
```

Tests include actual HTTP solution execution and separate environment processes,
score arithmetic, hostile/malformed submissions, evidence integrity, credential
separation, timeouts, and both challenge outcomes. CI runs on Python 3.11 and 3.12.

## Scope

This is a local development benchmark, not a multi-tenant hosted service. Default
listeners are loopback. Process/state isolation is provided; a separate process
is not a security boundary against hostile code running as the same OS user.
Keep untrusted workflow runtimes on a separate container/host; expose only the
run-scoped tool interface, not benchmark storage or administrative credentials.
See the deployment guide before connecting remote services.
