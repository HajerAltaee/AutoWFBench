"""Author through Chief, then optionally run one development seed without a judge."""
import argparse
import json
from pathlib import Path

from autowfbench.core.common import read_json, save_json
from autowfbench.interfaces.composer.n8n import N8nRuntime
from autowfbench.interfaces.composer.search import evaluate, generate, public_input


def local_pass(summary):
    """An intentionally unjudged run stays awaiting_llm_judge, not complete."""
    return bool(summary["runs"]) and all(
        run.get("execution_pass") is True and run.get("score_0_10") is None
        and run.get("status") == "awaiting_llm_judge"
        and any(c["evaluator"] == "deterministic" for c in run.get("criteria", []))
        and all(c["answer"] == "yes" for c in run["criteria"] if c["evaluator"] == "deterministic")
        for run in summary["runs"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="Run seed 0 locally; never invokes a judge")
    args = parser.parse_args()
    root = args.output.resolve()
    public_path = root / "public-input.json"
    public = read_json(public_path) if public_path.exists() else public_input("simspot-customer-discovery")
    save_json(public_path, public)
    workflow = generate(public, root / "generation", provider="sapiens")
    print(json.dumps({"workflow":str(root / "generation/workflow.json"), "validated":True, "scored":False}), flush=True)
    if args.execute:
        summary, _ = evaluate(workflow, "simspot-customer-discovery", [0], root / "local",
                              N8nRuntime(docker_image="docker.n8n.io/n8nio/n8n:2.42.3"), judge_model=None)
        print(json.dumps({"summary":str(root / "local/summary.json"), "scored":False,
                          "local_pass":local_pass(summary),
                          "runs":[{"status":run["status"], "execution_pass":run.get("execution_pass"),
                                   "deterministic_points":run.get("deterministic_points"),
                                   "tool_calls":run.get("tool_calls"),
                                   "failed_checks":[c["id"] for c in run.get("criteria", [])
                                                    if c["evaluator"] == "deterministic" and c["answer"] != "yes"]}
                                  for run in summary["runs"]]}), flush=True)
        if not local_pass(summary):
            raise SystemExit("Unscored workflow failed one or more local checks; inspect retained local evidence")


if __name__ == "__main__":
    main()
