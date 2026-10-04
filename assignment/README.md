# Assignment for AI automation specialists

Build an independently runnable workflow solution for your assigned challenge:
**CRM Lead Qualification** or **Production Checkout Recovery**. Demonstrate that
the same unmodified benchmark engine can execute and score each version.

## Deliverables

1. A complete n8n workflow export (or agreed alternative runtime) plus a portable
   setup guide, runtime version, dependency list, and credential configuration.
2. A solution API implementing start, status/result, and cancellation. Supply a
   manifest with stable solution ID, name, explicit version, runtime, and endpoint.
3. A valid `SolutionSubmission` for every completed or failed attempt. Include
   the final answer, required artifacts, and useful reported workflow trace.
4. **A baseline and at least three distinct improvements: four versioned submissions
   minimum.** These are improvements to your workflow solution, not edits to the
   benchmark or scoring rules.
5. An experiment report with hypotheses, changes, all run IDs, scores, execution
   times, failure rates, evidence, regressions, and limitations.

## Required evaluation plan

- Use baseline `0.1.0`, then three documented versions such as `0.2.0`, `0.3.0`, `0.4.0`.
- For each version run seeds **0, 1, and 2**, with **three attempts per seed**:
  **nine attempts per version, at least 36 attempts overall**.
- Use the same frozen challenge/environment/scorecard and same judge model/prompt
  configuration for all versions. Run isolated fresh environments each time.
- Retain every attempt, including timeouts and failures. Do not replace bad results
  with undisclosed retries or select only the best judge response.
- Report mean and median score and execution time, execution success rate, number
  of scored runs, and number/reasons of unscored runs. Do not treat unscored runs
  as zero or drop them from the failure/accounting report. With this small sample,
  describe observed results without claiming statistical significance.
- Use actual `codex exec` judge results. Simulated demo scores do not satisfy the
  assignment. A scripted reference is for adapter testing, not your final solution.

The submitted improvements may help or hurt performance. Honest negative results
are acceptable; unsupported claims of improvement are not. Each change must have
a concrete hypothesis and evidence showing what happened.

## Example improvement hypotheses

For CRM: improve question relevance, handle transient failures safely, reduce
redundant reads without losing verification, prevent duplicate follow-ups, improve
customer-facing commitments and next steps.

For checkout: improve evidence collection, diagnose before patching, reduce patch
scope, preserve regression checks, improve accuracy of incident reporting.

These are options, not a mandated action sequence. Planning, agent topology,
prompts, branching, concurrency, retry policy, and memory are solution-owned choices.

## Fixed benchmark boundary

**Do not modify ChallengeDefinition, ChallengeEnv, or ChallengeScorecardForm.**
This includes fixtures, failure injection, limits, simulator/verifier code,
weights, yes/no/maybe anchors, and the `maybe=0.33` mapping. Do not change the engine,
judge prompt, schemas, or collected evidence to improve scores.

`benchmark-lock.json` and `scripts/verify_lock.py` detect accidental edits. Official
grading uses the evaluator's trusted checkout/commit, not a specialist-provided
copy of the lock file. Editing both a protected file and the lock does not authorize
a benchmark change.

If you find a benchmark defect, report a minimal reproduction separately. The
benchmark owner decides whether a new benchmark version is needed; all compared
solutions must then be reevaluated consistently. Do not silently patch the task.

## Evidence is part of the deliverable

Read [the run-log specification](../docs/run-log-spec.md). Your workflow provides
candidate output. The engine independently adds environment, engine, and
verification evidence. Never fabricate those sources or supply your own score.
Every business action must occur in the provided environment. No real CRM,
payment, or email service is needed for these synthetic challenges.

## Acceptance

The engine must run all four versions through the same API without changing its
code. Runs must produce schema-valid logs, real judge artifacts, and results
visible on the score/time chart with solution name, version, seed, and evidence.
Follow [the submission checklist](submission-checklist.md) before handing over.
