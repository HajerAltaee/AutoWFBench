"""Sol-backed native n8n generation with deterministic bounded repair."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from autowfbench.composer.n8n_validation import (
    ALLOWED_NODE_VERSIONS,
    N8N_IMAGE,
    N8N_VERSION,
    issues_as_dicts,
    parse_workflow_json,
    validate_n8n_workflow,
)
from autowfbench.composer.tool_contracts import contracts_for
from autowfbench.core.common import digest, now, save_json


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"workflow_json": {"type": "string"}},
    "required": ["workflow_json"],
    "additionalProperties": False,
    "$schema": "http://json-schema.org/draft-07/schema#",
}


def public_challenge(challenge):
    return {key: challenge[key] for key in ("id", "version", "name", "task", "limits", "capabilities", "completion") if key in challenge}


def generation_prompt(challenge):
    public = public_challenge(challenge)
    payload = {
        "public_challenge": public,
        "public_tool_contracts": contracts_for(public["capabilities"]),
        "runtime": {"name": "n8n", "version": N8N_VERSION, "image": N8N_IMAGE},
        "allowed_node_versions": {key: sorted(value) for key, value in ALLOWED_NODE_VERSIONS.items()},
        "adapter_environment": {
            "AWB_RUN_ID": "original benchmark run ID",
            "AWB_ENV_BASE_URL": "run-scoped environment base URL",
            "AWB_ENV_ACCESS_TOKEN": "run-scoped bearer token",
        },
    }
    return """You are the AutoWFBench workflow Composer. Generate one complete native
n8n workflow export for the public task below. The workflow itself must contain all
task-specific business logic; a fixed external adapter supplies only the three
documented environment variables and runs the workflow.

Return exactly {"workflow_json":"<JSON-encoded native n8n workflow>"}. The decoded
workflow must contain exactly id, name, nodes, connections, settings, active. Use a
UUID workflow id and UUID node ids. Set active=false and settings.executionOrder=v1.
Use exactly one n8n-nodes-base.manualTrigger. All nodes must be reachable from it.

Use only the allowed node types and versions. Business tool calls must be HTTP
Request nodes (typeVersion 4.2) with POST URL
={{ $env.AWB_ENV_BASE_URL + '/tools' }}, bearer Authorization derived from
$env.AWB_ENV_ACCESS_TOKEN, and JSON body {operation,arguments}. Use only public
capabilities. HTTP Request v4.2 parameters must include method, url, sendHeaders,
headerParameters.parameters, sendBody, specifyBody='json', jsonBody, and options.

Native n8n expressions may reference earlier nodes with $('Node Name').first().json.
Finish with an Edit Fields/Set node (type n8n-nodes-base.set, typeVersion 3.4,
mode='raw') whose jsonOutput evaluates to one object with protocol_version='1.0',
run_id=$env.AWB_RUN_ID, status='completed', final_answer, artifacts, and trace.
Do not embed secrets, credentials, benchmark internals, scorecards, judge logic,
fixtures, Python, shell commands, community nodes, or arbitrary external URLs.
Do not output prose or Markdown outside the required envelope.

