from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from autowfbench.composer.evaluation import LocalBenchmarkEvaluator
from autowfbench.composer.generator import CodexGenerator
from autowfbench.composer.search import ComposerSearch
from autowfbench.composer.simulation import SIMULATED_CHALLENGE, SimulatedEvaluator, SimulatedGenerator
from autowfbench.core.contracts import load_challenge
from autowfbench.runtime.engine import Engine


def main():
    parser = argparse.ArgumentParser(description="Black-box Composer for AutoWFBench")
    sub = parser.add_subparsers(dest="command", required=True)
    simulated = sub.add_parser("simulate", help="Run a clearly labelled simulated plumbing experiment")
    simulated.add_argument("--data-dir", type=Path, default=Path("composer-runs/simulated"))
    real = sub.add_parser("run", help="Generate and benchmark candidates with the unchanged engine")
    real.add_argument("challenge_id")
    real.add_argument("--model", default=os.environ.get("AWB_COMPOSER_MODEL"))
    real.add_argument("--judge-url", default=os.environ.get("AWB_JUDGE_URL"))
    real.add_argument("--data-dir", type=Path, default=Path("composer-runs/real"))
    real.add_argument("--benchmark-data-dir", type=Path, default=Path("runs"))
    real.add_argument("--iterations", type=int, default=2)
    real.add_argument("--repeats", type=int, default=2)
    real.add_argument("--seeds", type=int, nargs="+", default=[0])
    real.add_argument("--env-bind", default="127.0.0.1")
    real.add_argument("--env-public", default="127.0.0.1")
    args = parser.parse_args()
    if args.command == "simulate":
        history = ComposerSearch(SIMULATED_CHALLENGE, SimulatedGenerator(), SimulatedEvaluator(), args.data_dir, iterations=2, repeats=2).run()
        print("SIMULATED ONLY — no benchmark or judge was invoked.")
        print(json.dumps(history, indent=2))
        return
    if not args.judge_url:
        raise SystemExit("A real judge URL is required; unscored runs are not an optimization signal.")
    challenge = load_challenge(args.challenge_id)["definition"]
    generator = CodexGenerator(args.model, args.data_dir / "generator")
    engine = Engine(args.benchmark_data_dir, args.judge_url, os.environ.get("AWB_JUDGE_TOKEN"), args.env_bind, args.env_public)
    evaluator = LocalBenchmarkEvaluator(engine, args.challenge_id)
    history = ComposerSearch(challenge, generator, evaluator, args.data_dir, args.iterations, args.seeds, args.repeats).run()
    print(json.dumps(history, indent=2))


if __name__ == "__main__":
    main()
