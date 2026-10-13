"""Negative checks for the independent mock-workflow acceptance oracle."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest

from development.simspot_ui.state import Store
from development.tools.smoke_sapiens_mock_leads import EXAMPLES, load_source, timestamp, verify_snapshot, workspace_lock
from development.tools.smoke_simspot_sapiens import check_structure


class MockLeadVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "crm.sqlite3")
        self.source = load_source(EXAMPLES / "mock-leads.json")
        self.now = timestamp(self.source["as_of"])
        self.before = self.snapshot()

    def snapshot(self):
        contacts = self.store.contacts()
        return {"contacts": contacts, "activities": {c["contact_id"]: self.store.activities(c["contact_id"]) for c in contacts}}

    def reference_state(self, now=None):
        """Build evaluator test data only; this is never the smoke workflow."""
        now = now or self.now
        for row in self.source["leads"]:
            existing = self.store.contacts(row["email"])
            contact = existing[0] if existing else self.store.create_contact({k: row[k] for k in ("email", "first_name", "last_name")})
            ident = contact["contact_id"]
            self.store.update(ident, {"job_title": row["job_title"]})
            self.store.create_activity(ident, "note", {"body": row["company"] + ": " + row["discovery_context"], "include_company": False})
            at = row["fixture_last_customer_message_utc"]
            if at:
                message = self.store.create_activity(ident, "message", {"source_id": row["lead_id"],
                    "body": row["fixture_last_customer_message_excerpt"], "received_at": at})
                if now - timestamp(at) > timedelta(hours=48):
                    self.store.create_activity(ident, "task", {"title": "Follow up with " + row["first_name"],
                        "body": message["body"], "due_date": now.date().isoformat(), "idempotency_key": row["lead_id"]})
        return self.snapshot()

    def test_fixture_and_expected_counts(self):
        result = verify_snapshot(self.before, self.reference_state(), self.source, self.now)
        self.assertTrue(all(result["checks"].values()), result)
        self.assertEqual((result["contacts"], result["contacts_added"], result["follow_up_tasks"]), (14, 8, 6))

    def test_duplicate_task_and_unrelated_mutation_fail(self):
        after = self.reference_state()
        ident = "CONTACT-1001"
        task = next(a for a in after["activities"][ident] if a["kind"] == "task")
        after["activities"][ident].append({**task, "activity_id": "duplicate"})
        next(c for c in after["contacts"] if c["contact_id"] == "CONTACT-2001")["job_title"] = "Unexpected change"
        result = verify_snapshot(self.before, after, self.source, self.now)
        self.assertFalse(result["checks"]["follow_up_selection"])
        self.assertFalse(result["checks"]["unrelated_state_preserved"])

    def test_latest_crm_message_overrides_old_source_message(self):
        self.reference_state()
        ident = "CONTACT-1001"
        self.store.create_activity(ident, "message", {"source_id": "newer-message", "body": "Customer replied today",
                                                   "received_at": self.now.isoformat()})
        result = verify_snapshot(self.before, self.snapshot(), self.source, self.now)
        self.assertNotIn("simspot.maya.orbitops@example.com", result["overdue_emails"])
        # The old task still present in this synthetic state fails selection.
        self.assertFalse(result["checks"]["follow_up_selection"])

    def test_internal_note_does_not_reset_clock(self):
        self.reference_state()
        self.store.create_activity("CONTACT-1001", "note", {"body": "Internal update written now"})
        result = verify_snapshot(self.before, self.snapshot(), self.source, self.now)
        self.assertIn("simspot.maya.orbitops@example.com", result["overdue_emails"])
        self.assertTrue(result["checks"]["follow_up_selection"])

    def test_exact_48_hour_boundary_and_no_message_are_skipped(self):
        now = timestamp("2026-10-13T09:00:00Z")
        after = self.reference_state(now)
        result = verify_snapshot(self.before, after, self.source, now)
        self.assertTrue(all(result["checks"].values()), result)
        self.assertNotIn("simspot.sofia.design@example.com", result["overdue_emails"])
        self.assertNotIn("simspot.daniel.new@example.com", result["overdue_emails"])
        later = verify_snapshot(self.before, after, self.source, now + timedelta(seconds=1))
        self.assertIn("simspot.sofia.design@example.com", later["overdue_emails"])
        self.assertFalse(later["checks"]["follow_up_selection"])

    def test_missing_message_duplicate_context_or_generic_followup_fails(self):
        after = self.reference_state()
        acts = after["activities"]["CONTACT-1001"]
        acts[:] = [a for a in acts if a["kind"] != "message"]
        note = next(a for a in acts if a["kind"] == "note")
        acts.append({**note, "activity_id": "another-note"})
        task = next(a for a in acts if a["kind"] == "task")
        task.update(title="Generic followup", body="Please contact us", idempotency_key="")
        result = verify_snapshot(self.before, after, self.source, self.now)
        for key in ("message_fixtures_saved_once", "context_notes_saved_once", "personalized_follow_ups", "stable_task_keys"):
            self.assertFalse(result["checks"][key], key)

    def test_mock_source_rejects_duplicate_email_and_half_message(self):
        for mutate in (lambda s: s["leads"][1].update(email=s["leads"][0]["email"].upper()),
                       lambda s: s["leads"][0].update(fixture_last_customer_message_excerpt="")):
            source = deepcopy(self.source)
            mutate(source)
            path = Path(self.temp.name) / "invalid.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_source(path)

    def test_workspace_lock_rejects_overlapping_run_and_releases(self):
        workspace = Path(self.temp.name) / "workspace"
        with workspace_lock(workspace):
            with self.assertRaises(FileExistsError):
                with workspace_lock(workspace):
                    self.fail("Overlapping run was admitted")
            self.assertTrue((workspace / ".run.lock").exists())
        self.assertFalse((workspace / ".run.lock").exists())

    def test_workflow_guard_accepts_reviewed_artifact(self):
        workflow = json.loads((EXAMPLES / "sapiens-mock-leads-flow.json").read_text(encoding="utf-8"))
        check_structure(workflow)
        node = next(n for n in workflow["nodes"] if n["name"] == "Set Job Title")
        original = deepcopy(node["parameters"])
        for change in ({"method": "={{ $json.method }}"}, {"method": "DELETE"},
                       {"sendBody": "={{ true }}"}, {"url": "https://example.com"}):
            node["parameters"] = {**original, **change}
            with self.assertRaises(ValueError):
                check_structure(workflow)


if __name__ == "__main__":
    unittest.main()
