# Feedback: Author of the CRM Lead Qualification benchmark

Reviewed submission commit: `d865646ccb042391d5b9c792d63717e66aa70ac4`.

## What the WF-specialist implemented well

- A structured challenge, resettable mock CRM/email/research environment, audit
  events, permissions, failure injection, weighted evaluator, and reference runner.
- V3 n8n workflow performs one action, observes its real result, and decides again.
  This supports reaction to actual tool failures better than generating a whole
  action plan upfront.
- Deterministic evaluation checks environment state and execution events rather
  than simply accepting the agent's final completion claim.
- A bounded communication rubric and judge-response validator exist. The README
  explicitly marks judging as pending and distinguishes the scripted reference
  from a live agent result.
- All five included tests and configuration validation passed in the review.

## Findings requiring correction

1. **No actual LLM judge invocation.** `benchmark/judge.py` builds a request and
   validates numbers; execution paths never call a judging model. The n8n evaluation
   endpoint passes `None`. The reference run reports 9 deterministic points and
   `awaiting_llm_judge`.
2. **A supplied number can appear as a completed judge score.** Passing `0.9` into
   the demo produced 9.9/10 and `complete`, without a model call. This was documented
   as an externally supplied score; the issue is missing integration, not evidence
   of intentional misrepresentation. Replace this route for official results with
   a recorded `codex exec` judge invocation and validated criterion responses.
3. **Evaluator coverage does not match the golden requirements.** In the review,
   wrong CRM platform, owner, next action, follow-up date, and a missing WhatsApp
   requirement still retained 9/9 deterministic points. Removing the completion
   event also retained 9/9. Add negative tests and align checks with the contract.
4. **Rubric anchors and evidence are incomplete.** Field names and maxima do not
   define partial-credit behavior. The judge request omits service-capability
   evidence, selects messages by position, and does not require valid strengths/
   problems arrays. Explicit anchors and referenced evidence are needed.
5. **Multi-agent behavior is largely simulated.** One planner selects actor labels;
   a research completion operation returns fixture data. This verifies a delegation
   protocol, not independent specialist reasoning. Claims must match what is observed.
6. **Framework and solution are coupled.** One local service hosts Codex execution,
   environment state, and evaluation. Codex runs from a repository containing
   evaluation-only answers. The next version should expose a whole-solution API,
   while the benchmark separately owns environment, evidence, and judging.

## Next deliverable

Implement your workflow behind the standard solution API. Return a valid candidate
submission, make every business action through the supplied environment, and let
the engine collect authoritative evidence. Complete the baseline plus three
improvement submissions in `assignment/README.md`. Do not change the challenge,
environment, scorecard, or grader to improve a result.
