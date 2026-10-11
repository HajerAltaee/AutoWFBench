import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fastjsonschema

from autowfbench.core.contracts import load_challenge
from autowfbench.core.common import background_server
from autowfbench.interfaces.solution import handler_for, solve
from autowfbench.runtime.engine import Engine
from autowfbench.runtime.environment.apps import catalog
from autowfbench.runtime.environment.state import ChallengeEnvironment


CHALLENGE = "simspot-customer-discovery"


def reference(seed):
    env = ChallengeEnvironment(load_challenge(CHALLENGE), seed)

    def http(_url, data, _token):
        return env.execute(data["operation"], data["arguments"])

    request = {"challenge": {"id": CHALLENGE}, "run_id": f"test-{seed}", "environment": {"base_url": "", "access_token": ""}}
    with patch("autowfbench.interfaces.solution.http_json", side_effect=http):
        submission = solve(request)
    return env, submission


class SimSpotCustomerDiscoveryTests(unittest.TestCase):
    def test_five_cases_define_start_revelations_questions_updates_and_completion(self):
        cases = load_challenge(CHALLENGE)["environment"]["fixtures"]["cases"]
        self.assertEqual([case["id"] for case in cases], [
            "interested-founder-unclear-budget",
            "enterprise-non-decision-maker",
            "existing-duplicate-customer",
            "privacy-conscious-customer",
            "high-value-changing-requirements",
        ])
        for case in cases:
            with self.subTest(case=case["id"]):
                for field in ("starting_contacts", "information_revealed", "questions", "expected_changes", "completion_criteria", "sapiens_routine"):
                    self.assertTrue(case[field], field)
                self.assertEqual(case["sapiens_routine"]["minutes"], 1440)
                self.assertIn(case["id"], case["sapiens_routine"]["prompt"])

    def test_catalog_exports_valid_simspot_results(self):
        env = ChallengeEnvironment(load_challenge(CHALLENGE), 0)
        schemas = {op["operation"]: fastjsonschema.compile(op["result"]) for op in catalog("simspot")["operations"]}
        schemas["inquiry.read"](env.execute("inquiry.read", {})["value"])
        schemas["discovery.guide.read"](env.execute("discovery.guide.read", {})["value"])
        schemas["contacts.search"](env.execute("contacts.search", {"company_id": "COMPANY-101"})["value"])
        schemas["customer.ask"](env.execute("customer.ask", {"topics": ["budget"]})["value"])

    def test_reference_completes_all_customer_discovery_cases(self):
        for seed in range(5):
            with self.subTest(seed=seed):
                env, submission = reference(seed)
                evidence = env.finalize()
                self.assertTrue(all(evidence["checks"].values()), evidence["checks"])
                self.assertEqual(submission["status"], "completed")
                self.assertNotIn("access_token", submission["final_answer"])

    def test_simspot_runs_through_real_autowfbench_http_on_windows(self):
        solution = background_server(handler_for())
        self.addCleanup(solution.server_close)
        self.addCleanup(solution.shutdown)
        manifest = {"id": "simspot-reference", "name": "SimSpot reference", "version": "0.1.0", "endpoint": f"http://127.0.0.1:{solution.server_port}", "runtime": "scripted-reference", "description": "local integration fixture", "auth_env": ""}
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(Path(directory))
            run_id = engine.submit(CHALLENGE, manifest, seed=4, background=False)
            result = engine.read(run_id)
        self.assertEqual(result["status"], "awaiting_llm_judge")
        self.assertEqual(result["deterministic_points"], 8)
        self.assertTrue(result["execution_pass"])

    def test_existing_customer_updates_canonical_record_only(self):
        env, _ = reference(2)
        original_duplicate = copy.deepcopy(env.initial["contacts"][1])
        evidence = env.finalize()
        canonical = next(c for c in evidence["final"]["contacts"] if c["contact_id"] == "CONTACT-3000")
        duplicate = next(c for c in evidence["final"]["contacts"] if c["contact_id"] == "CONTACT-3001")
        self.assertEqual(canonical["discovery_status"], "ExistingCustomerExpansion")
        self.assertEqual(duplicate, original_duplicate)

    def test_updating_duplicate_record_fails_duplicate_and_outcome_checks(self):
        env = ChallengeEnvironment(load_challenge(CHALLENGE), 2)
        case = env.case
        env.execute("contacts.search", {"email": case["inquiry"]["email"], "company_id": case["inquiry"]["company_id"]})
        env.execute("customer.ask", {"topics": case["required_topics"]})
        env.execute("customer.ask", {"topics": ["requirements_confirmation"]})
        env.execute("contact.update", {"contact_id": case["inquiry"]["incoming_contact_id"], "changes": case["expected_changes"], "idempotency_key": "wrong-record"})
        env.execute("contact.read", {"contact_id": case["inquiry"]["incoming_contact_id"]})
        checks = env.finalize()["checks"]
        self.assertFalse(checks["duplicate_handled"])
        self.assertFalse(checks["correct_contact"])

    def test_privacy_case_rejects_narrative_storage(self):
        env = ChallengeEnvironment(load_challenge(CHALLENGE), 3)
        result = env.execute("contact.update", {"contact_id": "CONTACT-4001", "changes": {"discovery_summary": "raw transcript"}, "idempotency_key": "privacy"})
        self.assertFalse(result["ok"])
        self.assertEqual(env.state["contacts"], env.initial["contacts"])

    def test_privacy_case_requires_consent_question(self):
        env = ChallengeEnvironment(load_challenge(CHALLENGE), 3)
        case = env.case
        env.execute("contacts.search", {"company_id": case["inquiry"]["company_id"]})
        topics = [topic for topic in case["required_topics"] if topic != "data_consent"]
        env.execute("customer.ask", {"topics": topics})
        env.execute("customer.ask", {"topics": ["requirements_confirmation"]})
        env.execute("contact.update", {"contact_id": case["expected_target"], "changes": case["expected_changes"], "idempotency_key": "no-consent"})
        env.execute("contact.read", {"contact_id": case["expected_target"]})
        self.assertFalse(env.finalize()["checks"]["privacy_respected"])

    def test_changed_requirements_need_separate_confirmation(self):
        env = ChallengeEnvironment(load_challenge(CHALLENGE), 4)
        case = env.case
        env.execute("contacts.search", {"company_id": case["inquiry"]["company_id"]})
        facts = env.execute("customer.ask", {"topics": case["required_topics"]})["value"]
        changes = copy.deepcopy(case["expected_changes"])
        changes["needs"] = facts["needs"]
        changes["requirements_revision"] = facts["requirements_revision"]
        env.execute("contact.update", {"contact_id": case["expected_target"], "changes": changes, "idempotency_key": "stale"})
        env.execute("contact.read", {"contact_id": case["expected_target"]})
        self.assertFalse(env.finalize()["checks"]["latest_requirements"])

    def test_confirmation_topic_in_initial_batch_is_not_a_separate_round(self):
        env = ChallengeEnvironment(load_challenge(CHALLENGE), 4)
        case = env.case
        env.execute("contacts.search", {"company_id": case["inquiry"]["company_id"]})
        env.execute("customer.ask", {"topics": [*case["required_topics"], "requirements_confirmation"]})
        env.execute("contact.update", {"contact_id": case["expected_target"], "changes": case["expected_changes"], "idempotency_key": "one-round"})
        env.execute("contact.read", {"contact_id": case["expected_target"]})
        self.assertFalse(env.finalize()["checks"]["latest_requirements"])


if __name__ == "__main__":
    unittest.main()
