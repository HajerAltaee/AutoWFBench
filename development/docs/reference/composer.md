# Black-box workflow Composer

## Purpose

The Composer investigates whether workflow solutions can be generated and improved
autonomously using fixed optimization principles and black-box numeric benchmark
results. It is separate from AutoWFBench's evaluator. It does not read or change a
challenge scorecard, verifier, environment, judge prompt, or benchmark run log.

The current prototype generates a constrained declarative workflow rather than
arbitrary Python. A stable runtime exposes that workflow through Solution API v1.0.
Generated candidates are distinguishable by runtime `composer-declarative-v1` and
are stored with their lineage and content digest.

## Architecture and black-box boundary

```text
public challenge + public tool contracts + fixed principles
                         |
                         v
                  Composer generator
                         |
                 declarative candidate
                         |
                  stable API runtime
                         |
               unchanged benchmark/judge
                         |
              trusted allowlist projection
                         |
 score_0_10 + calls + duration + coarse status + opaque run ID
                         |
                  Composer search
```

The benchmark still owns complete evidence and evaluation. `NumericObservation`
is the only benchmark result passed into Composer search or generation. Its fields
are exactly:

- candidate ID and opaque run ID;
- aggregate `score_0_10` or null;
- objective tool-call count and execution duration;
- coarse completed, timeout, unscored, or failed status;
- public seed number;
- an explicit simulation marker.

The projector discards criterion questions, weights, anchors, per-criterion
answers, judge reasons, evidence references, checks, snapshots, run logs,
`deterministic_points`, fixtures, and judge provenance. The Composer model runs in
a Composer-owned temporary directory and receives no `AWB_*` credentials.

This is a tested information-flow boundary, not complete hostile-code isolation.
For adversarial generated code or hosted evaluation, put Composer and benchmark
services on separate hosts or containers with network and filesystem access
controls.

## Fixed principles

The principles are defined once in `autowfbench/composer/principles.py` and are not
derived from scorecards:

- correctness: preserve public requirements and verify important outputs;
- reliability: reduce failure surface and use bounded recovery;
- efficiency: avoid redundant work and unnecessary calls;
- simplicity: prefer direct, understandable execution paths.

Each child selects one principle as its targeted optimization strategy. Strategy
and hypothesis are saved before evaluation.

## Candidate representation and lifecycle

A candidate JSON document contains a stable ID, challenge ID, version, one
strategy, one hypothesis, ordered steps, and final answer/artifact templates.
Steps may invoke only public challenge capabilities or the safe local operations
`set` and `regex_extract`. References use `{"$ref":"step.value.field"}` and
templates use `${step.value.field}`. There is no dynamic Python or shell execution.

Lifecycle:

1. Generate and validate `c000` from public inputs.
2. Evaluate it with the unchanged benchmark.
3. Project the result into numeric observations.
4. Inspect the current candidate and permitted history using fixed principles.
5. Generate one targeted child.
6. Evaluate and accept or reject it.
7. Continue until the fixed candidate/run budget is exhausted.

Every record includes candidate and parent IDs, candidate digest, strategy,
hypothesis, run observations, aggregate metrics, structural complexity, decision,
and a decision reason based only on permitted information.

## Conservative selection and stopping policy

The initial candidate is the baseline. Children are compared in this order:

1. reject a lower execution completion rate;
2. prefer a meaningfully higher aggregate score;
3. reject a meaningfully lower aggregate score;
4. require repeated measurements before cost-based decisions for equivalent scores;
5. prefer fewer median tool calls;
6. then lower median duration;
7. then lower candidate-owned structural complexity.

Default budget: two candidates, seed 0, and two attempts per candidate. Larger
seed/repetition matrices must be chosen explicitly. The prototype stops when its
candidate budget is exhausted; it does not run an opaque or infinite loop.

## Leakage protections

Tests inject canaries into scorecard-like fields, judge reasons, checks, evidence,
and logs, then verify those canaries do not occur in observations, Composer
prompts, candidate history, generated candidates, or Composer experiment files.
Prompt builders accept public challenge fields and already-sanitized history only.
Candidate schemas reject unexpected fields.

## Running

### Native n8n generation path

The immediate Composer path generates a native n8n workflow directly from the
public challenge with `gpt-6.1-sol`. It validates the JSON and supported n8n
structure, imports it into the pinned n8n 2.42.3 image, and executes it against a
public-contract stub before allowing benchmark execution. Validation failures may
be returned to the model for a bounded repair; benchmark criteria, judge output,
protected checks, and scorecards are never included.

The fixed Solution API adapter contains only benchmark protocol and process
plumbing. It supplies the run-scoped public environment URL and token to the
generated workflow and runs the workflow in the same Linux/Docker topology used
by benchmark solutions. Task-specific decisions and API calls remain in the
generated n8n workflow.

