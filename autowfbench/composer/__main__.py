from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from autowfbench.composer.evaluation import LocalBenchmarkEvaluator, N8nBenchmarkEvaluator
from autowfbench.composer.generator import CodexGenerator
from autowfbench.composer.n8n_generator import N8nGenerator
from autowfbench.composer.n8n_composition import McpCompositionRunner
from autowfbench.composer.n8n_mcp_generator import OfficialN8nMcpGenerator
from autowfbench.composer.n8n_runtime import N8nCliRuntime
from autowfbench.composer.n8n_validation import issues_as_dicts, validate_n8n_workflow
from autowfbench.core.common import read_json
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
    for name, help_text in (
        ("n8n-generate", "Generate and validate one native n8n workflow"),
        ("n8n-run", "Generate, validate, and benchmark one native n8n workflow"),
    ):
        native = sub.add_parser(name, help=help_text)
        native.add_argument("challenge_id")
        native.add_argument("--model", default=os.environ.get("AWB_COMPOSER_MODEL", "gpt-6.1-sol"))
        native.add_argument("--data-dir", type=Path, required=True)
        native.add_argument("--attempts", type=int, default=3)
        native.add_argument("--judge-url", default=os.environ.get("AWB_JUDGE_URL"))
        native.add_argument("--benchmark-data-dir", type=Path, default=Path("runs"))
        native.add_argument("--seed", type=int, default=0)
        native.add_argument("--env-bind", default="0.0.0.0")
        native.add_argument("--env-public", default="host.docker.internal")
    benchmark_native = sub.add_parser("n8n-benchmark", help="Benchmark an existing validated native n8n artifact")
    benchmark_native.add_argument("challenge_id")
    benchmark_native.add_argument("workflow", type=Path)
    benchmark_native.add_argument("--judge-url", default=os.environ.get("AWB_JUDGE_URL"))
    benchmark_native.add_argument("--benchmark-data-dir", type=Path, default=Path("runs"))
    benchmark_native.add_argument("--seed", type=int, default=0)
    benchmark_native.add_argument("--env-bind", default="0.0.0.0")
    benchmark_native.add_argument("--env-public", default="host.docker.internal")
    repair_native = sub.add_parser("n8n-repair", help="Repair an existing Composer-generated n8n artifact")
    repair_native.add_argument("challenge_id")
    repair_native.add_argument("workflow", type=Path)
    repair_native.add_argument("--model", default=os.environ.get("AWB_COMPOSER_MODEL", "gpt-6.1-sol"))
    repair_native.add_argument("--data-dir", type=Path, required=True)
    repair_native.add_argument("--attempts", type=int, default=3)
    validate_native = sub.add_parser("n8n-validate", help="Validate an existing native n8n artifact without benchmarking")
    validate_native.add_argument("challenge_id")
    validate_native.add_argument("workflow", type=Path)
    mcp_native = sub.add_parser("n8n-mcp-generate", help="Author and execute one workflow through official n8n MCP")
    mcp_native.add_argument("challenge_id")
    mcp_native.add_argument("--model", default=os.environ.get("AWB_COMPOSER_MODEL", "gpt-6.1-sol"))
    mcp_native.add_argument("--data-dir", type=Path, required=True)
    mcp_native.add_argument("--mcp-url", default=os.environ.get("N8N_MCP_URL", "http://127.0.0.1:5678/mcp-server/http"))
    mcp_native.add_argument("--mcp-token-env", default="N8N_MCP_TOKEN")
    mcp_native.add_argument("--n8n-container", default=os.environ.get("N8N_MCP_CONTAINER", "awb-composer-mcp-n8n"))
    mcp_native.add_argument("--existing-workflow-id")
    mcp_native.add_argument("--validation-error", action="append", default=[])
    mcp_compose = sub.add_parser("n8n-mcp-compose", help="Run bounded composition-first official n8n MCP iterations")
    mcp_compose.add_argument("challenge_id")
    mcp_compose.add_argument("--model", default=os.environ.get("AWB_COMPOSER_MODEL", "gpt-6.1-sol"))
    mcp_compose.add_argument("--data-dir", type=Path, required=True)
    mcp_compose.add_argument("--max-iterations", type=int, default=3)
    mcp_compose.add_argument("--mcp-url", default=os.environ.get("N8N_MCP_URL", "http://127.0.0.1:5678/mcp-server/http"))
    mcp_compose.add_argument("--mcp-token-env", default="N8N_MCP_TOKEN")
    mcp_compose.add_argument("--n8n-container", default=os.environ.get("N8N_MCP_CONTAINER", "awb-composer-mcp-n8n"))
    mcp_compose.add_argument("--judge-url", default=os.environ.get("AWB_JUDGE_URL"))
    mcp_compose.add_argument("--benchmark-data-dir", type=Path, default=Path("runs"))
    mcp_compose.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.command == "simulate":
        history = ComposerSearch(SIMULATED_CHALLENGE, SimulatedGenerator(), SimulatedEvaluator(), args.data_dir, iterations=2, repeats=2).run()
        print("SIMULATED ONLY — no benchmark or judge was invoked.")
        print(json.dumps(history, indent=2))
        return
    if args.command == "n8n-mcp-generate":
        challenge = load_challenge(args.challenge_id)["definition"]
        runtime = N8nCliRuntime()
        workflow, provenance = OfficialN8nMcpGenerator(
            args.model, args.data_dir, runtime, args.mcp_url,
            token_env=args.mcp_token_env, container=args.n8n_container,
        ).generate(
            challenge,
            existing_workflow_id=args.existing_workflow_id,
            validation_errors=[{"code": "N8N_EXECUTION_REJECTED", "message": item} for item in args.validation_error],
        )
        print(json.dumps({
            "workflow": str((args.data_dir / "workflow.json").resolve()),
            "workflow_id": workflow["id"],
            "workflow_digest": provenance["workflow_digest"],
            "mcp_tool_trace": str((args.data_dir / "mcp-tool-trace.json").resolve()),
        }, indent=2))
        return
    if args.command == "n8n-mcp-compose":
        challenge = load_challenge(args.challenge_id)["definition"]
        runtime = N8nCliRuntime()

        def generator_factory(iteration_dir):
            return OfficialN8nMcpGenerator(
                args.model, iteration_dir, runtime, args.mcp_url,
                token_env=args.mcp_token_env, container=args.n8n_container,
            )

        workflow, history = McpCompositionRunner(
            generator_factory, runtime, args.data_dir, max_iterations=args.max_iterations,
        ).run(challenge)
        result = {
            "workflow": str((args.data_dir / f"iteration-{len(history):02d}" / "workflow.json").resolve()),
            "workflow_id": workflow["id"], "iterations": history,
        }
        if args.judge_url:
            engine = Engine(args.benchmark_data_dir, args.judge_url, os.environ.get("AWB_JUDGE_TOKEN"), "0.0.0.0", "host.docker.internal")
            workflow_path = args.data_dir / f"iteration-{len(history):02d}" / "workflow.json"
            result["benchmark"] = N8nBenchmarkEvaluator(engine, args.challenge_id, workflow_path, runtime).evaluate(workflow, args.seed).as_dict()
        print(json.dumps(result, indent=2))
        return
    if args.command in ("n8n-generate", "n8n-run"):
        challenge = load_challenge(args.challenge_id)["definition"]
        runtime = N8nCliRuntime()
        workflow, provenance = N8nGenerator(args.model, args.data_dir, runtime, attempts=args.attempts).generate(challenge)
        result = {
            "workflow": str((args.data_dir / "workflow.json").resolve()),
            "workflow_id": workflow["id"],
            "workflow_digest": provenance["workflow_digest"],
            "attempts_used": provenance["attempts_used"],
            "n8n_version": provenance["n8n_version"],
        }
        if args.command == "n8n-run":
            if not args.judge_url:
                raise SystemExit("A real judge URL is required for n8n-run")
            engine = Engine(args.benchmark_data_dir, args.judge_url, os.environ.get("AWB_JUDGE_TOKEN"), args.env_bind, args.env_public)
            observation = N8nBenchmarkEvaluator(engine, args.challenge_id, args.data_dir / "workflow.json", runtime).evaluate(workflow, args.seed)
            result["benchmark"] = observation.as_dict()
        print(json.dumps(result, indent=2))
        return
    if args.command == "n8n-benchmark":
        if not args.judge_url:
            raise SystemExit("A real judge URL is required for n8n-benchmark")
        challenge = load_challenge(args.challenge_id)["definition"]
        workflow = read_json(args.workflow)
        errors = issues_as_dicts(validate_n8n_workflow(workflow, challenge))
        if errors:
            raise SystemExit("Workflow failed deterministic validation: " + json.dumps(errors))
        runtime = N8nCliRuntime()
        runtime_errors = runtime.validate_import(workflow, args.workflow.parent / "benchmark-validation")
        if runtime_errors:
            raise SystemExit("Workflow failed pinned n8n import: " + json.dumps(runtime_errors))
        engine = Engine(args.benchmark_data_dir, args.judge_url, os.environ.get("AWB_JUDGE_TOKEN"), args.env_bind, args.env_public)
        observation = N8nBenchmarkEvaluator(engine, args.challenge_id, args.workflow, runtime).evaluate(workflow, args.seed)
        print(json.dumps(observation.as_dict(), indent=2))
        return
    if args.command == "n8n-repair":
        challenge = load_challenge(args.challenge_id)["definition"]
        workflow = read_json(args.workflow)
        runtime = N8nCliRuntime()
        errors = issues_as_dicts(validate_n8n_workflow(workflow, challenge))
        if not errors:
            errors = runtime.validate_import(workflow, args.data_dir / "source-import")
        if not errors:
            errors = runtime.validate_execution(workflow, args.workflow, challenge)
        if not errors:
            raise SystemExit("Existing workflow already passes all deterministic validation")
        repaired, provenance = N8nGenerator(args.model, args.data_dir, runtime, attempts=args.attempts).generate(challenge, workflow, errors)
        print(json.dumps({
            "workflow": str((args.data_dir / "workflow.json").resolve()),
            "workflow_id": repaired["id"], "workflow_digest": provenance["workflow_digest"],
            "source_workflow_digest": provenance["source_workflow_digest"],
            "attempts_used": provenance["attempts_used"], "n8n_version": provenance["n8n_version"],
        }, indent=2))
        return
    if args.command == "n8n-validate":
        challenge = load_challenge(args.challenge_id)["definition"]
        workflow = read_json(args.workflow)
        runtime = N8nCliRuntime()
        errors = issues_as_dicts(validate_n8n_workflow(workflow, challenge))
        if not errors:
            errors = runtime.validate_import(workflow, args.workflow.parent / "standalone-validation")
        if not errors:
            errors = runtime.validate_execution(workflow, args.workflow, challenge)
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
        raise SystemExit(0 if not errors else 1)
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
