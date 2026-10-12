"""Unscored tests for the isolated local UI reconstruction."""
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest

from development.simspot_ui.contracts import InvalidInput
from development.simspot_ui.server import ASSETS, make_server
from development.simspot_ui.state import Store


class SimSpotUIStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.store = Store(self.path)

    def test_search_and_customer_filter_preserve_distinct_duplicate(self):
        self.assertEqual(len(self.store.contacts()), 6)
        self.assertEqual([c["contact_id"] for c in self.store.contacts("AISHA")], ["CONTACT-3000", "CONTACT-3001"])
        self.assertEqual(len(self.store.contacts("Harbor")), 2)
        self.assertEqual(len(self.store.contacts("simspot.a.noor.harbor@example.com")), 1)
        self.assertEqual([c["contact_id"] for c in self.store.contacts("Aisha", "Customer")], ["CONTACT-3000"])

    def test_example_sequence_persists_across_reopen_without_touching_duplicate(self):
        example = json.loads((ASSETS.parent / "replay-example.json").read_text(encoding="utf-8"))
        ident = example["contact_id"]
        duplicate = self.store.contact(example["unchanged_contact_id"])
        self.store.update(ident, example["identity"])
        note = self.store.create_activity(ident, "note", example["note"])
        task = self.store.create_activity(ident, "task", example["task"])
        reopened = Store(self.path)
        self.assertEqual(reopened.contact(ident)["job_title"], example["identity"]["job_title"])
        self.assertEqual(reopened.activities(ident), [task, note])
        self.assertEqual(reopened.contact(example["unchanged_contact_id"]), duplicate)
        self.assertEqual(reopened.activities(example["unchanged_contact_id"]), [])
        self.assertEqual(note["company_id"], "COMPANY-303")
        self.assertEqual(len(reopened.contacts()), 6)
        # No open SQLite connection should prevent Windows renaming/cleanup.
        renamed = self.path.with_name("renamed.sqlite3")
        self.path.rename(renamed)
        self.assertEqual(len(Store(renamed).contacts()), 6)

    def test_invalid_edits_are_atomic(self):
        before = self.store.contact("CONTACT-1001")
        for changes in ({"contact_id": "OTHER"}, {"email": "bad"}, {"email": "a@bad.example"},
                        {"email": "simspot.aisha.harbor@example.com"}, {"first_name": " "},
                        {"lifecycle_stage": "Invented"}, {"company_id": "COMPANY-303"}):
            with self.subTest(changes=changes), self.assertRaises(InvalidInput):
                self.store.update("CONTACT-1001", changes)
        self.assertEqual(self.store.contact("CONTACT-1001"), before)

    def test_new_lead_then_discovery_updates_persist(self):
        created = self.store.create_contact({"email": "new.lead@example.com", "first_name": "Nora", "last_name": "Vale"})
        ident = created["contact_id"]
        self.assertEqual((created["lifecycle_stage"], created["company_id"]), ("Lead", None))
        self.assertEqual(len(self.store.contacts("nora")), 1)
        self.store.update(ident, {"job_title": "Founder", "lifecycle_stage": "Opportunity"})
        note = self.store.create_activity(ident, "note", {"body": "Budget unclear. Confirm decision maker."})
        task = self.store.create_activity(ident, "task", {"title": "Clarify budget", "due_date": "2026-10-15"})
        reopened = Store(self.path)
        self.assertEqual(reopened.contact(ident)["job_title"], "Founder")
        self.assertEqual(reopened.contact(ident)["lifecycle_stage"], "Opportunity")
        self.assertEqual(reopened.activities(ident), [task, note])
        self.assertNotIn("company_id", note)
        self.assertNotIn("company_id", task)
        self.assertEqual(len(reopened.contacts()), 7)

    def test_new_lead_rejects_duplicate_and_bad_fields(self):
        self.store.create_contact({"email": "new.lead@example.com", "first_name": "Nora", "last_name": "Vale"})
        for payload in ({"email": "NEW.LEAD@example.com", "first_name": "Other", "last_name": "Person"},
                        {"email": "new.two@example.com", "first_name": " ", "last_name": "Person"},
                        {"email": "bad", "first_name": "Nora", "last_name": "Vale"},
                        {"email": "new.two@example.com", "first_name": "Nora", "last_name": "Vale", "stage": "Customer"}):
            with self.subTest(payload=payload), self.assertRaises(InvalidInput):
                self.store.create_contact(payload)
        self.assertEqual(len(self.store.contacts()), 7)

    def test_contact_only_note_and_optional_company_validation(self):
        ident = "CONTACT-1001"
        existing = self.store.create_activity(ident, "note", {"body": "Associated by default"})
        contact_only = self.store.create_activity(ident, "note", {"body": "Contact only", "include_company": False})
        self.assertEqual(existing["company_id"], "COMPANY-101")
        self.assertEqual(contact_only["contact_id"], ident)
        self.assertNotIn("company_id", contact_only)
        self.assertEqual(Store(self.path).activities(ident), [contact_only, existing])
        for invalid in ("false", 0, 1, None, [], {}):
            with self.subTest(invalid=invalid), self.assertRaises(InvalidInput):
                self.store.create_activity(ident, "note", {"body": "Invalid association", "include_company": invalid})
        self.assertEqual(self.store.activities(ident), [contact_only, existing])

    def test_contact_only_task_and_observed_default_time(self):
        payload = {"title": "Clarify budget", "due_date": "2026-10-15"}
        associated = self.store.create_activity("CONTACT-1001", "task", payload)
        contact_only = self.store.create_activity("CONTACT-1001", "task", {**payload, "include_company": False})
        self.assertEqual(associated["company_id"], "COMPANY-101")
        self.assertEqual(contact_only["due_time"], "08:00")
        self.assertNotIn("company_id", contact_only)
        self.assertEqual(Store(self.path).activities("CONTACT-1001"), [contact_only, associated])
        for invalid in ("false", 0, None, []):
            with self.subTest(invalid=invalid), self.assertRaises(InvalidInput):
                self.store.create_activity("CONTACT-1001", "task", {**payload, "include_company": invalid})

    def test_invalid_activities_leave_no_records(self):
        for kind, payload in [("note", {"body": " "}), ("note", {"body": "x" * 10001}),
                              ("task", {"title": "Task", "due_date": "2026-02-30"}),
                              ("task", {"title": "Task", "due_date": "2026-10-15", "task_type": {"bad": 1}}),
                              ("task", {"title": "Task", "due_date": "2026-10-15", "priority": []})]:
            with self.subTest(payload=payload), self.assertRaises(InvalidInput):
                self.store.create_activity("CONTACT-1001", kind, payload)
        self.assertEqual(self.store.activities("CONTACT-1001"), [])
        with self.assertRaises(KeyError):
            self.store.create_activity("MISSING", "note", {"body": "No orphan"})

    def test_user_text_is_data_and_client_has_no_html_injection_sink(self):
        malicious = '<img src=x onerror="alert(1)"><script>alert(2)</script>'
        self.store.update("CONTACT-1001", {"job_title": malicious})
        self.store.create_activity("CONTACT-1001", "note", {"body": malicious})
        self.assertEqual(Store(self.path).activities("CONTACT-1001")[0]["body"], malicious)
        script = (ASSETS / "app.js").read_text(encoding="utf-8")
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            self.assertNotIn(sink, script)
        self.assertIn("node.textContent = text", script)


class SimSpotUIHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "http.sqlite3")
        self.server = make_server(self.store, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, data=None, headers=None, raw=None):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            body = raw if raw is not None else json.dumps(data) if data is not None else None
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def good_headers(self):
        return {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{self.server.server_port}"}

    def test_http_save_and_readback(self):
        status, _, body = self.request("GET", "/api/contacts?q=Aisha")
        self.assertEqual((status, len(json.loads(body))), (200, 2))
        status, _, _ = self.request("PATCH", "/api/contacts/CONTACT-3000", {"job_title": "Director"}, self.good_headers())
        self.assertEqual(status, 200)
        status, _, _ = self.request("POST", "/api/contacts/CONTACT-3000/notes", {"body": "Persist me"}, self.good_headers())
        self.assertEqual(status, 201)
        status, _, body = self.request("GET", "/api/contacts/CONTACT-3000/activities")
        self.assertEqual(json.loads(body)[0]["body"], "Persist me")

    def test_http_create_update_and_readback(self):
        status, _, body = self.request("POST", "/api/contacts", {"email": "nora@example.com", "first_name": "Nora", "last_name": "Vale"}, self.good_headers())
        self.assertEqual(status, 201)
        ident = json.loads(body)["contact_id"]
        self.assertEqual(self.request("PATCH", f"/api/contacts/{ident}", {"job_title": "Founder"}, self.good_headers())[0], 200)
        self.assertEqual(self.request("POST", f"/api/contacts/{ident}/notes", {"body": "New details"}, self.good_headers())[0], 201)
        status, _, body = self.request("GET", f"/api/contacts/{ident}")
        self.assertEqual((status, json.loads(body)["job_title"]), (200, "Founder"))
        self.assertEqual(self.request("POST", "/api/contacts", {"email": "NORA@example.com", "first_name": "Duplicate", "last_name": "Vale"}, self.good_headers())[0], 400)

    def test_cross_origin_non_json_and_untrusted_host_are_rejected(self):
        good = self.good_headers()
        for headers, expected in [({"Content-Type": "application/json"}, 403),
                                  ({**good, "Origin": "https://attacker.invalid"}, 403),
                                  ({**good, "Content-Type": "text/plain"}, 415),
                                  ({**good, "Host": "attacker.invalid"}, 403)]:
            with self.subTest(headers=headers):
                status, response_headers, _ = self.request("POST", "/api/contacts/CONTACT-3000/notes", {"body": "Blocked"}, headers)
                self.assertEqual(status, expected)
                self.assertNotIn("Access-Control-Allow-Origin", response_headers)
        self.assertEqual(self.store.activities("CONTACT-3000"), [])

    def test_invalid_json_oversized_body_and_object_enum(self):
        status, _, _ = self.request("POST", "/api/contacts/CONTACT-3000/notes", headers=self.good_headers(), raw="{")
        self.assertEqual(status, 400)
        # Reject the declared length before a body is sent; unread trailing bytes
        # can cause Windows to reset an intentionally closed HTTP/1.0 socket.
        status, _, _ = self.request("POST", "/api/contacts/CONTACT-3000/notes", headers={**self.good_headers(), "Content-Length": "999999"}, raw="")
        self.assertEqual(status, 413)
        for bad in ({}, []):
            status, _, _ = self.request("POST", "/api/contacts/CONTACT-3000/tasks", {"title": "Task", "due_date": "2026-10-15", "task_type": bad}, self.good_headers())
            self.assertEqual(status, 400)

    def test_static_security_headers_and_no_path_traversal(self):
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Experimental SimSpot UI", body)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.request("GET", "/../state.py")[0], 404)


if __name__ == "__main__":
    unittest.main()
