# Operating and deployment notes

## Local services

Defaults: engine/UI 8080, judge 9100, example solution 9201. Each environment binds
an ephemeral local port and exists for one run. The engine currently runs on macOS
or Linux (its child startup uses a pipe selector). Use WSL/Linux for Windows hosting.
All services use Python's standard HTTP server and are development services.

`AWB_CONTROL_TOKEN` authenticates engine mutations. If unset, a random token is
printed at startup. Dashboard read APIs have no authentication because the default
binding is local. `AWB_JUDGE_TOKEN` authenticates requests between engine and judge.
Solution API credentials are resolved from a manifest's `auth_env` variable.
Administrative environment tokens are separate from candidate tool tokens.

## Docker-hosted n8n / remote workflow

The solution must be able to reach the environment URL supplied in its run request.
`127.0.0.1` inside an n8n container refers to that container. On Docker Desktop use:

```bash
python -m autowfbench serve --env-bind 0.0.0.0 \
  --env-public host.docker.internal --judge-url http://127.0.0.1:9100
```

This exposes ephemeral environment ports on the host; restrict them to the solution
network with a firewall. A remote deployment needs stable routing/reverse proxy or
a dedicated network. Do not expose the UI or judge to the public internet without
authentication, TLS, access control, and a production server. Benchmark credentials
and result storage must remain inaccessible to candidate hosts.

Process isolation guarantees fresh state, not protection from same-user malicious
code. The benchmark/examples do not execute candidate source. General code-execution tasks
need container/VM isolation, resource controls, restricted egress, and an external
verifier. Do not grant candidates the benchmark filesystem or administrative API.

## Budgets and limits

- At most four active engine attempts.
- Per-challenge wall-clock and tool-call limits; solution start response within 15s.
- 2 MB maximum JSON request/response, 20 text artifacts, 1,000 reported trace entries.
- Judge subprocess timeout 180s; engine judge request timeout 200s.
- Clock is monotonic for durations; UTC timestamps are for human inspection.
- Environment freezes before cancellation and judging. Late calls cannot mutate it.

The lightweight example adapter stores its job status in memory and is not a
durable production queue. It is intentionally a protocol reference. Specialist
adapters should persist status, implement idempotency, and clean up old jobs.
The engine persists completed logs/reports atomically but does not recover active
processes after a host crash; keep crash-interrupted runs separate from scored ones.

Store `runs/` as private benchmark data. It is gitignored. Do not commit secrets or
large execution logs. Only synthetic, sanitized benchmark/examples belong in `benchmark/examples/`.

## Source checkout distribution

This MVP is run from a cloned source checkout (`pip install -e .`). Challenge files
and benchmark/schemas are repository assets, not bundled wheel data. For an alternate checkout
location set `AUTOWFBENCH_ROOT` to its root. A standalone wheel distribution is not
supported yet.
