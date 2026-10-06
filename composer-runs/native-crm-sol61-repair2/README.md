# Native CRM Composer experiment

This directory preserves the reviewable provenance for the autonomous
`gpt-6.1-sol` CRM workflow generation experiment.

- `source-workflow.json` is the workflow supplied to the bounded repair run.
- `attempt-*/prompt.txt` records the public generation/repair input.
- `attempt-*/raw-envelope.json` and `raw-workflow.json.txt` preserve raw model
  output.
- `attempt-*/validation-errors.json` records deterministic validation feedback.
- `attempt-*/workflow.json` records each parsed candidate.
- `workflow.json` is the unchanged final validated native n8n artifact.
- `provenance.json` records attempt results, runtime pin, and content digests.
- `benchmark-result.json` is a non-protected summary of the one completed run.

No task-specific workflow logic was manually added, and the final artifact was
not edited after generation. Attempts one and two failed execution-contract
validation; attempt three passed static checks, pinned n8n 2.42.3 import,
public-contract stub execution, and submission-schema validation.

Final canonical workflow digest:
`057c8950d224cb6e611a7859a87a4f7bba0e8191616a19917eb27fd43b2f687b`

The benchmark completed with a score of 2.33/10, 11 tool calls, and a 20.3348
second execution duration. The low score is an experimental result: no additional
generation or repair was performed after this run.
