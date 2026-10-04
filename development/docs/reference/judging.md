# Independent judging and score calculation

The engine sends `definition`, `run_log`, and `scorecard` to `POST /evaluate` on a
separate judge service. Authenticate using the benchmark-only `AWB_JUDGE_TOKEN`.
The candidate must not know that token or invoke this API.

## Real execution

Default mode is `codex`, requiring a pinned model. Each evaluation starts a fresh
`codex exec` with a strict output schema, read-only sandbox, prompt through stdin,
and a service-owned output directory. It does not resume the candidate's session.
The exact prompt, JSONL execution events, stderr, response, model selection, and
digests are preserved under the judge data directory. A nonzero exit, timeout,
missing output, schema error, wrong run ID, unknown evidence reference, duplicate
criterion, or incomplete complete-response is a failed evaluation.

The service gives candidate text no instructional authority and omits solution
identity metadata from the prompt. Read-only CLI mode is not complete host
isolation; use a dedicated judge account/container for untrusted hosted evaluation.

## Scorecard answers

Every criterion defines yes/maybe/no anchors, weight, required evidence source,
and evaluator type. **Maybe = 0.33**, meaning partial satisfaction. It is never a
substitute for absent telemetry or evaluator uncertainty.

`deterministic` criteria come directly from protected environment verification.
The LLM returns only `llm` criteria; it cannot alter a verified state check.
Every returned answer includes a short reason and existing event IDs. The
validator checks response shape, IDs, completeness, and references. It cannot
guarantee that a model's interpretation is substantively correct; calibrate against
human-reviewed good/bad benchmark/examples before treating rankings as dependable.

```text
criterion_points = weight × {yes: 1, maybe: 0.33, no: 0}
score_0_10 = 10 × sum(criterion_points) / sum(weights)
```

Decimal arithmetic is used; rounding occurs only after aggregation to two decimals.
All provided scorecards sum to ten. A weight of 2 with “maybe” earns 0.66 points.
A missing answer never gets an implicit zero. No API accepts `judge_score` or a
candidate-supplied total. Python computes all numeric scores.

The report separately exposes `execution_pass`: every deterministic check passed
and the candidate completed normally. High communication scores cannot change a
failed execution into a successful one. No hidden score caps are introduced.

## Demo mode

`--mode demo` exists for smoke development/tests and UI demonstrations. It returns explicit
simulated partial credit, model `SIMULATED`, and provenance `mode=demo`. Its results
are excluded when the UI selects “Real Codex judge only.” Never report them as
LLM-as-a-Judge outcomes. The reference solution runtime is independently labelled
`scripted-reference`; a real judge scoring it still does not make it an AI solution.

## Reproducibility

Pin challenge, scorecard, environment implementation, model, judge prompt version,
and seed schedule. Judge stochasticity means one rating is not a confidence
interval. For formal comparison, specify repetitions and aggregation before running;
retain all attempts and judge responses. Do not choose only favorable rescoring
results. The starter UI deliberately displays per-run results without claiming
statistical significance.
