# Draft pull request: Add SimSpot customer-discovery MVP

Draft only. Do not publish until the challenge version and protected benchmark files
are approved.

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
- document the existing Sapiens Routine boundary and a proposed credential-isolating
  relay without inventing an approved callback API.

## Test plan

- [x] `python -m unittest development.tests.test_simspot -v`
- [x] `python -m unittest discover -s development/tests -v`
- [x] Real child-process/authenticated HTTP SimSpot run on Windows
- [x] Sapiens `test_routines.py` on Windows
- [x] Sapiens `tests.test_windows` on Windows
- [x] Composer public-input discovery for SimSpot
- [x] Docker n8n 2.42.3 -> Windows-hosted SimSpot authenticated smoke test
- [ ] Live Sapiens-to-SimSpot relay test
- [ ] Owner-approved lock refresh
- [ ] Development Composer attempts
- [ ] Held-out/scored runs

## Known blockers

1. Sapiens does not yet document a completed-turn callback/read contract for a relay.
2. Direct Windows installation is still inconsistent: `n8n@2.42.3` declares Node
   `>=24`, while this repository says Node 22, and `isolated-vm` needs C++ build
   tools when no compatible binary is available. The pinned Docker image is a
   verified Windows development path: it reached host SimSpot through
   `host.docker.internal`, authenticated, read the inquiry and completed `Submit`.
3. The benchmark lock correctly remains red until an owner approves the new challenge
   version and refreshes the four changed protected hashes.

## Review focus

- Is the deterministic simulator boundary appropriate for Sapiens customer personas?
- Should summary-only consent permit a generated narrative, or structured fields only?
- Is the relay the approved live integration direction?
- Should Docker become the documented Windows n8n path, with direct Node installation
  retained only for environments that already satisfy n8n's native dependencies?

## Protected files awaiting approval

- `autowfbench/interfaces/cli.py`
- `autowfbench/runtime/engine.py`
- `autowfbench/runtime/environment/apps.py`
- `autowfbench/runtime/environment/state.py`
