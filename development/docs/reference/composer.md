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
