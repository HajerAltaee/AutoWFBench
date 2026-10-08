from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autowfbench.composer.candidate_runtime import local_step, resolve
from autowfbench.composer.generator import child_prompt, initial_prompt
from autowfbench.composer.models import NumericObservation, structural_complexity, validate_candidate
from autowfbench.composer.n8n_validation import normalize_workflow_export, parse_workflow_json, validate_n8n_workflow
from autowfbench.composer.n8n_mcp_generator import _mcp_trace, mcp_prompt
from autowfbench.composer.n8n_composition import Structure, failure_category, structural_regression, workflow_structure
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


def native_workflow():
    return {
        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "name": "Generated test workflow",
        "nodes": [
            {"id": "11111111-1111-4111-8111-111111111111", "name": "Start", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [0, 0], "parameters": {}},
            {
                "id": "22222222-2222-4222-8222-222222222222", "name": "Read inquiry",
                "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [240, 0],
                "parameters": {
                    "method": "POST", "url": "={{ $env.AWB_ENV_BASE_URL + '/tools' }}",
                    "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Authorization", "value": "={{ 'Bearer ' + $env.AWB_ENV_ACCESS_TOKEN }}"}]},
                    "sendBody": True, "specifyBody": "json", "jsonBody": "={{ { operation: 'inquiry.read', arguments: {} } }}", "options": {},
                },
            },
            {
                "id": "33333333-3333-4333-8333-333333333333", "name": "Build Submission",
                "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": [480, 0],
                "parameters": {"mode": "raw", "jsonOutput": "={{ { protocol_version: '1.0', run_id: $env.AWB_RUN_ID, status: 'completed', final_answer: $('Read inquiry').first().json.ok, artifacts: [], trace: [] } }}", "options": {}},
            },
        ],
        "connections": {
            "Start": {"main": [[{"node": "Read inquiry", "type": "main", "index": 0}]]},
            "Read inquiry": {"main": [[{"node": "Build Submission", "type": "main", "index": 0}]]},
        },
        "settings": {"executionOrder": "v1"},
        "active": False,
    }


class ComposerTests(unittest.TestCase):
    def test_native_n8n_validation_accepts_supported_connected_workflow(self):
        challenge = {"capabilities": ["inquiry.read"]}
        self.assertEqual(validate_n8n_workflow(native_workflow(), challenge), [])

    def test_native_n8n_validation_rejects_dangling_disallowed_and_secret_config(self):
        value = native_workflow()
        value["connections"]["Start"]["main"][0][0]["node"] = "Missing"
        value["nodes"][1]["type"] = "n8n-nodes-base.executeCommand"
        value["nodes"][1]["parameters"]["apiKey"] = "literal-secret"
        codes = {issue.code for issue in validate_n8n_workflow(value, {"capabilities": ["inquiry.read"]})}
        self.assertTrue({"UNKNOWN_CONNECTION_TARGET", "DISALLOWED_NODE_TYPE", "EMBEDDED_SECRET"} <= codes)

    def test_native_n8n_json_parser_rejects_duplicate_keys(self):
        with self.assertRaises(ValueError):
            parse_workflow_json('{"name":"one","name":"two"}')

    def test_official_one_item_n8n_export_is_normalized(self):
        value = native_workflow()
        self.assertIs(normalize_workflow_export([value]), value)
        self.assertEqual(normalize_workflow_export([]), [])

    def test_official_n8n_mcp_prompt_and_trace_preserve_boundary(self):
        challenge = {
            "id": "crm", "version": "1", "name": "CRM", "task": "Public task",
            "limits": {}, "capabilities": ["inquiry.read", "crm.update", "followup.create"], "completion": "Return result",
        }
        prompt = mcp_prompt(challenge)
        self.assertIn("official n8n MCP", prompt)
        self.assertIn("HTTP 200 with\nok=false", prompt)
        self.assertIn("status='pending_scheduling'", prompt)
        self.assertIn("subject_to_assessment", prompt)
        self.assertNotIn("scorecard", json.dumps(challenge))
        events = "\n".join([
            json.dumps({"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "n8n", "tool": "validate_workflow", "status": "completed"}}),
            json.dumps({"type": "item.completed", "item": {"type": "command_execution", "command": "ignored"}}),
        ])
        self.assertEqual([item["tool"] for item in _mcp_trace(events)], ["validate_workflow"])

    def test_native_n8n_validation_accepts_official_export_metadata_and_ids(self):
        value = native_workflow()
        value["id"] = "G20KumTAqqgYTevq"
        value.update({"createdAt": "2026-10-07", "versionId": "version", "tags": [], "pinData": {}})
        self.assertEqual(validate_n8n_workflow(value, {"capabilities": ["inquiry.read"]}), [])

    def test_composition_strategy_detects_cycles_and_relative_regressions(self):
        value = native_workflow()
        value["connections"]["Build Submission"] = {"main": [[{"node": "Read inquiry", "type": "main", "index": 0}]]}
        issues = validate_n8n_workflow(value, {"capabilities": ["inquiry.read"]})
        self.assertIn("UNBOUNDED_CONTROL_FLOW", {issue.code for issue in issues})
        compact = workflow_structure(native_workflow())
        expanded = Structure(nodes=30, edges=35, branches=0, code_characters=100, retry_nodes=0, duplicate_shapes=20, cycles=0)
        self.assertTrue(structural_regression(compact, expanded, "execution_timeout", "execution_timeout"))
        self.assertFalse(structural_regression(compact, expanded, "validation", "completed"))
        self.assertEqual(failure_category([{"code": "N8N_EXECUTION_TIMEOUT", "message": "timed out"}]), "execution_timeout")

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
