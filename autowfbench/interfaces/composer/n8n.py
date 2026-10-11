"""Small native n8n adapter. Only the run context is injected, never business logic."""
import copy
import json
import os
import signal
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from autowfbench.core.common import save_json
from autowfbench.core.contracts import validate

VERSION = "2.42.3"
ALLOWED = {"manualTrigger": 1, "set": 3.4, "code": 2, "httpRequest": 4.2, "if": 2.2, "switch": 3.2, "merge": 3.2, "noOp": 1}


def validate_workflow(workflow, apps):
    nodes, connections = workflow["nodes"], workflow["connections"]
    if not 3 <= len(nodes) <= 60:
        raise ValueError("Expected 3..60 nodes")
    names = [n["name"] for n in nodes]
    ids = [n["id"] for n in nodes]
    if len(set(names)) != len(names) or len(set(ids)) != len(ids):
        raise ValueError("Duplicate node name or ID")
    if not {"Context", "Submit"} <= set(names):
        raise ValueError("Context and Submit nodes required")
    urls = {"={{ $('Context').first().json.environment.base_url + '" + op["path"] + "' }}" for op in apps["operations"]}
    starts = []
    for n in nodes:
        kind = n["type"].removeprefix("n8n-nodes-base.")
        if n["type"] != "n8n-nodes-base." + kind or kind not in ALLOWED or n["typeVersion"] != ALLOWED[kind]:
            raise ValueError("Unsupported node type/version: " + n["type"])
        if n.get("credentials") or n.get("disabled") or n.get("retryOnFail") or n.get("continueOnFail"):
            raise ValueError("Credentials, disabled nodes and automatic retries are not allowed")
        if kind == "manualTrigger":
            starts.append(n["name"])
        if n["name"] == "Context" and kind != "set":
            raise ValueError("Context must be Set v3.4")
        if kind == "httpRequest":
            p = n["parameters"]
            if p.get("url") not in urls or p.get("method") != "POST" or p.get("authentication", "none") != "none":
                raise ValueError("HTTP Request must POST to an exact documented simApp path")
            expected = [{"name": "Authorization", "value": "={{ 'Bearer ' + $('Context').first().json.environment.access_token }}"}]
            if p.get("headerParameters", {}).get("parameters") != expected:
                raise ValueError("HTTP Authorization must use Context.environment.access_token")
        content = json.dumps(n["parameters"])
        if any(word in content for word in ("$env", "process.", "require(", "require (", "import(", "eval(", "Function(", "this.helpers", "$execution", "$workflow", "getWorkflowStaticData")):
            raise ValueError("Nodes may only use their inputs and simApp HTTP nodes")
    if len(starts) != 1:
        raise ValueError("Exactly one Manual Trigger required")
    adjacency = {name:[] for name in names}
    for source, ports in connections.items():
        if source not in adjacency or set(ports) != {"main"}:
            raise ValueError("Unknown source or connection type")
        for branch in ports["main"]:
            for edge in branch:
                if edge["node"] not in adjacency or edge["type"] != "main" or edge["index"] != 0:
                    raise ValueError("Invalid edge")
                adjacency[source].append(edge["node"])
    if adjacency[starts[0]] != ["Context"]:
        raise ValueError("Manual Trigger must feed Context")
    seen, pending = set(), starts[:]
    while pending:
        node = pending.pop()
        if node not in seen:
            seen.add(node)
            pending.extend(adjacency[node])
    if seen != set(names) or adjacency["Submit"]:
        raise ValueError("All nodes must be reachable and Submit must be terminal")
    return workflow


