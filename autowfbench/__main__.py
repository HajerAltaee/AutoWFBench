from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

from .common import ROOT, background_server, read_json


def main():
    parser = argparse.ArgumentParser(description="AutoWFBench — separate workflow execution and evidence-based judging")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("serve", "judge", "example-solution", "demo"):
        p = sub.add_parser(name)
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default={"serve": 8080, "judge": 9100, "example-solution": 9201, "demo": 8080}[name])
        if name in ("serve", "demo", "judge"):
            p.add_argument("--data-dir", type=Path, default=Path("runs" if name != "judge" else "runs/judge"))
        if name == "serve":
            p.add_argument("--judge-url", default=os.environ.get("AWB_JUDGE_URL"))
            p.add_argument("--env-bind", default="127.0.0.1")
            p.add_argument("--env-public", default="127.0.0.1")
        if name == "judge":
            p.add_argument("--mode", choices=("codex", "demo"), default="codex")
            p.add_argument("--model", default=os.environ.get("AWB_JUDGE_MODEL"))
        if name == "example-solution":
            p.add_argument("--variant", choices=("reference", "incomplete"), default="reference")
    p = sub.add_parser("environment")
    p.add_argument("challenge_id"); p.add_argument("--seed", type=int, default=0); p.add_argument("--host", default="127.0.0.1")
    p = sub.add_parser("run")
    p.add_argument("challenge_id"); p.add_argument("solution", type=Path); p.add_argument("--seed", type=int, default=0); p.add_argument("--data-dir", type=Path, default=Path("runs")); p.add_argument("--judge-url", default=os.environ.get("AWB_JUDGE_URL"))
    p = sub.add_parser("validate-submission")
    p.add_argument("file", type=Path)
    args = parser.parse_args()
    if args.command == "environment":
        from .environment import serve
        return serve(args.challenge_id, args.seed, args.host)
    if args.command == "judge":
        from .judge import serve
        return serve(args.host, args.port, args.mode, args.model, args.data_dir)
    if args.command == "example-solution":
        from .example_solution import serve
        return serve(args.host, args.port, args.variant)
    if args.command == "validate-submission":
        from .contracts import validate
        validate("submission", read_json(args.file)); print("Submission schema valid."); return
    from .engine import Engine
    from .server import serve
    token = os.environ.get("AWB_CONTROL_TOKEN") or secrets.token_urlsafe(24)
    if args.command == "demo":
        from .judge import Judge, handler_for as judge_handler
        from .example_solution import handler_for as solution_handler
        judge_token = secrets.token_urlsafe(24)
        judge = background_server(judge_handler(Judge("demo", data_dir=args.data_dir / "judge"), judge_token))
        engine = Engine(args.data_dir, f"http://127.0.0.1:{judge.server_port}", judge_token)
        solutions = [background_server(solution_handler(variant)) for variant in ("incomplete", "reference")]
        for challenge, manifest_file in (("crm-lead-qualification", "crm-reference"), ("production-checkout-recovery", "checkout-reference")):
            for variant, server in zip(("incomplete", "reference"), solutions):
                manifest = read_json(ROOT / "examples/solutions" / (manifest_file + ".json"))
                manifest.update(endpoint=f"http://127.0.0.1:{server.server_port}", version="0.1.0" if variant == "incomplete" else "1.0.0")
                engine.submit(challenge, manifest, background=False)
        print("DEMO MODE: real environment execution; simulated judge. No LLM performance claims.", flush=True)
        return serve(engine, args.host, args.port, token)
    engine = Engine(args.data_dir, args.judge_url, os.environ.get("AWB_JUDGE_TOKEN"), getattr(args, "env_bind", "127.0.0.1"), getattr(args, "env_public", "127.0.0.1"))
    if args.command == "run":
        run_id = engine.submit(args.challenge_id, read_json(args.solution), args.seed, background=False)
        result = engine.read(run_id)
        print(f"{run_id}: {result['status']} — score={result['score_0_10']}")
        if result["status"] in ("engine_error", "judge_failed"):
            raise SystemExit(1)
        return
    serve(engine, args.host, args.port, token)


if __name__ == "__main__":
    main()
