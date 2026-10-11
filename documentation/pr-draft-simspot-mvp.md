# Pull request notes: Add SimSpot customer-discovery MVP

PR #9 remains a draft while the MVP is reviewed. The challenge version and benchmark
lock refresh are owner-approved and included on the branch.

## Summary

- add a fixture-driven `simspot-customer-discovery` challenge with five customer
  personas and edge cases;
- expose typed SimSpot discovery, contact, follow-up and messaging operations;
- verify duplicate selection, explicit consent, separate requirements confirmation,
  readback ordering, customer contact and call efficiency;
- connect the challenge to the generic AutoWFBench CLI, Composer discovery and
  scripted local protocol fixture;
- make environment startup and benchmark-lock verification work correctly with
  Windows pipes and CRLF checkouts;
- document the confirmed Sapiens boundary: the Routine delivers the workflow-authored
  objective, with no separate response relay or callback API.

## Test plan

- [x] `python -m unittest development.tests.test_simspot -v`
- [x] `python -m unittest discover -s development/tests -v`
- [x] Real child-process/authenticated HTTP SimSpot run on Windows
- [x] Sapiens `test_routines.py` on Windows
- [x] Sapiens `tests.test_windows` on Windows
- [x] Composer public-input discovery for SimSpot
- [x] Docker n8n 2.42.3 -> Windows-hosted SimSpot authenticated smoke test
- [x] Full Docker runner across all five SimSpot cases (8/8 deterministic points,
  10 calls per case, judging disabled)
- [x] Sapiens objective-delivery boundary confirmed; no separate relay required
- [x] Owner-approved `v0.1.0` challenge registration and lock refresh
- [ ] Development Composer attempts
- [ ] Held-out/scored runs

## Remaining work

- Run development Composer attempts after review of the MVP boundary.
- Run held-out/scored benchmarks only after local Composer integration passes.

Direct Windows installation remains a portability caveat: `n8n@2.42.3` declares
Node `>=24`, and `isolated-vm` needs C++ build tools when no compatible binary is
available. The tested Docker runner is the documented Windows path.

## Review focus

- Is the deterministic simulator boundary appropriate for Sapiens customer personas?
- Should summary-only consent permit a generated narrative, or structured fields only?
- Does the documented workflow-objective boundary match the intended Sapiens usage?
- Should Docker become the documented Windows n8n path, with direct Node installation
  retained only for environments that already satisfy n8n's native dependencies?

## Protected files included in the approved lock refresh

- `autowfbench/interfaces/cli.py`
- `autowfbench/runtime/engine.py`
- `autowfbench/runtime/environment/apps.py`
- `autowfbench/runtime/environment/state.py`