class N8nRuntime:
    def __init__(self, binary=None, docker_image=None):
        self.docker_image = docker_image or (None if binary else os.environ.get("N8N_DOCKER_IMAGE"))
        self.binary = shutil.which("docker") if self.docker_image else binary or os.environ.get("N8N_BIN") or shutil.which("n8n")
        if not self.binary:
            raise ValueError("Set N8N_BIN to n8n@" + VERSION + " or N8N_DOCKER_IMAGE to its pinned image")
        version_command = [self.binary, "run", "--rm", self.docker_image, "--version"] if self.docker_image else [self.binary, "--version"]
        version = subprocess.check_output(version_command, text=True, timeout=120).strip()
        if version != VERSION:
            raise ValueError(f"Expected n8n {VERSION}; found {version}")

    def _runtime_request(self, request):
        request = copy.deepcopy(request)
        if not self.docker_image:
            return request
        parts = urlsplit(request["environment"]["base_url"])
        if parts.hostname not in ("127.0.0.1", "localhost", "::1"):
            return request
        host = "host.docker.internal" + ((":" + str(parts.port)) if parts.port else "")
        request["environment"]["base_url"] = urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
        return request

    def _command(self, args, tmp, container_name):
        if not self.docker_image:
            return [self.binary, *args]
        mapped = ["--input=/workspace/" + Path(arg.removeprefix("--input=")).name if arg.startswith("--input=") else arg for arg in args]
        settings = {
            "N8N_USER_FOLDER":"/workspace",
            "N8N_DIAGNOSTICS_ENABLED":"false",
            "N8N_VERSION_NOTIFICATIONS_ENABLED":"false",
            "N8N_LOG_LEVEL":"info",
            "N8N_BLOCK_ENV_ACCESS_IN_NODE":"true",
            "N8N_RUNNERS_BROKER_PORT":"5679",
            "N8N_COMMUNITY_PACKAGES_ENABLED":"false",
            "N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS":"false",
        }
        command = [self.binary, "run", "--rm", "--name", container_name, "-v", str(tmp.resolve()) + ":/workspace", "-w", "/workspace"]
        for key, value in settings.items():
            command.extend(("-e", key + "=" + value))
        return [*command, self.docker_image, *mapped]

    def execute(self, workflow, request, cancelled, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        token = request["environment"]["access_token"]
        timings = {}
        def redact(text):
            return text.replace(token, "[RUN_TOKEN]")
        workflow = copy.deepcopy(workflow)
        runtime_request = self._runtime_request(request)
        workflow.update(id="awbGeneratedWorkflow", active=False, settings={"executionOrder":"v1", "executionTimeout":request["limits"]["wall_clock_seconds"]})
        workflow.pop("pinData", None)
        for node in workflow["nodes"]:
            if node["name"] == "Context":
                node["parameters"] = {"mode":"raw", "jsonOutput":json.dumps(runtime_request), "options":{}}
            if node["type"] == "n8n-nodes-base.httpRequest":
                node["parameters"].setdefault("options", {}).update(timeout=10000, redirect={"redirect":{"followRedirects":False}})
        with tempfile.TemporaryDirectory(prefix="n8n-", dir=directory) as tmp:
            tmp = Path(tmp)
            save_json(tmp / "workflow.json", workflow)
            env = {k:os.environ[k] for k in ("PATH", "HOME", "TMPDIR") if k in os.environ}
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                broker_port = str(sock.getsockname()[1])
            env.update(N8N_USER_FOLDER=str(tmp), N8N_DIAGNOSTICS_ENABLED="false", N8N_VERSION_NOTIFICATIONS_ENABLED="false", N8N_LOG_LEVEL="info", N8N_BLOCK_ENV_ACCESS_IN_NODE="true", N8N_RUNNERS_BROKER_PORT=broker_port, N8N_COMMUNITY_PACKAGES_ENABLED="false", N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS="true")
            def command(args, name):
                started = time.monotonic()
                container_name = "awb-n8n-" + uuid.uuid4().hex[:16]
                # Separate process group ensures cancellation also stops task runners.
                with (tmp / "stdout").open("w+") as out, (tmp / "stderr").open("w+") as err:
                    proc = subprocess.Popen(self._command(args, tmp, container_name), cwd=tmp, env=env, stdout=out, stderr=err, start_new_session=True)
                    try:
                        while proc.poll() is None:
                            if cancelled.is_set() or time.monotonic()-started > request["limits"]["wall_clock_seconds"]:
                                raise TimeoutError("n8n cancelled or timed out")
                            time.sleep(.1)
                    finally:
                        if proc.poll() is None:
                            if self.docker_image:
                                subprocess.run([self.binary, "rm", "-f", container_name], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
                            if proc.poll() is None:
                                if os.name == "nt":
                                    proc.kill()
                                else:
                                    os.killpg(proc.pid, signal.SIGKILL)
                                proc.wait()
                        out.seek(0); err.seek(0)
                        stdout, stderr = out.read(), err.read()
                        (directory / (name+".stdout.log")).write_text(redact(stdout))
                        (directory / (name+".stderr.log")).write_text(redact(stderr))
                        timings[name+"_seconds"] = round(time.monotonic()-started, 3)
                        save_json(directory / "timings.json", timings)
                    if proc.returncode:
                        raise RuntimeError(redact((stdout+stderr)[-2500:]))
                    return stdout
            command(["import:workflow", "--input="+str(tmp / "workflow.json")], "import")
            stdout = command(["execute", "--id=awbGeneratedWorkflow", "--rawOutput"], "execute")
            decoder = json.JSONDecoder()
            for i,c in enumerate(stdout):
                if c != "{":
                    continue
                try:
                    result, _ = decoder.raw_decode(stdout[i:])
                except json.JSONDecodeError:
                    continue
                if isinstance(result, dict) and "data" in result and "status" in result:
                    break
            else:
                raise ValueError("No n8n execution result: " + redact(stdout[-2000:]))
            data = result["data"]["resultData"]
            if result["status"] != "success" or data.get("error") or data.get("lastNodeExecuted") != "Submit":
                raise ValueError("n8n did not reach Submit successfully: " + redact(json.dumps(data.get("error", data.get("lastNodeExecuted")))))
            items = data["runData"]["Submit"][-1]["data"]["main"][0]
            if len(items) != 1:
                raise ValueError("Submit must emit exactly one item")
            submission = validate("submission", items[0]["json"])
            if submission["run_id"] != request["run_id"]:
                raise ValueError("Submission run ID mismatch")
            return submission
