"""Explicitly simulated plumbing exercise; never a benchmark result."""
from __future__ import annotations

import uuid

from autowfbench.composer.models import NumericObservation


def _candidate(candidate_id, strategy, steps, hypothesis):
    return {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "challenge_id": "simulated-task",
        "version": "0.1.0" if candidate_id == "c000" else "0.2.0",
        "strategy": strategy,
        "hypothesis": hypothesis,
        "steps": [
            {"id": f"step_{index}", "kind": "tool", "operation": operation, "arguments": {}, "save_as": f"result_{index}", "require_ok": True, "when": []}
            for index, operation in enumerate(steps)
        ],
        "final": {"answer": "Simulated candidate completed.", "artifacts": []},
    }


class SimulatedGenerator:
    def initial(self, challenge, candidate_id):
        return _candidate(candidate_id, "initial", ["alpha.read", "alpha.read", "beta.write"], "Establish an intentionally redundant plumbing baseline.")

    def child(self, challenge, candidate_id, parent, history):
        return _candidate(candidate_id, "efficiency", ["alpha.read", "beta.write"], "Remove one duplicate read using the fixed efficiency principle.")


class SimulatedEvaluator:
    def evaluate(self, candidate, seed, repeat):
        # Fixed, clearly simulated values exercise selection without claiming a benchmark run.
        calls = len(candidate["steps"])
        return NumericObservation(
            candidate_id=candidate["candidate_id"],
            run_id="SIMULATED-" + uuid.uuid4().hex,
            score_0_10=8.0,
            tool_calls=calls,
            duration_seconds=round(0.1 * calls + repeat * 0.001, 4),
            status="simulated",
            seed=seed,
            simulated=True,
        )


SIMULATED_CHALLENGE = {
    "id": "simulated-task",
    "version": "SIMULATED",
    "name": "Composer plumbing simulation",
    "task": "Read one value and write one result.",
    "limits": {"wall_clock_seconds": 1, "tool_calls": 10},
    "capabilities": ["alpha.read", "beta.write"],
    "completion": "Return a simulated completion message.",
}