```bash
python -m autowfbench.composer n8n-generate crm-lead-qualification \
  --data-dir composer-runs/native-crm
python -m autowfbench.composer n8n-validate \
  composer-runs/native-crm/workflow.json
python -m autowfbench.composer n8n-benchmark crm-lead-qualification \
  composer-runs/native-crm/workflow.json
```

The preserved CRM experiment is under
`composer-runs/native-crm-sol61-repair2/`. Its final workflow was generated and
repaired without manual workflow edits. Attempts one and two failed deterministic
execution-contract validation; attempt three passed static validation, pinned n8n
import, public-stub execution, and submission-schema validation. The unchanged
artifact digest is
`057c8950d224cb6e611a7859a87a4f7bba0e8191616a19917eb27fd43b2f687b`.
The single completed benchmark run scored 2.33/10 with 11 tool calls in 20.3348
seconds. This demonstrates autonomous native configuration generation and valid
execution, not successful task completion or optimization.

### Official n8n MCP composition strategy

`n8n-mcp-compose` uses Sol with n8n's official instance-level MCP. Before authoring,
Sol records a compact execution plan, maps it to native control-flow primitives,
and states an iteration hypothesis. The bounded runner then records deterministic
validation, pinned-runtime import, execution outcome and duration, structural
complexity, and a runtime-safe failure category.

Repairs are classified as targeted or architectural. They preserve working graph
sections by default, prohibit retry-node unrolling, and must retain provable
termination. Cyclic graphs without a native bounded-loop primitive are rejected.
Large relative graph growth is treated as a regression when it does not advance
execution status; there is no fixed maximum node count. The default limit is three
Composer iterations, after which the experiment stops and preserves its evidence.

```bash
export N8N_MCP_TOKEN='instance-level-mcp-api-key'
python -m autowfbench.composer n8n-mcp-compose crm-lead-qualification \
  --data-dir composer-runs/native-crm-composition --max-iterations 3
```

Benchmark execution is only attempted after the exact exported MCP-authored
workflow completes the public-contract execution check. No validation/runtime
error details beyond the Composer's own artifact are taken from the benchmark,
and benchmark evaluation remains behind the existing numeric-only projection.

The current preserved CRM artifact is the 22-node workflow
`development/solutions/crm/composer-mcp-final/workflow.json`, authored and repaired
through the official instance-level n8n MCP. It passes deterministic validation,
pinned-runtime import, and public-stub execution. Three completed seed-0 runs scored
4.66/10 with 10 tool calls; the most recent completed in 14.8957 seconds. The repeated
score establishes the current baseline rather than a high-quality endpoint.

The public execution trace exposed a simulator-contract problem: deterministic
verification required exact routing values such as `Qualified`, `discovery_call`,
and `sales_coordinator`, while the public policy tool did not publish those values
as a structured contract. The environment now exposes structured capability states,
CRM and follow-up routing, and communication constraints, and rejects conflicting
values at tool-call time. This standardization changes the public environment, so a
future score must be reported separately from the 4.66 baseline after regenerating
the workflow against the new contract.

Run all tests:

```bash
python -m unittest discover -s development/tests -v
python development/tools/verify_lock.py
```

Run the plumbing simulation:

```bash
python -m autowfbench.composer simulate --data-dir composer-runs/simulated
```

The simulation uses invented values and `SIMULATED-*` identifiers and never calls
the benchmark or judge.

For a real run, first start the independent judge as described in the root README.
Then set the same judge token and a pinned Composer model:

```bash
export AWB_JUDGE_TOKEN='private-token'
export AWB_COMPOSER_MODEL='available-model-id'
python -m autowfbench.composer run crm-lead-qualification \
  --judge-url http://127.0.0.1:9100 \
  --data-dir composer-runs/crm-small \
  --benchmark-data-dir runs/composer-crm \
  --iterations 2 --seeds 0 --repeats 2
```

Use the same command with `production-checkout-recovery` for the other challenge.
On Windows, run the protected benchmark under WSL/Linux rather than changing its
locked subprocess startup behavior.

## Reproducibility and limitations

`config.json`, `public-challenge.json`, `principles.json`, each candidate, full
numeric history, content digests, and the final incumbent are retained. Real run
IDs refer to benchmark-owned artifacts outside the Composer directory.

Current limitations:

- AutoWFBench exposes one aggregate score, not public dimension scores.
- Model generation remains stochastic even with fixed prompts.
- Objective duration requires repeated measurements and is only a tie-breaker.
- The declarative language is intentionally small and may need general public
  operations as more challenge types are added.
- Local process separation is not a security boundary against malicious code.
- Simulated evaluation validates plumbing only and is never a performance result.
