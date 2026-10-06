"""Stable interpreter and Solution API for constrained generated candidates."""
from __future__ import annotations

import argparse
import json
import re
import threading
import uuid
from http.server import ThreadingHTTPServer

from autowfbench.composer.models import validate_candidate
from autowfbench.core.common import HTTPError, JsonHandler, http_json, now, read_json

TEMPLATE = re.compile(r"\$\{([a-zA-Z0-9_.-]+)\}")


class CandidateExecutionError(RuntimeError):
    pass


def lookup(context, path):
    value = context
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise CandidateExecutionError(f"Unknown candidate reference: {path}")
    return value


def resolve(value, context):
    if isinstance(value, dict):
        if set(value) == {"$ref"}:
            return lookup(context, value["$ref"])
        return {k: resolve(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, context) for v in value]
    if isinstance(value, str):
        exact = TEMPLATE.fullmatch(value)
        if exact:
            return lookup(context, exact.group(1))
        return TEMPLATE.sub(lambda match: str(lookup(context, match.group(1))), value)
    return value


def conditions_match(conditions, context):
    return all(lookup(context, item["path"]) == item["equals"] for item in conditions)


def local_step(operation, arguments):
    if operation == "set":
        if set(arguments) != {"value"}:
            raise CandidateExecutionError("set expects only value")
        return {"ok": True, "value": arguments["value"]}
    if operation == "regex_extract":
        if set(arguments) != {"text", "pattern"} or not isinstance(arguments["text"], str) or not isinstance(arguments["pattern"], str):
            raise CandidateExecutionError("regex_extract expects text and pattern strings")
        if len(arguments["pattern"]) > 1000:
            raise CandidateExecutionError("regex pattern is too large")
        match = re.search(arguments["pattern"], arguments["text"], re.MULTILINE)
        if not match:
            return {"ok": False, "error": {"code": "NO_MATCH", "message": "Pattern did not match", "retryable": False}}
        return {"ok": True, "value": {"match": match.group(0), **match.groupdict()}}
    raise CandidateExecutionError("Unsupported local operation")


def execute_candidate(candidate, request, cancelled=None):
    validate_candidate(candidate, expected_challenge=request["challenge"]["id"])
    context, trace = {"request": request}, []
    env = request["environment"]
    capabilities = set(request["challenge"]["capabilities"])
    for step in candidate["steps"]:
        if cancelled and cancelled.is_set():
            raise CandidateExecutionError("Cancelled")
        if step["when"] and not conditions_match(step["when"], context):
            continue
        arguments = resolve(step["arguments"], context)
        if step["kind"] == "tool":
            if step["operation"] not in capabilities:
                raise CandidateExecutionError(f"Operation is not a public challenge capability: {step['operation']}")
            result = http_json(
                env["base_url"] + "/tools",
                {"operation": step["operation"], "arguments": arguments},
                env["access_token"],
            )
        else:
            result = local_step(step["operation"], arguments)
        context[step["save_as"]] = result
        trace.append({"timestamp": now(), "kind": "candidate_step", "data": {"step_id": step["id"], "kind": step["kind"], "operation": step["operation"], "ok": bool(result.get("ok"))}})
        if step["require_ok"] and not result.get("ok"):
            raise CandidateExecutionError(f"Required step failed: {step['id']}")
    answer = resolve(candidate["final"]["answer"], context)
    artifacts = [{k: resolve(v, context) for k, v in artifact.items()} for artifact in candidate["final"]["artifacts"]]
    return {"protocol_version": "1.0", "run_id": request["run_id"], "status": "completed", "final_answer": str(answer), "artifacts": artifacts, "trace": trace}


def handler_for(candidate):
    validate_candidate(candidate)
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
                        result = execute_candidate(candidate, request, cancel)
                    except Exception as exc:
                        result = {"protocol_version": "1.0", "run_id": request.get("run_id", "unknown"), "status": "failed", "final_answer": f"{type(exc).__name__}: {exc}", "artifacts": [], "trace": []}
                    with lock:
                        jobs[execution_id].update(status=result["status"], submission=result)

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
                        return self.send(200, {k: v for k, v in job.items() if k != "cancel"})
            raise HTTPError(404, "Not found")

    return Handler


def serve(candidate, host="127.0.0.1", port=0):
    server = ThreadingHTTPServer((host, port), handler_for(candidate))
    print(json.dumps({"port": server.server_port, "candidate_id": candidate["candidate_id"]}), flush=True)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Run one generated Composer candidate behind Solution API v1.0")
    parser.add_argument("candidate")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    serve(read_json(args.candidate), args.host, args.port)


if __name__ == "__main__":
    main()
