"""Run a reviewed Sapiens-authored n8n artifact against an isolated UI server.

This is a local development smoke test; it does not invoke Composer search,
benchmark scoring, or a judge. The existing n8n executor owns workflow execution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import threading
import time
from uuid import uuid4

from autowfbench.core.common import ROOT, save_json
from autowfbench.interfaces.composer.n8n import N8nRuntime


class NetworkRuntime(N8nRuntime):
    """Use the existing runner with a dedicated Docker network for this test."""
    def __init__(self, network):
        self.network = network
        super().__init__(docker_image="docker.n8n.io/n8nio/n8n:2.42.3")

    def _command(self, args, tmp, container_name):
        command = super()._command(args, tmp, container_name)
        command[2:2] = ["--network", self.network]
        return command


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, encoding="utf-8", stderr=subprocess.STDOUT, timeout=60).strip()


def check_structure(workflow):
    """Small development guard; production benchmark API validation is separate."""
    nodes = workflow.get("nodes", [])
    allowed = {"manualTrigger": 1, "set": 3.4, "httpRequest": 4.2, "code": 2, "if": 2.2}
    names = {node["name"] for node in nodes}
    if not {"Start", "Context", "Submit"} <= names or len(names) != len(nodes):
        raise ValueError("Expected unique Start, Context, Submit and business nodes")
    for node in nodes:
        kind = node["type"].removeprefix("n8n-nodes-base.")
        if node["type"] != "n8n-nodes-base." + kind or node["typeVersion"] != allowed.get(kind):
            raise ValueError("Unsupported native node")
        if any(node.get(key) for key in ("credentials", "disabled", "retryOnFail", "continueOnFail", "onError")):
            raise ValueError("Credentials, retries and error continuation are outside this smoke test")
        parameters = json.dumps(node["parameters"])
        if any(word in parameters for word in ("$env", "process.", "require(", "require (", "import(", "eval(", "Function(", "this.helpers", "getWorkflowStaticData")):
            raise ValueError("Unexpected code capability")
        if kind == "httpRequest":
            settings = node["parameters"]
            if settings.get("method", "GET") not in ("GET", "POST", "PATCH"):
                raise ValueError("Unexpected HTTP method")
            if "environment.base_url" not in settings.get("url", "") or "/api/contacts" not in settings["url"]:
                raise ValueError("HTTP must use the supplied SimSpot contacts URL")
    if workflow.get("pinData"):
        raise ValueError("Pinned data is not a live execution")


def run(args):
    workflow_path = ROOT / "development/simspot_ui/examples/sapiens-lead-flow.json"
    raw = workflow_path.read_bytes()
    workflow = json.loads(raw)
    check_structure(workflow)
    run_id = "sapiens-ui-" + uuid4().hex[:12]
    output = (args.output or ROOT / "runs" / run_id).resolve()
    output.mkdir(parents=True, exist_ok=False)
    network, container = run_id + "-net", run_id + "-server"
    origin = f"http://127.0.0.1:{args.port}"
    def contacts():
        # A separate HTTP client reads authoritative state, independently of n8n.
        # No published Windows port is needed on this internal Docker network.
        client = "import sys; from urllib.request import build_opener,ProxyHandler; print(build_opener(ProxyHandler({})).open(sys.argv[1], timeout=3).read().decode())"
        return json.loads(docker("exec", container, "python", "-c", client, origin + "/api/contacts"))

    runtime = NetworkRuntime(network)
    made_network = made_container = False
    try:
        docker("network", "create", "--internal", network)
        made_network = True
        docker("run", "-d", "--name", container, "--network", network,
               "--network-alias", "simspot",
               "autowfbench-simspot-ui:local", "python", "-m", "development.simspot_ui.server",
               "--bind", "0.0.0.0", "--port", str(args.port), "--store", "/data/smoke.sqlite3")
        made_container = True
        for attempt in range(20):
            try:
                before = contacts()
                break
            except (OSError, subprocess.CalledProcessError):
                if attempt == 19:
                    raise
                time.sleep(.5)
        save_json(output / "before.json", before)
        request = {
            "run_id": run_id,
            "environment": {"base_url": f"http://simspot:{args.port}", "access_token": secrets.token_urlsafe(24)},
            "limits": {"wall_clock_seconds": 120}, "ui_origin": origin,
            "lead": {"email": f"simspot.{run_id}@example.com", "first_name": "Nora", "last_name": "Vale"},
            "updates": {"job_title": "Founder", "lifecycle_stage": "Opportunity"},
        }
        submission = runtime.execute(workflow, request, threading.Event(), output / "n8n")
        after = contacts()
        matching = [c for c in after if c["email"] == request["lead"]["email"]]
        old_ids = {c["contact_id"] for c in before}
        checks = {
            "workflow_reported_completed": submission["status"] == "completed",
            "one_new_lead": len(after) == len(before) + 1 and len(matching) == 1,
            "requested_values_saved": len(matching) == 1 and all(matching[0][key] == value for key, value in {**request["lead"], **request["updates"]}.items()),
            "existing_contacts_unchanged": [c for c in after if c["contact_id"] in old_ids] == before,
        }
        save_json(output / "submission.json", submission)
        save_json(output / "after.json", after)
        summary = {"run_id": run_id, "scored": False, "workflow_sha256": hashlib.sha256(raw).hexdigest(),
                   "runtime": "n8n 2.42.3 in Docker", "checks": checks,
                   "contact": matching[0] if len(matching) == 1 else None}
        save_json(output / "summary.json", summary)
        print(json.dumps({"output": str(output), **summary}, indent=2))
        if not all(checks.values()):
            raise RuntimeError("Workflow completion did not match independent CRM readback")
    except Exception as error:
        save_json(output / "error.json", {"type": type(error).__name__, "message": str(error)})
        if made_container:
            try:
                save_json(output / "after.json", contacts())
            except (OSError, subprocess.CalledProcessError):
                pass
        raise
    finally:
        if made_container:
            docker("rm", "-f", container)
        if made_network:
            docker("network", "rm", network)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="Internal container port; never published")
    parser.add_argument("--output", type=Path)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