PUBLIC_INPUT_JSON:
""" + json.dumps(payload, indent=2, ensure_ascii=False)


class N8nGenerationError(RuntimeError):
    pass


class N8nGenerator:
    def __init__(self, model, output_dir, runtime_validator=None, binary=None, attempts=3, timeout=600):
        if not model:
            raise ValueError("Pin a Composer model")
        self.model = model
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_validator = runtime_validator
        self.binary = binary or os.environ.get("CODEX_BIN") or shutil.which("codex")
        if not self.binary:
            raise ValueError("Codex CLI not found")
        self.attempts, self.timeout = attempts, timeout

    def generate(self, challenge, repair_workflow=None, repair_errors=None):
        base_prompt = generation_prompt(challenge)
        source_digest = None
        if repair_workflow is not None:
            source_digest = digest(repair_workflow)
            save_json(self.output_dir / "source-workflow.json", repair_workflow)
            base_prompt += (
                "\n\nREPAIR_EXISTING_WORKFLOW:\nRepair this Composer-generated workflow using only "
                "the deterministic configuration errors below. Do not redesign it from benchmark feedback.\n"
                "VALIDATION_ERRORS_JSON:\n" + json.dumps(repair_errors or [], indent=2, ensure_ascii=False)
                + "\nPREVIOUS_WORKFLOW_JSON:\n" + json.dumps(repair_workflow, ensure_ascii=False)
            )
        repair = ""
        records = []
        for number in range(1, self.attempts + 1):
            attempt = self.output_dir / f"attempt-{number:02d}"
            attempt.mkdir(parents=True, exist_ok=False)
            prompt = base_prompt + repair
            (attempt / "prompt.txt").write_text(prompt, encoding="utf-8")
            schema, output = attempt / "output.schema.json", attempt / "raw-envelope.json"
            save_json(schema, OUTPUT_SCHEMA)
            command = [
                self.binary, "exec", "--model", self.model, "--sandbox", "read-only",
                "--skip-git-repo-check", "--ephemeral", "--output-schema", str(schema),
                "--json", "-o", str(output), "-",
            ]
            env = {key: value for key, value in os.environ.items() if not key.startswith("AWB_")}
            try:
                completed = subprocess.run(command, input=prompt, text=True, cwd=attempt, env=env, capture_output=True, timeout=self.timeout, shell=False)
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                (attempt / "codex-events.jsonl").write_text(stdout, encoding="utf-8")
                (attempt / "codex-stderr.log").write_text(stderr, encoding="utf-8")
                errors = [{"code": "GENERATOR_TIMEOUT", "path": "$", "message": f"Sol exceeded the {self.timeout}-second generation limit"}]
                save_json(attempt / "validation-errors.json", errors)
                records.append({"attempt": number, "created_at": now(), "valid": False, "errors": errors})
                repair = (
                    "\n\nRETRY_AFTER_TIMEOUT:\nThe previous generation exceeded the bounded time limit "
                    "without producing a workflow. Produce a concise complete workflow now."
                )
                continue
            (attempt / "codex-events.jsonl").write_text(completed.stdout, encoding="utf-8")
            (attempt / "codex-stderr.log").write_text(completed.stderr, encoding="utf-8")
            errors = []
            workflow = None
            raw_workflow_text = None
            if completed.returncode:
                errors = [{"code": "GENERATOR_EXIT", "path": "$", "message": f"Sol exited with code {completed.returncode}"}]
            else:
                try:
                    envelope = json.loads(output.read_text(encoding="utf-8"))
                    if set(envelope) != {"workflow_json"} or not isinstance(envelope["workflow_json"], str):
                        raise ValueError("Output envelope must contain only workflow_json as a string")
                    raw_workflow_text = envelope["workflow_json"]
                    (attempt / "raw-workflow.json.txt").write_text(raw_workflow_text, encoding="utf-8")
                    workflow = parse_workflow_json(raw_workflow_text)
                    save_json(attempt / "workflow.json", workflow)
                    errors = issues_as_dicts(validate_n8n_workflow(workflow, challenge))
                    if not errors and self.runtime_validator:
                        errors = self.runtime_validator.validate_import(workflow, attempt)
                    if not errors and self.runtime_validator:
                        errors = self.runtime_validator.validate_execution(workflow, attempt / "workflow.json", challenge)
                except (json.JSONDecodeError, ValueError) as exc:
                    errors = [{"code": "INVALID_JSON", "path": "$", "message": str(exc)}]
            save_json(attempt / "validation-errors.json", errors)
            record = {"attempt": number, "created_at": now(), "valid": not errors, "errors": errors}
            if workflow is not None:
                record["workflow_digest"] = digest(workflow)
            records.append(record)
            if not errors:
                final = self.output_dir / "workflow.json"
                save_json(final, workflow)
                provenance = {
                    "generator": "codex",
                    "model": self.model,
                    "attempt_limit": self.attempts,
                    "attempts_used": number,
                    "manually_edited": False,
                    "workflow_digest": digest(workflow),
                    "n8n_version": N8N_VERSION,
                    "n8n_image": N8N_IMAGE,
                    "challenge": public_challenge(challenge),
                    "attempt_records": records,
                }
                if source_digest:
                    provenance["source_workflow_digest"] = source_digest
                save_json(self.output_dir / "provenance.json", provenance)
                return workflow, provenance
            repair = (
                "\n\nREPAIR_ATTEMPT:\nThe preceding generated workflow was rejected by deterministic "
                "configuration validation. Repair the complete native n8n workflow using only "
                "these errors and the same public inputs. Return the complete envelope again.\n"
                "VALIDATION_ERRORS_JSON:\n" + json.dumps(errors, indent=2, ensure_ascii=False)
                + "\nPREVIOUS_WORKFLOW_JSON:\n" + (raw_workflow_text or "Unavailable because the prior envelope was not parseable.")
            )
        save_json(self.output_dir / "provenance.json", {
            "generator": "codex", "model": self.model, "attempt_limit": self.attempts,
            "attempts_used": len(records), "manually_edited": False, "valid": False,
            "n8n_version": N8N_VERSION, "n8n_image": N8N_IMAGE, "attempt_records": records,
            "source_workflow_digest": source_digest,
        })
        raise N8nGenerationError(f"Sol failed to generate a valid n8n workflow in {self.attempts} attempts")
