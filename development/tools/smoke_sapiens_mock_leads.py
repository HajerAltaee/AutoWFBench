"""Execute a Sapiens-authored mock-source workflow and verify persistent CRM state.

The harness supplies source data and a clock, but all business mutations and
follow-up decisions belong to the authored n8n workflow. No judge is invoked.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
from uuid import uuid4

from autowfbench.core.common import ROOT, save_json
from development.simspot_ui.contracts import new_contact
from development.tools.smoke_simspot_sapiens import NetworkRuntime, check_structure, docker

EXAMPLES = ROOT / "development/simspot_ui/examples"
TOPICS = {"LEAD-001": ("budget",), "LEAD-003": ("notes", "privacy", "names"),
          "LEAD-005": ("pilot",), "LEAD-006": ("interview",),
          "LEAD-007": ("arabic", "english"), "LEAD-008": ("company", "rollout"),
          "LEAD-010": ("consent",), "LEAD-002": ("team",), "LEAD-004": ("procurement",)}


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("A timezone-aware timestamp is required")
    return result.astimezone(timezone.utc)


def load_source(path):
    source = json.loads(Path(path).read_text(encoding="utf-8"))
    if len(source["leads"]) != 10:
        raise ValueError("This smoke fixture requires ten leads")
    emails, ids = set(), set()
    for row in source["leads"]:
        new_contact({k: row[k] for k in ("email", "first_name", "last_name")})
        email = row["email"].strip().casefold()
        if email in emails or row["lead_id"] in ids:
            raise ValueError("Source lead IDs and emails must be unique")
        emails.add(email)
        ids.add(row["lead_id"])
        at, body = row["fixture_last_customer_message_utc"], row["fixture_last_customer_message_excerpt"]
        if bool(at) != bool(body):
            raise ValueError("A fixture message needs both timestamp and text")
        if at:
            timestamp(at)
    timestamp(source["as_of"])
    return source


def verify_snapshot(before, after, source, now):
    """Independent readback oracle; never writes CRM or trusts workflow prose."""
    rows = source["leads"]
    source_emails = {row["email"].casefold() for row in rows}
    contacts = after["contacts"]
    emails = [c["email"].casefold() for c in contacts]
    baseline = {c["contact_id"]: c for c in before["contacts"]}
    checks = {"unique_emails": len(emails) == len(set(emails)),
              "exact_contact_set": set(emails) == source_emails | {c["email"].casefold() for c in before["contacts"]},
              "source_values_saved": True, "message_fixtures_saved_once": True,
              "context_notes_saved_once": True, "follow_up_selection": True,
              "personalized_follow_ups": True, "stable_task_keys": True,
              "existing_identity_preserved": True, "unrelated_state_preserved": True}
    due_emails, task_count = [], 0
    for contact in contacts:
        ident = contact["contact_id"]
        if ident in baseline:
            old = baseline[ident]
            checks["existing_identity_preserved"] &= all(contact[k] == old[k] for k in
                ("email", "first_name", "last_name", "lifecycle_stage", "company_id", "company_name"))
            if contact["email"].casefold() not in source_emails:
                checks["unrelated_state_preserved"] &= contact == old and after["activities"][ident] == before["activities"][ident]
    for row in rows:
        matching = [c for c in contacts if c["email"].casefold() == row["email"].casefold()]
        if len(matching) != 1:
            checks["source_values_saved"] = False
            continue
        contact = matching[0]
        acts = after["activities"][contact["contact_id"]]
        checks["source_values_saved"] &= contact["job_title"] == row["job_title"]
        messages = [a for a in acts if a["kind"] == "message"]
        expected_at = row["fixture_last_customer_message_utc"]
        if expected_at:
            matching_messages = [m for m in messages if m["body"] == row["fixture_last_customer_message_excerpt"]
                                 and timestamp(m["received_at"]) == timestamp(expected_at)]
            checks["message_fixtures_saved_once"] &= len(matching_messages) == 1
        else:
            checks["message_fixtures_saved_once"] &= not messages
        checks["message_fixtures_saved_once"] &= len({m["source_id"] for m in messages}) == len(messages)
        notes = [a for a in acts if a["kind"] == "note" and row["discovery_context"] in a["body"] and row["company"] in a["body"]]
        checks["context_notes_saved_once"] &= len(notes) == 1 and "company_id" not in notes[0]
        latest = max(messages, key=lambda m: timestamp(m["received_at"]), default=None)
        due = latest is not None and now - timestamp(latest["received_at"]) > timedelta(hours=48)
        tasks = [a for a in acts if a["kind"] == "task"]
        task_count += len(tasks)
        checks["follow_up_selection"] &= len(tasks) == int(due)
        if due:
            due_emails.append(row["email"])
        for task in tasks:
            content = (task["title"] + " " + task["body"]).casefold()
            topics = TOPICS.get(row["lead_id"], ())
            checks["personalized_follow_ups"] &= contact["first_name"].casefold() in content and (not topics or any(t in content for t in topics))
            checks["stable_task_keys"] &= bool(task.get("idempotency_key"))
    return {"checks": checks, "contacts": len(contacts), "contacts_added": len(contacts) - len(before["contacts"]),
            "overdue_emails": due_emails, "follow_up_tasks": task_count}


@contextmanager
def workspace_lock(workspace):
    workspace.mkdir(parents=True, exist_ok=True)
    lock = workspace / ".run.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock.unlink()


def snapshot(container, origin):
    client = """import json,sys
