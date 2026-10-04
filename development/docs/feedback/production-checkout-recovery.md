# Feedback: Author of the Production Checkout Recovery benchmark

Reviewed submission commit: `a7b397f59614d7d2995b0d20f38fb8ef22b94359`.
The submission also included a customer-escalation WorkGraph. Its findings are
included here because they explain the workflow infrastructure's current limits.

## What the WF-specialist implemented well

- Two concrete scenarios, reset scripts, task instructions, and separate verifiers.
- Production checks exercise USD/EUR checkout, payment validation, and existing
  order behavior. These are useful functional checks, beyond plausible prose.
- Customer escalation decomposes investigation into payment, order, and support
  roles, then decision and execution stages.
- A local Codex bridge supports read-only/write modes and asynchronous jobs.

## Findings requiring correction

1. **LLM-as-a-Judge is absent.** The Decision Agent chooses remediation; it does
   not independently grade the completed attempt. There is no judge rubric,
   evaluation model call, or judge-response artifact. Python PASS/FAIL is useful
   verification, but does not satisfy the LLM judging requirement.
2. **The exported asynchronous WorkGraph loses specialist findings.** `/jobs`
   returns an acknowledgement and job ID. The n8n export immediately reads
   `.output` without waiting or retrieving `/jobs/{job_id}`. Add bounded polling,
   failure handling, and result collection before the decision stage.
3. **The verifier branch development/tests existence rather than truth.** Its `exists`
   operator accepts a present `benchmark_passed` field even when its value is false.
   Test the Boolean value and verify failure/retry behavior.
4. **Escalation output is a plan, not completed remediation.** The execution prompt
   writes only `resolution.json`. It does not execute a refund or update order and
   support state. Describe this accurately or implement observable state changes.
5. **Text verification can be fooled.** A resolution action containing
   `do_not_refund_or_mark_paid` passed the substring checks. Incident-summary
   verification checks nonempty headings, not factual accuracy. Add semantic
   judging backed by source evidence and retain functional verification.
6. **Reproducibility and isolation need work.** Machine-specific paths are hardcoded;
   initialization does not invoke reset; specialist read boundaries mostly live in
   prompts. Only the escalation n8n export is committed, despite the described
   production incident workflow. Provide portable exports and explicit isolation.

The intentionally unsolved fixtures failed their verifiers as expected during
review. That is not a failed remediation attempt; no live workflow was executed.

## Next deliverable

Build a complete incident workflow behind the standard solution API, including
investigation, patching, before/after verification, and accurate incident reporting.
Use the supplied constrained checkout environment for this assignment. A fresh
external judge evaluates the frozen result; your workflow does not select its own
score. Follow the baseline plus three improvements assignment, with all benchmark
modules unchanged.
