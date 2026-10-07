"""Pinned native n8n runtime validation and fixed Solution API adapter."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from autowfbench.composer.n8n_validation import N8N_IMAGE
from autowfbench.core.common import HTTPError, JsonHandler, background_server, save_json
from autowfbench.core.contracts import validate


class N8nCliRuntime:
    """Use the pinned n8n image for both acceptance and benchmark execution."""

    def __init__(self, image=N8N_IMAGE, docker="docker", timeout=150, network=None, cleanup_timeout=15):
        self.image, self.docker, self.timeout = image, docker, timeout
        self.cleanup_timeout = cleanup_timeout
        self.network = network or os.environ.get("AWB_N8N_DOCKER_NETWORK")

    def _volume(self):
        return "awb-n8n-" + uuid.uuid4().hex

    def _common(self, volume):
        command = [
            self.docker, "run", "--rm", "--user", "root",
            "-e", "N8N_DIAGNOSTICS_ENABLED=false", "-e", "N8N_VERSION_NOTIFICATIONS_ENABLED=false",
            "-e", "N8N_RUNNERS_ENABLED=false", "-v", f"{volume}:/root/.n8n",
        ]
        if self.network:
            command += ["--network", self.network]
        return command

    def _create_volume(self, volume):
        subprocess.run([self.docker, "volume", "create", volume], check=True, capture_output=True, text=True)

    def _remove_volume(self, volume):
        return self._bounded_docker(["volume", "rm", "-f", volume])

    def _bounded_docker(self, arguments, timeout=None):
        started = time.monotonic()
        try:
            completed = subprocess.run(
                [self.docker, *arguments], capture_output=True, text=True,
                timeout=timeout or self.cleanup_timeout,
            )
            return {
                "duration_seconds": round(time.monotonic() - started, 3),
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "duration_seconds": round(time.monotonic() - started, 3),
                "returncode": None,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "timed_out": True,
            }

    def _import(self, workflow_path, volume):
        container = "awb-n8n-import-" + uuid.uuid4().hex[:20]
        command = [
            self.docker, "create", "--name", container, "--user", "root", "-e", "N8N_LOG_LEVEL=error",
            "-e", "N8N_DIAGNOSTICS_ENABLED=false", "-e", "N8N_RUNNERS_ENABLED=false",
            "-v", f"{volume}:/root/.n8n", self.image,
            "import:workflow", "--input=/tmp/workflow.json",
        ]
        try:
            created = subprocess.run(command, capture_output=True, text=True, timeout=30)
            if created.returncode:
                return created
            copied = subprocess.run([self.docker, "cp", str(workflow_path.resolve()), f"{container}:/tmp/workflow.json"], capture_output=True, text=True, timeout=30)
            if copied.returncode:
                return copied
            return subprocess.run([self.docker, "start", "-a", container], capture_output=True, text=True, timeout=self.timeout)
        finally:
            self._bounded_docker(["rm", "-f", container])

    def validate_import(self, workflow, attempt_dir):
        attempt_dir = Path(attempt_dir)
        attempt_dir.mkdir(parents=True, exist_ok=True)
        workflow_path = attempt_dir / "workflow.json"
        if not workflow_path.exists():
            save_json(workflow_path, workflow)
        volume = self._volume()
        try:
            self._create_volume(volume)
            completed = self._import(workflow_path, volume)
            (Path(attempt_dir) / "n8n-import.stdout.log").write_text(completed.stdout, encoding="utf-8")
            (Path(attempt_dir) / "n8n-import.stderr.log").write_text(completed.stderr, encoding="utf-8")
            if completed.returncode:
                message = (completed.stderr or completed.stdout)[-1200:].strip()
                return [{"code": "N8N_IMPORT_REJECTED", "path": "$", "message": message or "Pinned n8n runtime rejected the workflow"}]
            return []
        except (OSError, subprocess.TimeoutExpired) as exc:
            return [{"code": "N8N_IMPORT_FAILED", "path": "$", "message": f"{type(exc).__name__}: {exc}"}]
        finally:
            self._remove_volume(volume)

    def validate_execution(self, workflow, workflow_path, challenge):
        """Execute against public-contract stubs to catch config/runtime errors only."""
        allowed = set(challenge.get("capabilities", ()))
        requests, request_lock = [], threading.Lock()
        server = background_server(_public_tool_handler(allowed, requests, request_lock), host="0.0.0.0")
        host = os.environ.get("AWB_N8N_VALIDATION_HOST", "host.docker.internal")
        diagnostics_dir = Path(workflow_path).resolve().parent / "runtime-execution-diagnostics"
        try:
            request = {
                "run_id": "composer-validation-run",
                "workflow_id": workflow["id"],
                "environment": {"base_url": f"http://{host}:{server.server_port}", "access_token": "validation-only"},
            }
            self.execute(workflow_path, request, threading.Event(), diagnostics_dir=diagnostics_dir)
            return []
        except Exception as exc:
            return [{"code": "N8N_EXECUTION_REJECTED", "path": "$", "message": str(exc)[-1600:]}]
        finally:
            server.shutdown()
            server.server_close()
            with request_lock:
                snapshot = list(requests)
            diagnostics_dir.mkdir(parents=True, exist_ok=True)
            save_json(diagnostics_dir / "public-stub-requests.json", {
                "requests": snapshot,
                "operation_counts": dict(Counter(item.get("operation") for item in snapshot)),
            })

    def execute(self, workflow_path, request, cancelled, diagnostics_dir=None):
        volume = self._volume()
        container = "awb-n8n-exec-" + uuid.uuid4().hex[:20]
        diagnostics_dir = Path(diagnostics_dir).resolve() if diagnostics_dir else None
        timings, cleanup = {}, {}
        if diagnostics_dir:
            diagnostics_dir.mkdir(parents=True, exist_ok=True)
        total_started = time.monotonic()
        try:
            self._create_volume(volume)
            import_started = time.monotonic()
            imported = self._import(Path(workflow_path), volume)
            timings["import_seconds"] = round(time.monotonic() - import_started, 3)
            if imported.returncode:
                raise RuntimeError("Pinned n8n runtime rejected the previously validated workflow: " + (imported.stderr or imported.stdout)[-800:])
            command = self._common(volume) + [
                "--name", container,
                "-e", "N8N_LOG_LEVEL=debug",
                "-e", "N8N_BLOCK_ENV_ACCESS_IN_NODE=false",
                "-e", f"AWB_RUN_ID={request['run_id']}",
                "-e", f"AWB_ENV_BASE_URL={request['environment']['base_url']}",
                "-e", f"AWB_ENV_ACCESS_TOKEN={request['environment']['access_token']}",
                self.image, "execute", f"--id={request['workflow_id']}", "--rawOutput",
            ]
            stdout_path = diagnostics_dir / "n8n-execution.stdout.log" if diagnostics_dir else None
            stderr_path = diagnostics_dir / "n8n-execution.stderr.log" if diagnostics_dir else None
            stdout_parts, stderr_parts = [], []
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

            def drain(stream, destination, parts):
                handle = destination.open("w", encoding="utf-8") if destination else None
                try:
                    for line in iter(stream.readline, ""):
                        parts.append(line)
                        if handle:
                            handle.write(line)
                            handle.flush()
                finally:
                    if handle:
                        handle.close()

            readers = [
                threading.Thread(target=drain, args=(process.stdout, stdout_path, stdout_parts), daemon=True),
                threading.Thread(target=drain, args=(process.stderr, stderr_path, stderr_parts), daemon=True),
            ]
            for reader in readers:
                reader.start()
            started = time.monotonic()
            while process.poll() is None:
                if cancelled.is_set():
                    cleanup["container_stop"] = self._bounded_docker(["stop", "--time", "1", container])
                    raise RuntimeError("Cancelled")
                if time.monotonic() - started > self.timeout:
                    timings["n8n_execution_seconds"] = round(time.monotonic() - started, 3)
                    if diagnostics_dir:
                        cleanup["database_copy"] = self._bounded_docker([
                            "cp", f"{container}:/root/.n8n/database.sqlite",
                            str(diagnostics_dir / "database-timeout.sqlite"),
                        ])
                        cleanup["container_inspect"] = self._bounded_docker(["inspect", container])
                        save_json(diagnostics_dir / "pre-stop-diagnostics.json", {
                            "watchdog_seconds": self.timeout,
                            "timings": timings,
                            "container": container,
                            "volume": volume,
                            "stdout_tail": "".join(stdout_parts)[-8000:],
                            "stderr_tail": "".join(stderr_parts)[-8000:],
                            "cleanup_so_far": cleanup,
                        })
                    cleanup["container_stop"] = self._bounded_docker(["stop", "--time", "1", container])
                    raise RuntimeError("n8n execution timed out")
                time.sleep(0.1)
            timings["n8n_execution_seconds"] = round(time.monotonic() - started, 3)
            for reader in readers:
                reader.join(timeout=2)
            stdout, stderr = "".join(stdout_parts), "".join(stderr_parts)
            if process.returncode:
                raise RuntimeError("n8n execution failed: " + (stderr or stdout)[-1200:])
            result = _execution_json(stdout)
            result_data = result["data"]["resultData"]
            last = result_data["lastNodeExecuted"]
            runs = result_data["runData"][last]
            submission = runs[-1]["data"]["main"][0][0]["json"]
            validate("submission", submission)
            if submission["run_id"] != request["run_id"]:
                raise ValueError("Generated workflow returned the wrong run_id")
            return submission
        finally:
            cleanup["container_removal"] = self._bounded_docker(["rm", "-f", container])
            cleanup["volume_cleanup"] = self._remove_volume(volume)
            timings["total_seconds"] = round(time.monotonic() - total_started, 3)
            if diagnostics_dir:
                save_json(diagnostics_dir / "runtime-timings.json", {
                    "timings": timings,
                    "cleanup": cleanup,
                })


def _execution_json(stdout):
    decoder = json.JSONDecoder()
    for index, character in enumerate(stdout):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "data" in value and "status" in value:
            return value
    raise ValueError("Could not locate n8n execution JSON")


def _public_tool_handler(allowed, requests=None, request_lock=None):
    values = {
        "inquiry.read": {"lead_id": "lead-validation", "contact": "customer@example.test", "message": "Public validation inquiry"},
        "documents.read": {"service": "validation", "policy": "No unsupported commitments"},
        "research.read": {"company": "Validation Company", "authority": "authorized"},
        "customer.ask": {"budget_aed": 100000, "timeline_weeks": 8, "volume": 10000, "languages": ["Arabic", "English"], "crm": "Salesforce", "channel": "WhatsApp", "human_handoff": True},
        "crm.read": {"id": "lead-validation", "status": "Qualified", "budget_aed": 100000, "timeline_weeks": 8, "volume": 10000},
        "crm.update": {"id": "lead-validation", "status": "Qualified"},
        "followup.create": {"followup_id": "followup-validation"},
        "customer.send": {"sent": True},
        "incident.read": {"summary": "Checkout incident", "restriction": "smallest correction"},
        "source.read": {"content": "def checkout(amount, currency):\n    return charge_card(currency, amount)"},
        "checkout.patch": {"patched": True},
        "tests.run": {"passed": True, "cases": []},
    }

    class Handler(JsonHandler):
        def route(self, method):
            if method != "POST" or self.path != "/tools":
                raise HTTPError(404, "Not found")
            body = self.body()
            operation = body.get("operation")
            if requests is not None:
                entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "operation": operation,
                    "arguments": body.get("arguments"),
                }
                if request_lock:
                    with request_lock:
                        requests.append(entry)
                else:
                    requests.append(entry)
            if operation not in allowed:
                return self.send(200, {"ok": False, "error": {"code": "UNSUPPORTED", "message": "Not a public capability", "retryable": False}})
            return self.send(200, {"ok": True, "value": values.get(operation, {})})

    return Handler


def handler_for(workflow_path, runtime):
    """Task-independent benchmark adapter; workflow JSON owns all business logic."""
    workflow_path = Path(workflow_path).resolve()
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow_id = workflow["id"]
    jobs, lock = {}, threading.RLock()

    class Handler(JsonHandler):
        def route(self, method):
            if method == "POST" and self.path == "/runs":
                request = self.body()
                execution_id, cancel = uuid.uuid4().hex, threading.Event()
                with lock:
                    jobs[execution_id] = {"status": "running", "cancel": cancel}

                def work():
                    try:
                        submission = runtime.execute(workflow_path, {**request, "workflow_id": workflow_id}, cancel)
                    except Exception as exc:
                        submission = {
                            "protocol_version": "1.0", "run_id": request.get("run_id", "unknown"),
                            "status": "failed", "final_answer": f"{type(exc).__name__}: {exc}",
                            "artifacts": [], "trace": [],
                        }
                    with lock:
                        jobs[execution_id].update(status=submission["status"], submission=submission)

                threading.Thread(target=work, daemon=True).start()
                return self.send(202, {"execution_id": execution_id, "status": "running"})
            parts = self.path.strip("/").split("/")
            if len(parts) in (2, 3) and parts[0] == "runs":
                with lock:
                    job = jobs.get(parts[1])
                    if not job:
                        raise HTTPError(404, "Unknown execution")
                    if method == "POST" and len(parts) == 3 and parts[2] == "cancel":
                        job["cancel"].set()
                        return self.send(200, {"accepted": True})
                    if method == "GET" and len(parts) == 2:
                        return self.send(200, {key: value for key, value in job.items() if key != "cancel"})
            raise HTTPError(404, "Not found")

    return Handler