from urllib.request import build_opener,ProxyHandler
opener=build_opener(ProxyHandler({}))
def get(path):
    return json.load(opener.open(sys.argv[1]+path,timeout=5))
contacts=get('/api/contacts')
print(json.dumps({'contacts':contacts,'activities':{c['contact_id']:get('/api/contacts/'+c['contact_id']+'/activities') for c in contacts}}))
"""
    return json.loads(docker("exec", container, "python", "-c", client, origin))


def wait_snapshot(container, origin):
    for attempt in range(20):
        try:
            return snapshot(container, origin)
        except Exception:
            if attempt == 19:
                raise
            time.sleep(.5)


def run(args):
    source = load_source(args.source)
    now = datetime.now(timezone.utc) if args.current_time else timestamp(args.now or source["as_of"])
    raw = args.workflow.read_bytes()
    workflow = json.loads(raw)
    check_structure(workflow)
    workspace = args.workspace.resolve()
    with workspace_lock(workspace):
        state = workspace / "state"
        state.mkdir(exist_ok=True)
        run_id = "sapiens-mock-" + uuid4().hex[:12]
        output = workspace / run_id
        output.mkdir()
        save_json(output / "source.json", source)
        network, container = run_id + "-net", run_id + "-server"
        origin = "http://127.0.0.1:8765"
        made_network = made_container = False
        try:
            runtime = NetworkRuntime(network)
            docker("network", "create", "--internal", network)
            made_network = True
            docker("run", "-d", "--name", container, "--network", network, "--network-alias", "simspot",
                   "-v", str(state) + ":/data", "autowfbench-simspot-ui:local", "python", "-m",
                   "development.simspot_ui.server", "--bind", "0.0.0.0", "--port", "8765", "--store", "/data/mock.sqlite3")
            made_container = True
            before = wait_snapshot(container, origin)
            save_json(output / "before.json", before)
            summaries, previous = [], None
            for cycle in range(1, args.repeat + 1):
                request = {"run_id": f"{run_id}-{cycle}",
                           "environment": {"base_url": "http://simspot:8765", "access_token": secrets.token_urlsafe(24)},
                           "limits": {"wall_clock_seconds": 180}, "ui_origin": origin,
                           "now": now.isoformat(), "source": {k: source[k] for k in ("source_name", "leads")}}
                directory = output / f"cycle-{cycle}"
                submission = runtime.execute(workflow, request, threading.Event(), directory / "n8n")
                after = snapshot(container, origin)
                result = verify_snapshot(before, after, source, now)
                result["checks"]["workflow_completed"] = submission["status"] == "completed"
                if previous is not None:
                    result["checks"]["repeat_state_identical"] = previous == after
                save_json(directory / "submission.json", submission)
                save_json(directory / "after.json", after)
                save_json(directory / "verification.json", result)
                summaries.append(result)
                if not all(result["checks"].values()):
                    raise RuntimeError("Independent CRM verification failed: " + json.dumps(result))
                previous = after
                if cycle < args.repeat:
                    docker("restart", container)
                    if wait_snapshot(container, origin) != after:
                        raise RuntimeError("CRM state changed across server restart")
            summary = {"run_id": run_id, "scored": False, "source_kind": "local mock file",
                       "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
                       "workflow_sha256": hashlib.sha256(raw).hexdigest(), "now": now.isoformat(),
                       "cycles": summaries, "state_file": str(state / "mock.sqlite3")}
            save_json(output / "summary.json", summary)
            print(json.dumps({"output": str(output), **summary}, indent=2))
            return summary
        except Exception as error:
            save_json(output / "error.json", {"type": type(error).__name__, "message": str(error)})
            if made_container:
                try:
                    save_json(output / "failure-state.json", snapshot(container, origin))
                except Exception:
                    pass
            raise
        finally:
            if made_container:
                docker("rm", "-f", container)
            if made_network:
                docker("network", "rm", network)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=EXAMPLES / "mock-leads.json")
    parser.add_argument("--workflow", type=Path, default=EXAMPLES / "sapiens-mock-leads-flow.json")
    parser.add_argument("--workspace", type=Path, default=ROOT / "runs/sapiens-mock-workspace")
    parser.add_argument("--repeat", type=int, choices=(1, 2), default=2)
    clock = parser.add_mutually_exclusive_group()
    clock.add_argument("--now", help="ISO timestamp; default is source.as_of")
    clock.add_argument("--current-time", action="store_true", help="Use real UTC time for a scheduled occurrence")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
