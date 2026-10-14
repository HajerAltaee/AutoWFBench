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

## Windows UI QA: foreground activation, 2026-10-13

This is a separate, unscored browser UI test against the local SimSpot UI database.
It does not validate the benchmark runner or a complete Sapiens-controlled flow.
Sanitized evidence and the follow-up checklist are recorded in
`development/results/sapiens-blindly-ui-qa.json`.

### Observed failure through Sapiens

Chief was asked to use its managed Blindly4 wrapper to edit only the fictional
Sapiens Demo contact's Job Title, save it and verify persistence after refresh.
The execution session confirms that `blindly activate --pid 17104`, invoked through
`sapiens/computer/commands.py`, exited 1 with:

```json
{"error":"Input blocked: the intended PID is not the foreground application","code":"accessibility_error"}
```

The turn's conversation status is `done`, but its execution outcome is
`Unresolved`: Sapiens reported stopping before observing the SimSpot URL or making
CRM changes. A completed conversation must not be counted as a passed UI test.

Blindly4's `windows/Input/Native.cs` attempts `SetForegroundWindow`, waits for the
target foreground PID, and fails closed if it does not match. This locates the
failure at foreground activation; it does not establish a general Chrome
permission problem, a SimSpot defect, or why activation failed on this occasion.

### Successful direct control

In a later test, the Codex desktop agent called the same configured Blindly4 build
directly, outside Sapiens. Chrome activation, Edit, changing Job Title from
`Automation test lead` to `UI-verified automation lead`, guarded Save, and browser
Reload all succeeded. Fresh accessibility observations confirmed the updated title
after reload. No API or database write was used for this edit.

The local screenshot is
`runs/sapiens-live-demo-20261013/06-blindly-ui-result.jpg`. It is not committed; raw
provider logs and unrelated browser information should not be published as QA
evidence. The direct run had a different foreground/tab context, so it is not a
controlled reproduction or proof that the Sapiens path now works.

### Follow-up reproduction and acceptance

1. Use a disposable fictional contact with a known initial title, or explicitly
   reset the demo title through the UI. It already contains the successful edit.
2. Confirm no competing automation; freshly observe Chrome's PID and foreground
   state. Never reuse the historical PID or accessibility paths blindly.
3. Submit the bounded edit/save/reload objective through Sapiens with Chrome
   already foreground, retaining the managed-wrapper command and output evidence.
4. Separately test background-to-foreground activation to isolate that boundary.
   Do not disable guards, change security settings or substitute API writes.
5. Count success only when Sapiens observes the correct URL and contact, edits and
   saves the intended field, and observes the new value after reload. On a blocked
   action, stop and record it as unresolved.

### Follow-up results, same day

Two user-requested, unscored Sapiens retests were run after the initial report:

- Turn `9f90114fae474f8db59cd035c1d53b92`: Chrome was prepared in the foreground,
  and Sapiens independently confirmed that state. Its managed `find` command then
  failed while printing a Unicode UI label: `'charmap' codec can't encode character
  '\u25cf' in position 839: character maps to <undefined>`. The execution log
  confirms exit 1; no edit or Save was attempted.
- The diagnostic Python process reported stdout encoding `cp1252`. The same
  read-only wrapper command with `python -X utf8` and the configured Blindly binary
  returned the URL and Unicode UI labels successfully. This was an output-encoding
  adjustment, not a source change or a safety-guard bypass. The diagnostic was
  outside the managed workspace and is not an end-to-end Sapiens result.
- Turn `573eec2ebd4747eab2a6d0206bfb0553`: Sapiens used `python -X utf8`, but its
  fresh observation found ChatGPT foreground and Chrome background. Managed
  activation failed again with the original foreground-PID error. The reason for
  that foreground state is unconfirmed. It stopped before editing or testing the
  previously failing Unicode read.
- Independent read-only Blindly inspection still showed `UI-verified automation
  lead`, not the requested new value `Sapiens UI-verified lead`.

The foreground failure now has two recorded managed occurrences, but the reason
Windows did not switch focus remains unconfirmed. The Unicode diagnostic passed;
neither retest completed the UI workflow. No CRM writes, source fixes, security
changes or scored benchmarks were made during these retests. Further model retries
were stopped to conserve usage. Next validation needs Chrome kept foreground for
the entire UTF-8-mode run; background activation remains a separate open QA case.

### Verified Sapiens-controlled UI run, 2026-10-14

The local Sapiens source helper now explicitly configures stdout and stderr as
UTF-8 at its CLI entrypoint. Four regression tests exercise the real Python
entrypoint under forced `cp1252:strict` output with mocked desktop results; three
reproduced the original failure before the change, and all four now pass. The eight
Windows tests, eight computer-recovery tests, and 54 permission-free Blindly checks
also pass. Foreground validation and guarded-save checks were not changed.

After restarting the existing source host and SimSpot with their original data
directories and the documented Blindly binary override, Chief completed turn
`680e344421ea427fb4833839f4b82cf0` through its managed UI wrapper:

1. Opened the task's exact local URL with `blindly open --url`, then freshly
   verified Chrome's foreground PID, URL and the fictional contact identity.
2. Observed `UI-verified automation lead`, opened Edit, and changed only Job Title
   to `Sapiens UI-verified lead`.
3. Used an exact field-value guard for Save (`ok: true`, `verified: true`).
4. Pressed Chrome's Reload control and read back the new title on the same contact.

The provider execution log confirms the actual UI commands and returned values,
not just a model success claim. One initial `blindly read` syntax error was corrected
to the documented wrapper `read` command before editing. No CRM API/database writes,
scored benchmarks or security changes were used. This is the first verified
**Sapiens-controlled** edit/save/reload result, distinct from the earlier direct
Codex-to-Blindly control.

The new Chrome process disappeared at the end of the model run. This is consistent
with the existing Windows process-job cleanup in `sapiens/runtime/codex.py` and
`sapiens/runtime/windows.py`; no process-lifetime safeguards were removed. Reopening
the contact independently through Blindly confirmed the saved title again. A native
screenshot is retained locally at
`runs/sapiens-ui-fix-20261014/sapiens-ui-verified.jpg`. For subsequent tests, leave an
already-running Chrome open before submitting the request, and avoid competing
desktop input.

This verifies one local UI scenario. It does not prove that arbitrary background
foreground-switch requests now work, that the complete import/follow-up flow passes
through UI, or that a separately installed Sapiens4 desktop package contains the
source fix. The local Sapiens source change and its tests must be reviewed in that
repository; this AutoWFBench report alone does not distribute the fix.

Companion fix: [Sapiens4 PR #28](https://github.com/aleski-green/sapiens4/pull/28),
commit `7b894a5d98fcd633293ff6d647f539a9aba59761`.

## Earlier Windows verification

- Sapiens Routine contract suite: 15 tests passed.
- Sapiens Windows suite: 8 tests passed.
- AutoWFBench suite: 45 tests passed.
- Docker n8n completed all five SimSpot cases on Windows with 8/8 deterministic
  points and ten business calls per case; judging was disabled.

No Linux or WSL installation is required on the host. Docker Desktop supplies the
Linux container used for n8n, while Sapiens and AutoWFBench retain their supported
Windows execution paths.
