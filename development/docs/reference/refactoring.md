# Reduction and rTernarity review

Refactored from upstream `d4576156a606910ff8fe1283b8ff86b53d43d704` on 2026-10-05.

The maintained application and JSON Schema sources now occupy **1,882 physical
rows instead of 2,656: 774 fewer rows (29.1%)**. Application source alone fell
19.3%. This approaches the requested 30% row target, but **does not represent
30% less executable logic**: much of the row reduction is declarative formatting.
The existing Python engine is already small and heavily condensed; deleting
another large fraction of it would remove behavior or protections.

## Measurement

| Scope | Before | After | Reduction |
|---|---:|---:|---:|
| Python application | 986 | 989 | -0.3% |
| Dashboard JS, HTML, CSS | 1,095 | 690 | 37.0% |
| Application subtotal | 2,081 | 1,679 | 19.3% |
| JSON Schemas | 575 | 203 | 64.7% |
| Application + schemas | 2,656 | 1,882 | 29.1% |

Counts include blank and comment rows in `.py`, `.js`, `.html`, `.css`, and
schema `.json` files. They exclude tests, development tools, docs, configuration,
challenge data, and example evidence. Those exclusions apply equally to both
revisions; existing tests and example evidence were retained. New regression
tests and this report are additions, not disguised reductions.

Application plus schema bytes fell from 94,629 to 88,625 (**6.3%**), a useful
cross-check against overinterpreting the physical-row percentage. The application
alone fell from 83,139 to 81,711 bytes (1.7%).

Reproduce against the original commit:

```sh
python development/tools/measure_source.py
```

## Three responsibility groups

```text
AutoWFBench/
├── autowfbench/                      application
│   ├── core/                        shared rules
│   │   ├── common.py                storage, hashes, HTTP
│   │   ├── contracts.py             schemas and challenge loading
│   │   └── scoring.py               validation and score arithmetic
│   ├── runtime/                     independent services
│   │   ├── engine.py                orchestration and frozen evidence
│   │   ├── environment.py           simulators and protected checks
│   │   └── judge.py                 independent semantic judgement
│   └── interfaces/                  interaction surfaces
│       ├── cli.py                   command-line workflows
│       ├── solution.py              reference solution API adapter
│       └── web/                     dashboard server and assets
├── benchmark/                       benchmark specification and examples
│   ├── challenges/                  tasks, fixtures, scorecards
│   ├── schemas/                     machine-readable contracts
│   └── examples/                    manifests and evidence examples
└── development/                     maintenance and handoff
    ├── docs/
    │   ├── reference/               system contracts and operation
    │   ├── assignment/              specialist implementation brief
    │   └── feedback/                reviewed challenge lessons
    ├── tests/                       behavioral regression coverage
    └── tools/                       baseline verification and measurement
```

Root entry points, Python package markers, and ecosystem files such as
`pyproject.toml`, `.github`, and `benchmark-lock.json` remain where their tools
expect them. Decomposition stops at cohesive units; files are not split or
invented just to fill three slots. Each challenge retains its definition,
environment, and scorecard. There are still **four evidence sources**, two
challenges, and all seven CLI commands.

## What was removed or consolidated

1. **Contracts:** the run-log schema embedded an 83-row copy of the submission
   contract. It now references `submission.schema.json`. Validators resolve
   relative references from the schema file's absolute URI, independent of the
   caller's working directory. The remaining schema-row savings are formatting.
2. **Dashboard:** one safe DOM builder and cell/badge helpers replace repeated
   table construction. The same builder serves run and criterion rows, using
   text nodes rather than HTML interpolation. Manifest fields are selected from
   one list. Shared CSS rules remove 48 repeated declarations; short rules and
   wrapped markup use compact formatting. Appearance, accessibility attributes,
   chart semantics, filters, and controls remain intact.
3. **Maintenance:** module and asset paths now follow their responsibilities;
   docs, CI, demo manifests, subprocess imports, and lock verification follow
   the new layout. Challenge package loading uses the three module names
   directly. An unused engine import and unused solution result bindings were
   removed; the solution still makes and records those tool calls.

The Python net row count increases by three because of explicit package entry
points and robust schema reference resolution. No new runtime dependencies or
frontend framework were introduced.

## Verification and migration

- All **15 original tests** passed before the refactor; all **18 tests** pass
  afterward. Added tests cover shared-schema rejection parity, schema resolution
  outside the checkout, and the three dashboard assets.
- All five schemas are structurally equivalent to their originals after
  expanding the shared submission reference and ignoring schema declarations.
- Headless Chrome checks at 1440px and 390px verified filtering, challenge
  switching, inspector opening/closing, and submission-dialog controls, with
  no browser errors. Given identical run data, compared DOM content and computed
  styles matched the original at both widths (excluding SVG nodes, which were
  exercised through chart rendering and inspected in screenshots).
- Both real HTTP reference adapters and child environment processes still run.
  Demo reference scores remain 7.32; incomplete workflows remain failures.
  Timeout, authentication, provenance, frozen-log integrity, and null scores
  when judging is unavailable remain covered by the original suite.
- Lock verification and example submission validation pass. The original
  21 protected files remain protected at their relocated paths; new Python
  entry points/package markers expand the protected set to 26 files. Lock
  version 1.1.0 records this intentional owner-level refactor.
- A live paid Codex judge was **not** invoked. Its subprocess contract and
  provenance were tested with the existing mock; demo judging is simulated.

The CLI commands and HTTP routes are unchanged. File paths and internal Python
imports have moved; update local scripts using the former paths. The supported
setup remains an editable install from this checkout. The simulator source
hash changes because its imports moved, so new runs use a new environment
comparison group. Historical frozen packages/logs remain self-contained for
rescoring. Challenge fixtures, weights, scoring anchors, and public protocol
fields have not changed.

To validate:

```sh
python -m unittest discover -s development/tests -v
python development/tools/verify_lock.py
python -m autowfbench validate-submission benchmark/examples/submission.json
```

## Where further reduction would cost functionality

Keep deadline enforcement, child-process cleanup, separate credentials, schema
validation, evidence redaction/freezing, source-AST restrictions, and judgement
provenance. These are core benchmark correctness, not incidental boilerplate.
Keep complete and incomplete reference solutions: both exercise the dashboard
and establish negative controls. Keep illustrative frozen evidence: generating
it on demand adds machinery and weakens inspectability.

A much larger substantive reduction would require accepting a narrower product
scope (for example, removing a challenge, the interactive dashboard, or a judge
mode). None of those features were removed to meet a line-count target.
