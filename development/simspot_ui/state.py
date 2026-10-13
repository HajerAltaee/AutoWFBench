"""Persistent fictional CRM state. No browser, HTTP, or benchmark dependencies."""
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import uuid

from .contracts import activity, contact_changes, new_contact, InvalidInput


SEED_CONTACTS = (
    ("CONTACT-1001", "Maya", "Rahman", "simspot.maya.orbitops@example.com", "OrbitOps", "Lead"),
    ("CONTACT-2001", "Liam", "Chen", "simspot.liam.northstar@example.com", "Northstar", "Lead"),
    ("CONTACT-3000", "Aisha", "Noor", "simspot.aisha.harbor@example.com", "Harbor", "Customer"),
    ("CONTACT-3001", "Aisha", "Noor", "simspot.a.noor.harbor@example.com", "Harbor", "Lead"),
    ("CONTACT-4001", "Elena", "Rossi", "simspot.elena.medaxis@example.com", "MedAxis", "Lead"),
    ("CONTACT-5001", "Omar", "Haddad", "simspot.omar.quantum@example.com", "Quantum", "Lead"),
)
COMPANIES = tuple({"company_id": f"COMPANY-{n}", "name": name} for n, name in (
    (101, "OrbitOps"), (202, "Northstar"), (303, "Harbor"), (404, "MedAxis"), (505, "Quantum")))


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS contacts (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS activities (
                    id TEXT PRIMARY KEY, contact_id TEXT NOT NULL REFERENCES contacts(id),
                    kind TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL);
            """)
            if not db.execute("SELECT value FROM metadata WHERE key='seeded'").fetchone():
                for ident, first, last, email, company, stage in SEED_CONTACTS:
                    record = {"contact_id": ident, "first_name": first, "last_name": last,
                              "email": email, "company_id": next(c["company_id"] for c in COMPANIES if c["name"] == company),
                              "company_name": company, "lifecycle_stage": stage, "job_title": ""}
                    db.execute("INSERT INTO contacts VALUES (?, ?)", (ident, json.dumps(record)))
                db.execute("INSERT INTO metadata VALUES ('seeded', '1')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def contacts(self, query="", stage=""):
        with self.connect() as db:
            records = [json.loads(row[0]) for row in db.execute("SELECT payload FROM contacts ORDER BY id")]
        query = query.strip().casefold()
        return [c for c in records if (not stage or c["lifecycle_stage"] == stage) and
                query in " ".join(c[k] for k in ("first_name", "last_name", "email", "company_name")).casefold()]

    def contact(self, ident):
        with self.connect() as db:
            return self._contact(db, ident)

    def create_contact(self, payload):
        values = new_contact(payload)
        record = {"contact_id": f"CONTACT-{uuid.uuid4().hex}", **values,
                  "company_id": None, "company_name": "", "lifecycle_stage": "Lead", "job_title": ""}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if any(json.loads(row[0])["email"].casefold() == values["email"].casefold()
                   for row in db.execute("SELECT payload FROM contacts")):
                raise InvalidInput("Another contact already uses this email")
            db.execute("INSERT INTO contacts VALUES (?, ?)", (record["contact_id"], json.dumps(record)))
        return record

    @staticmethod
    def _contact(db, ident):
        row = db.execute("SELECT payload FROM contacts WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise KeyError("Contact not found")
        return json.loads(row[0])

    def update(self, ident, payload):
        changes = contact_changes(payload)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            record = self._contact(db, ident)
            if "email" in changes:
                others = [json.loads(r[0]) for r in db.execute("SELECT payload FROM contacts WHERE id<>?", (ident,))]
                if any(c["email"].casefold() == changes["email"].casefold() for c in others):
                    raise InvalidInput("Another contact already uses this email")
            record.update(changes)
            db.execute("UPDATE contacts SET payload=? WHERE id=?", (json.dumps(record), ident))
        return self.contact(ident)

    def activities(self, ident):
        with self.connect() as db:
            self._contact(db, ident)
            return [{"activity_id": row[0], "kind": row[1], "created_at": row[2], **json.loads(row[3])}
                    for row in db.execute("SELECT id,kind,created_at,payload FROM activities WHERE contact_id=? ORDER BY rowid DESC", (ident,))]

    def customer_messages(self, ident):
        """Only customer-authored inbound messages count toward follow-up recency."""
        return sorted((item for item in self.activities(ident) if item["kind"] == "message"),
                      key=lambda item: item["received_at"], reverse=True)

    def create_activity(self, ident, kind, payload):
        if kind not in ("note", "task", "message"):
            raise InvalidInput("Unsupported activity")
        values = activity(payload, kind)
        aid, created = str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            record = self._contact(db, ident)
            key_field = "source_id" if kind == "message" else "idempotency_key" if kind == "task" else None
            if key_field and key_field in values:
                for row in db.execute("SELECT id,created_at,payload FROM activities WHERE contact_id=? AND kind=?", (ident, kind)):
                    previous = json.loads(row[2])
                    if previous.get(key_field) == values[key_field]:
                        if kind == "message" and any(previous[field] != values[field] for field in ("body", "received_at")):
                            raise InvalidInput("Source ID already refers to a different message")
                        if kind == "task" and any(previous.get(field) != value for field, value in values.items() if field != "include_company"):
                            raise InvalidInput("Idempotency key already refers to a different task")
                        return {"activity_id": row[0], "kind": kind, "created_at": row[1], **previous}
            include_company = values.pop("include_company", kind != "message")
            values["contact_id"] = ident
            if include_company and record["company_id"]:
                values["company_id"] = record["company_id"]
            db.execute("INSERT INTO activities VALUES (?,?,?,?,?)", (aid, ident, kind, created, json.dumps(values)))
        return {"activity_id": aid, "kind": kind, "created_at": created, **values}
