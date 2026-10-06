from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autowfbench.composer.candidate_runtime import local_step, resolve
from autowfbench.composer.generator import child_prompt, initial_prompt
from autowfbench.composer.models import NumericObservation, structural_complexity, validate_candidate
from autowfbench.composer.search import ComposerSearch, select
from autowfbench.composer.simulation import SIMULATED_CHALLENGE, SimulatedEvaluator, SimulatedGenerator


def candidate(candidate_id="c000", strategy="initial", operations=("alpha.read",)):
    return {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "challenge_id": "simulated-task",
        "version": "0.1.0",
        "strategy": strategy,
        "hypothesis": "Exercise the fixed principles without evaluator feedback.",
        "steps": [
            {"id": f"step_{index}", "kind": "tool", "operation": operation, "arguments": {}, "save_as": f"result_{index}", "require_ok": True, "when": []}
            for index, operation in enumerate(operations)
        ],
        "final": {"answer": "Done", "artifacts": []},
    }


class ComposerTests(unittest.TestCase):
    def test_candidate_contract_is_strict_and_complexity_is_candidate_owned(self):
        value = candidate(operations=("alpha.read", "beta.write"))
        self.assertIs(validate_candidate(value, "simulated-task", "c000"), value)
        self.assertEqual(structural_complexity(value), 2)
        with self.assertRaises(ValueError):
            validate_candidate({**value, "scorecard": "forbidden"})
        broken = json.loads(json.dumps(value)); broken["steps"][0]["kind"] = "python"
        with self.assertRaises(ValueError):
            validate_candidate(broken)

    def test_declarative_runtime_resolves_refs_templates_and_regex_without_eval(self):
        context = {"source": {"value": {"content": "return charge_card(currency, amount)"}}}
        result = local_step("regex_extract", {
            "text": resolve({"$ref": "source.value.content"}, context),
            "pattern": r"return charge_card\((?P<first>\w+), (?P<second>\w+)\)",
        })
        context["patch"] = result
        self.assertTrue(result["ok"])
        self.assertEqual(resolve("${patch.value.second}, ${patch.value.first}", context), "amount, currency")
        with self.assertRaises(Exception):
            local_step("python", {"value": "import os"})

    def test_engine_result_projection_drops_all_hidden_evaluator_data(self):
        canary = "HIDDEN-EVALUATOR-CANARY-91A7"
        full_result = {
            "run_id": "run-real",
            "status": "complete",
            "score_0_10": 8.25,
            "tool_calls": 7,
            "duration_seconds": 1.5,
            "seed": 2,
            "deterministic_points": 6,
            "criteria": [{"question": canary, "reason": canary, "evidence_refs": [canary]}],
            "checks": {canary: True},
            "run_log": {"secret": canary},
            "scorecard": {"anchor": canary},
            "judge": {"reasoning": canary},
        }
        observation = NumericObservation.from_engine_result("c000", full_result)
        encoded = json.dumps(observation.as_dict(), sort_keys=True)
        self.assertNotIn(canary, encoded)
        self.assertEqual(set(observation.as_dict()), {
            "candidate_id", "run_id", "score_0_10", "tool_calls",
            "duration_seconds", "status", "seed", "simulated",
        })

    def test_hidden_canaries_cannot_enter_prompts_history_candidates_or_logs(self):
        canary = "HIDDEN-EVALUATOR-CANARY-4C2D"

        class RecordingGenerator:
            def __init__(self): self.prompt = None
            def initial(self, challenge, candidate_id):
                return candidate(candidate_id, "initial", ("alpha.read", "alpha.read", "beta.write"))
            def child(self, challenge, candidate_id, parent, history):
                # Attempt to smuggle non-allowlisted fields into prompt construction.
                poisoned = [{**history[-1], "judge_reason": canary, "scorecard": canary, "evidence": canary}]
                self.prompt = child_prompt(challenge, candidate_id, parent, poisoned)
                return candidate(candidate_id, "efficiency", ("alpha.read", "beta.write"))

        class ProjectingEvaluator:
            def evaluate(self, value, seed, repeat):
                full = {
                    "run_id": f"run-{value['candidate_id']}-{repeat}",
                    "status": "complete",
                    "score_0_10": 8.0,
                    "tool_calls": len(value["steps"]),
                    "duration_seconds": len(value["steps"]) / 10,
                    "seed": seed,
                    "criteria": [{"reason": canary}],
                    "checks": {canary: True},
                    "judge": {"raw": canary},
                }
                return NumericObservation.from_engine_result(value["candidate_id"], full)

        with tempfile.TemporaryDirectory() as directory:
            generator = RecordingGenerator()
            history = ComposerSearch(SIMULATED_CHALLENGE, generator, ProjectingEvaluator(), directory, iterations=2, repeats=2).run()
            written = "\n".join(path.read_text(encoding="utf-8") for path in Path(directory).rglob("*.json"))
        self.assertNotIn(canary, generator.prompt)
        self.assertNotIn(canary, json.dumps(history))
        self.assertNotIn(canary, written)
        self.assertTrue(history[-1]["accepted"])

    def test_initial_prompt_contains_public_inputs_not_benchmark_internals(self):
        prompt = initial_prompt(SIMULATED_CHALLENGE, "c000")
        self.assertIn("public_challenge", prompt)
        for forbidden in ("criterion_points", "deterministic_points", "evidence_refs", "HIDDEN-EVALUATOR-CANARY"):
            self.assertNotIn(forbidden, prompt)

    def test_selection_requires_repetition_for_equivalent_score_cost_claim(self):
        parent = {"aggregate": {"completion_rate": 1, "mean_score": 8, "attempts": 1, "median_tool_calls": 3, "median_duration_seconds": 1}, "structural_complexity": 3}
        child = {"aggregate": {"completion_rate": 1, "mean_score": 8, "attempts": 1, "median_tool_calls": 2, "median_duration_seconds": .5}, "structural_complexity": 2}
        accepted, reason = select(parent, child)
        self.assertFalse(accepted)
        self.assertIn("repeated measurements", reason)
        parent["aggregate"]["attempts"] = child["aggregate"]["attempts"] = 2
        accepted, reason = select(parent, child)
        self.assertTrue(accepted)
        self.assertIn("fewer median tool calls", reason)

    def test_simulated_search_is_explicit_and_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            history = ComposerSearch(SIMULATED_CHALLENGE, SimulatedGenerator(), SimulatedEvaluator(), directory, iterations=2, repeats=2).run()
            saved = json.loads((Path(directory) / "history.json").read_text())
        self.assertEqual([row["candidate_id"] for row in history], ["c000", "c001"])
        self.assertTrue(all(run["simulated"] for row in history for run in row["benchmark_runs"]))
        self.assertTrue(all(run["run_id"].startswith("SIMULATED-") for row in history for run in row["benchmark_runs"]))
        self.assertEqual(saved[-1]["optimization_strategy"], "efficiency")
        self.assertTrue(saved[-1]["accepted"])


if __name__ == "__main__":
    unittest.main()
