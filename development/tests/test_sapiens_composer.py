"""CLI orchestration tests use fixtures, never a live model or benchmark judge."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autowfbench.interfaces.composer.search import generate
from autowfbench.runtime.environment.apps import catalog
from development.tools.smoke_sapiens_composer import local_pass, main


class SapiensComposerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / "sapiens4"
        self.script.touch()
        self.output = self.root / "candidate"
        self.public = {"apps":catalog("crm")}
        self.graph = {"name":"fixture", "nodes":[{"name":"Submit", "kind":"code",
            "operation":"", "code":"return [{json: {message: 'fixture'}}];",
            "expression":"", "next":[], "on_false":[]}]}
        env = patch.dict(os.environ, {"SAPIENS_CLI":str(self.script), "AWB_COMPOSER_PROVIDER":"sapiens",
            "SAPIENS4_URL":"http://127.0.0.1:4174", "AWB_TEST_SECRET":"do-not-forward"})
        env.start()
        self.addCleanup(env.stop)

    def reply(self, data, ok=True, code=0):
        return subprocess.CompletedProcess([], code, json.dumps({"schema_version":1, "ok":ok, "data":data, "error":None}))

    def accepted(self):
        return self.reply({"id":"turn-1", "agent":"chief-id", "status":"queued"})

    def completed(self):
        return self.reply({"id":"turn-1", "state":"Completed"})

    def save_graph(self, graph=None):
        (self.output / "response.json").write_text(json.dumps(graph or self.graph), encoding="utf-8")

    def successful_cli(self, command, **kwargs):
        self.assertNotIn("AWB_TEST_SECRET", kwargs["env"])
        self.assertFalse(kwargs.get("shell", False))
        if "chat" in command:
            self.assertIn("--sapi", command)
            self.assertEqual(command[-1], "chief")
            self.assertIn(str(self.output / "prompt.txt"), command[-3])
            self.assertNotIn('"operations"', command[-3])
            return self.accepted()
        self.assertEqual(command[-5:], ["conversation", "watch", "turn-1", "--sapi", "chief-id"])
        self.save_graph()
        return self.completed()

    def test_submit_watch_compile_and_cached_reuse(self):
        with patch("autowfbench.interfaces.composer.search.subprocess.run", side_effect=self.successful_cli) as run:
            workflow = generate(self.public, self.output)
            self.assertEqual(workflow["nodes"][-1]["name"], "Submit")
            self.assertEqual(generate(self.public, self.output), workflow)
        self.assertEqual(run.call_count, 2)
        provenance = json.loads((self.output / "provenance.json").read_text())
        self.assertEqual(provenance["provider"], "sapiens")
        self.assertEqual(provenance["turn_id"], "turn-1")

    def test_timeout_resumes_without_duplicate_submission(self):
        with patch("autowfbench.interfaces.composer.search.subprocess.run", side_effect=[self.accepted(), subprocess.TimeoutExpired("watch", 1)]):
            with self.assertRaisesRegex(RuntimeError, "host work may continue"):
                generate(self.public, self.output)
        with patch("autowfbench.interfaces.composer.search.subprocess.run", side_effect=self.successful_cli) as run:
            generate(self.public, self.output)
        self.assertEqual(run.call_count, 1)
        self.assertIn("watch", run.call_args.args[0])

    def test_ambiguous_submission_never_retried(self):
        with patch("autowfbench.interfaces.composer.search.subprocess.run", side_effect=subprocess.TimeoutExpired("chat", 1)) as run:
            with self.assertRaisesRegex(RuntimeError, "outcome unknown"):
                generate(self.public, self.output)
            with self.assertRaisesRegex(RuntimeError, "outcome is unknown"):
                generate(self.public, self.output)
        self.assertEqual(run.call_count, 1)

    def test_unparseable_submission_never_retried(self):
        with patch("autowfbench.interfaces.composer.search.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "not json")) as run:
            with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
                generate(self.public, self.output)
            with self.assertRaisesRegex(RuntimeError, "outcome is unknown"):
                generate(self.public, self.output)
        self.assertEqual(run.call_count, 1)

    def test_waiting_or_failed_turn_cannot_accept_early_artifact(self):
        for state, code in [("WaitingForInput", 5), ("Failed", 1), ("Unresolved", 1)]:
            with self.subTest(state=state):
                self.output = self.root / state
                def cli(command, **kwargs):
                    if "chat" in command:
                        return self.accepted()
                    self.save_graph()
                    return self.reply({"id":"turn-1", "state":state}, ok=False, code=code)
                with patch("autowfbench.interfaces.composer.search.subprocess.run", side_effect=cli):
                    with self.assertRaisesRegex(RuntimeError, "did not complete"):
                        generate(self.public, self.output)
                self.assertFalse((self.output / "workflow.json").exists())

    def test_wrong_turn_or_incomplete_state_rejected(self):
        for data in [{"id":"different", "state":"Completed"}, {"id":"turn-1", "state":"queued"}]:
            self.output = self.root / data["state"]
            with patch("autowfbench.interfaces.composer.search.subprocess.run", side_effect=[self.accepted(), self.reply(data)]):
                with self.assertRaisesRegex(RuntimeError, "not confirmed completion"):
                    generate(self.public, self.output)

    def test_completed_without_artifact_fails(self):
        with patch("autowfbench.interfaces.composer.search.subprocess.run", side_effect=[self.accepted(), self.completed()]):
            with self.assertRaisesRegex(RuntimeError, "without saving"):
                generate(self.public, self.output)

    def test_completed_graph_still_passes_standard_validation(self):
        self.graph["nodes"][0]["code"] = "return require('fs').readFileSync('/secret');"
        with patch("autowfbench.interfaces.composer.search.subprocess.run", side_effect=self.successful_cli):
            with self.assertRaises(ValueError):
                generate(self.public, self.output)

    def test_prompt_provider_and_host_changes_rejected(self):
        with patch("autowfbench.interfaces.composer.search.subprocess.run", side_effect=self.successful_cli) as run:
            generate(self.public, self.output)
            with self.assertRaisesRegex(ValueError, "different prompt"):
                generate({**self.public, "extra":"changed"}, self.output)
            with self.assertRaises(ValueError):
                generate(self.public, self.output, provider="codex")
            with patch.dict(os.environ, {"SAPIENS4_URL":"http://127.0.0.1:9999"}):
                with self.assertRaisesRegex(ValueError, "host, CLI or prompt changed"):
                    generate(self.public, self.output)
        self.assertEqual(run.call_count, 2)

    def test_orphaned_artifact_and_unknown_provider_rejected(self):
        self.output.mkdir()
        self.save_graph()
        with self.assertRaisesRegex(ValueError, "no Sapiens receipt"):
            generate(self.public, self.output)
        with self.assertRaisesRegex(ValueError, "must be codex or sapiens"):
            generate(self.public, self.output, provider="unknown")

    def test_codex_default_and_cache_are_preserved(self):
        def codex(command, **kwargs):
            self.assertEqual(command[:2], ["codex-fixture", "exec"])
            self.assertIn("--output-schema", command)
            self.assertNotIn("AWB_TEST_SECRET", kwargs["env"])
            self.save_graph()
            return subprocess.CompletedProcess(command, 0)
        with patch.dict(os.environ, {"AWB_COMPOSER_PROVIDER":"codex", "CODEX_BIN":"codex-fixture"}), \
             patch("autowfbench.interfaces.composer.search.subprocess.run", side_effect=codex) as run:
            workflow = generate(self.public, self.output)
            self.assertEqual(generate(self.public, self.output), workflow)
        self.assertEqual(run.call_count, 1)

    def test_smoke_requires_execution_and_all_deterministic_checks(self):
        row = {"status":"awaiting_llm_judge", "execution_pass":True, "score_0_10":None,
               "criteria":[{"evaluator":"deterministic", "answer":"yes"}, {"evaluator":"llm", "answer":None}]}
        self.assertTrue(local_pass({"runs":[row]}))
        self.assertFalse(local_pass({"runs":[]}))
        for override in [{"execution_pass":False}, {"score_0_10":8.5}, {"status":"engine_error"},
                         {"criteria":[]}, {"criteria":[{"evaluator":"llm", "answer":None}]},
                         {"criteria":[{"evaluator":"deterministic", "answer":"no"}]}]:
            self.assertFalse(local_pass({"runs":[{**row, **override}]}))

    def test_smoke_authors_only_unless_execute_explicit_and_never_judges(self):
        base = "development.tools.smoke_sapiens_composer."
        row = {"status":"awaiting_llm_judge", "execution_pass":True, "score_0_10":None,
               "criteria":[{"evaluator":"deterministic", "answer":"yes"}]}
        with patch(base + "public_input", return_value=self.public), \
             patch(base + "generate", return_value={"name":"fixture"}), \
             patch(base + "N8nRuntime"), patch(base + "evaluate", return_value=({"runs":[row]}, [])) as evaluate, \
             patch("builtins.print"):
            with patch("sys.argv", ["smoke", "--output", str(self.output)]):
                main()
            evaluate.assert_not_called()
            with patch("sys.argv", ["smoke", "--output", str(self.output), "--execute"]):
                main()
            self.assertIsNone(evaluate.call_args.kwargs["judge_model"])
            self.assertEqual(evaluate.call_args.args[2], [0])


if __name__ == "__main__":
    unittest.main()
