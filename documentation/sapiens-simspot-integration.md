# Sapiens and SimSpot integration

## Confirmed boundary

The customer-discovery objective is part of the authored workflow. A customer Sapi
owns a Scheduled Routine whose saved prompt contains that objective and the selected
customer persona. When the Routine runs, Sapiens delivers the objective through its
existing turn-delivery behavior. No separate completed-turn relay, callback or new
public Sapiens API is required.

SimSpot remains the authoritative CRM SimApp. AutoWFBench starts fresh SimSpot state
for each benchmark run and the n8n workflow uses only the documented, authenticated
SimApp operations. Sapiens does not receive the run-scoped SimSpot token and does not
write evaluator state.

## Existing contracts

- Sapiens Routine ownership and scheduling use `routines`, `routine_create`,
  `routine_update`, `routine_pause` and `routine_resume`.
- Each case fixture supplies a repeatable Routine objective describing which customer
  facts may be revealed for the discovery topics asked.
- AutoWFBench exposes `GET /apps` and typed
  `POST /apps/{app}/{operation}` calls using a run-scoped bearer token.
- SimSpot owns contacts, discovery state, follow-ups and customer-message evidence.
- AutoWFBench freezes authoritative events and state before evaluation.

## Repeatable customer behaviour

The five Routine objectives cover:

1. an interested founder whose budget remains unclear;
2. an enterprise contact who is not the decision-maker;
3. an existing customer represented by a duplicate inbound contact;
4. a privacy-conscious customer allowing structured summary fields only; and
5. a high-value customer whose confirmed requirements replace the initial scope.

For deterministic local and scored evaluation, the AutoWFBench customer SimApp
mirrors the facts and topic-gating defined by the same case objective. This keeps
benchmark state reproducible while Sapiens tests validate the real Routine scheduling
and delivery mechanism separately.

## Security and privacy

- Keep Sapiens and SimSpot on local interfaces during development.
- Never place SimSpot bearer tokens, authorization headers or evaluator data in a
  Routine prompt, chat history, artifact or retained log.
- Ask only allowlisted discovery topics from the active challenge package.
- Store only fields permitted by the customer's explicit consent scope.
- Do not treat Sapiens prose as authoritative CRM state; verify SimSpot readback.

## Optional Sapiens Composer backend

Composer generation now accepts `AWB_COMPOSER_PROVIDER=sapiens`; the default remains
`codex`. The existing `compose` command uses the selected backend without changing
the protected CLI or benchmark contracts. Generation sends one public authoring
request through the documented Sapiens CLI to Chief, who selects or creates the
`N8nComposer` specialist. It does not schedule a customer Routine.

From the repository root in PowerShell, with an authenticated Sapiens host already
running, point to its **Python entrypoint**, not the `.cmd` launcher:

```powershell
$env:SAPIENS_CLI = (Resolve-Path ../sapiens4-latest/sapiens4).Path
$env:SAPIENS4_URL = 'http://127.0.0.1:4174'
python -m development.tools.smoke_sapiens_composer --output runs/sapiens-composer-local
```

This authors and validates one typed graph without executing or scoring it. To
reuse that graph and execute only development seed 0 in pinned Docker n8n:

```powershell
python -m development.tools.smoke_sapiens_composer --output runs/sapiens-composer-local --execute
```

The smoke command explicitly disables the judge. Its total remains `null` and its
benchmark status stays `awaiting_llm_judge`; success requires verified execution
and every deterministic criterion passing, not a fabricated overall score. It
targets the authenticated benchmark SimSpot environment, **not** the browser UI's
separate SQLite database. It is distinct from the UI lead-creation smoke described
in `development/simspot_ui/examples/README.md`.

For an explicitly authorized future scored Composer run, setting
`$env:AWB_COMPOSER_PROVIDER = 'sapiens'` selects the backend for the usual `compose`
command. That command still runs its existing development search and held-out
judging; selecting Sapiens does **not** make it unscored. Generation's model comes
from the Sapiens host configuration; it does not override the judge model.

Each generation directory retains the public prompt/schema, submission receipt,
final observation, typed graph, validated native workflow and provenance. Only a
successful `Completed` observation for the accepted turn permits compilation.
An early output file, waiting clarification, failed call or malformed graph is
not accepted as success. The native workflow passes the same graph compiler and
validation used by Codex.

On an observation timeout, the host may still be working. Re-run with the same
output directory to observe the **same** accepted turn; no duplicate chat is sent.
`SAPIENS_COMPOSER_TIMEOUT` controls the observation timeout in seconds (default
1800). If submission itself has an uncertain outcome, generation stops: inspect
Chief history through the CLI before making any explicit retry. Do not delete the
receipt to retry blindly. A changed host, prompt or provider needs a fresh directory.

The CLI argument contains file paths instead of a large JSON prompt, avoiding
Windows command-line length limits. Child CLI processes do not inherit `AWB_` or
`AUTOWFBENCH_` variables. The running Sapiens host has its own permissions: the
authoring file restriction is a prompt boundary, **not an OS sandbox**. Use a
dedicated host/workspace with only public authoring material; never pass secrets
or hidden evaluator data. Generated code is untrusted and must be reviewed before
any execution outside the isolated local development environment.

### First adapter verification, 2026-10-12

- 72/72 local development tests passed on Windows, including 13 adapter/smoke tests.
- The unchanged benchmark lock verified all 28 protected files.
- A live CLI submission to Chief delegated to `N8nComposer`, completed, and returned
  a typed graph accepted by the standard compiler. Cached reuse did not resubmit.
- The compiled workflow ran in Docker n8n against fresh SimSpot development seed 0.
  Execution completed; all functional deterministic checks passed. It used 13
  business calls and failed the efficiency criterion, yielding **7.5/8 deterministic
  points**, with overall score **null**. The strict smoke command therefore exited
  nonzero. This is a working transport/authoring/execution integration, not a fully
  passing candidate or a scored benchmark result.
- The generated candidate still needs call-count optimization and validation across
  the other cases. No repair generation or judge was started for this adapter test.

Portable evidence metadata is in `development/results/sapiens-composer-smoke.json`.
The public prompts, receipt, candidate and full local evidence remain under the
ignored `runs/sapiens-composer-cli-20261012/` directory on the test machine.

## Earlier Windows verification

- Sapiens Routine contract suite: 15 tests passed.
- Sapiens Windows suite: 8 tests passed.
- AutoWFBench suite: 45 tests passed.
- Docker n8n completed all five SimSpot cases on Windows with 8/8 deterministic
  points and ten business calls per case; judging was disabled.

No Linux or WSL installation is required on the host. Docker Desktop supplies the
Linux container used for n8n, while Sapiens and AutoWFBench retain their supported
Windows execution paths.
