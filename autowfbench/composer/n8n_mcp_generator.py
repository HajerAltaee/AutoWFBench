"""Sol orchestration over n8n's official instance-level MCP authoring tools."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from autowfbench.composer.n8n_generator import public_challenge
from autowfbench.composer.n8n_validation import N8N_IMAGE, N8N_VERSION
from autowfbench.composer.tool_contracts import contracts_for
from autowfbench.core.common import digest, now, save_json


OUTPUT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "workflow_id": {"type": "string", "minLength": 1},
        "summary": {"type": "string"},
        "composition_plan": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "hypothesis": {"type": "string", "minLength": 1},
        "repair_scope": {"type": "string", "enum": ["initial_composition", "targeted_local_repair", "architectural_replan"]},
    },
    "required": ["workflow_id", "summary", "composition_plan", "hypothesis", "repair_scope"],
    "additionalProperties": False,
}


def mcp_prompt(challenge):
    public = public_challenge(challenge)
    payload = {
        "public_challenge": public,
        "public_tool_contracts": contracts_for(public["capabilities"]),
        "runtime": {"name": "n8n", "version": N8N_VERSION, "image": N8N_IMAGE},
        "adapter_environment": {
            "AWB_RUN_ID": "original benchmark run ID",
            "AWB_ENV_BASE_URL": "run-scoped environment base URL",
            "AWB_ENV_ACCESS_TOKEN": "run-scoped bearer token",
        },
    }
    return """You are the AutoWFBench Composer. Use only the official n8n MCP server
named n8n to author one executable native n8n workflow for the public task below.
Do not merely print or save workflow JSON.

COMPOSITION FIRST: before writing workflow code, form a compact execution plan and
map every step to an n8n control-flow primitive. Prefer a direct finite graph,
retryOnFail/maxTries for bounded transient retry, explicit state only where needed,
and a single final submission path. Known finite business operations should be
composed explicitly; do not implement a generic graph back-edge state machine.
Do not copy Attempt 1/Attempt 2/Attempt 3 sections or unroll retry loops. Avoid
duplicating large node sections. Node count is not an objective, but each node must
have a distinct semantic purpose and the graph must have a provable termination.

Use the required MCP authoring sequence: read the Workflow SDK reference and
relevant best practices; inspect the exact node types; validate node configs where
useful; write SDK code; validate it; create the workflow; then inspect the created
workflow. If validation or creation rejects the workflow, repair it through MCP.

The workflow must use exactly one Manual Trigger and finish with an Edit Fields/Set
node whose output is the AutoWFBench submission object. Use HTTP Request nodes for
all business operations. Each request must POST to
={{ $env.AWB_ENV_BASE_URL + '/tools' }}, use a Bearer value derived from
$env.AWB_ENV_ACCESS_TOKEN, and send {operation, arguments}. All task-specific
decisions belong in the workflow. Use no credentials, secrets, shell, Python,
community nodes, arbitrary external URLs, benchmark internals, judge information,
fixtures, or scorecards. Keep the workflow unpublished.

The final Set output must contain protocol_version='1.0', run_id=$env.AWB_RUN_ID,
status, final_answer, artifacts, and trace, matching the public completion contract.
After the official MCP confirms creation and inspection, return only the required
structured response containing its workflow_id, compact composition_plan, explicit
hypothesis, repair_scope, and summary. Do not include workflow JSON in the final
response.

PUBLIC_INPUT_JSON:
""" + json.dumps(payload, indent=2, ensure_ascii=False)


class OfficialN8nMcpGenerator:
    def __init__(self, model, output_dir, runtime_validator, mcp_url, token_env="N8N_MCP_TOKEN",
                 container="awb-composer-mcp-n8n", binary=None, docker="docker", timeout=900):
        self.model = model
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=False)
        self.runtime_validator = runtime_validator
        self.mcp_url, self.token_env, self.container = mcp_url, token_env, container
        self.binary = binary or os.environ.get("CODEX_BIN") or shutil.which("codex")
        self.docker, self.timeout = docker, timeout
        if not self.binary:
            raise ValueError("Codex CLI not found")
        if not os.environ.get(token_env):
            raise ValueError(f"{token_env} is required for official n8n MCP authentication")

    def generate(self, challenge, existing_workflow_id=None, validation_errors=None, iteration_feedback=None):
        prompt = mcp_prompt(challenge)
        if existing_workflow_id:
            feedback = iteration_feedback or {"errors": validation_errors or []}
            prompt += (
                "\n\nWORKFLOW_ITERATION:\nDo not create a second workflow. Inspect the existing workflow first. "
                "Classify the failure as a targeted local repair or architectural re-plan using the supplied "
                "runtime-safe feedback. Default to the smallest semantically correct repair and preserve working "
                "nodes. Never duplicate or unroll the graph to repair retry or termination. If the architecture "
                "is wrong, replace the problematic control-flow section with a compact terminating composition. "
                "Update only through official n8n MCP, validate, then inspect the result.\nWORKFLOW_ID: "
                + existing_workflow_id + "\nITERATION_FEEDBACK_JSON:\n" + json.dumps(feedback, indent=2)
            )
        prompt_path = self.output_dir / "prompt.txt"
        schema_path = self.output_dir / "output.schema.json"
        response_path = self.output_dir / "final-response.json"
        events_path = self.output_dir / "mcp-events.jsonl"
        stderr_path = self.output_dir / "codex-stderr.log"
        prompt_path.write_text(prompt, encoding="utf-8")
        save_json(schema_path, OUTPUT_SCHEMA)
        command = [
            self.binary, "exec", "--model", self.model,
            "--skip-git-repo-check", "--ephemeral", "--approve-for-me",
            "-c", f'mcp_servers.n8n.url="{self.mcp_url}"',
            "-c", f'mcp_servers.n8n.bearer_token_env_var="{self.token_env}"',
            "--output-schema", str(schema_path), "--json", "-o", str(response_path), "-",
        ]
        env = {key: value for key, value in os.environ.items() if not key.startswith("AWB_")}
        env[self.token_env] = os.environ[self.token_env]
        completed = subprocess.run(
            command, input=prompt, text=True, cwd=self.output_dir, env=env,
            capture_output=True, timeout=self.timeout, shell=False,
            encoding="utf-8", errors="replace",
        )
        events_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        save_json(self.output_dir / "mcp-tool-trace.json", _mcp_trace(completed.stdout))
        if completed.returncode:
            raise RuntimeError(f"Sol MCP authoring exited with code {completed.returncode}")
        response = json.loads(response_path.read_text(encoding="utf-8"))
        workflow = self._export(response["workflow_id"])
        workflow_path = self.output_dir / "workflow.json"
        save_json(workflow_path, workflow)
        provenance = {
            "generator": "codex-official-n8n-mcp",
            "model": self.model,
            "created_at": now(),
            "manually_edited": False,
            "mcp_server": "official n8n instance-level MCP",
            "mcp_url": self.mcp_url,
            "n8n_version": N8N_VERSION,
            "n8n_image": N8N_IMAGE,
            "workflow_id": response["workflow_id"],
            "source_workflow_id": existing_workflow_id,
            "workflow_digest": digest(workflow),
            "composition_plan": response["composition_plan"],
            "hypothesis": response["hypothesis"],
            "repair_scope": response["repair_scope"],
            "challenge": public_challenge(challenge),
        }
        save_json(self.output_dir / "provenance.json", provenance)
        return workflow, provenance

    def _export(self, workflow_id):
        remote = "/tmp/autowfbench-mcp-export.json"
        completed = subprocess.run(
            [self.docker, "exec", self.container, "n8n", "export:workflow", "--id", workflow_id,
             "--output", remote, "--pretty"], capture_output=True, text=True, timeout=120,
        )
        (self.output_dir / "n8n-export.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
        if completed.returncode:
            raise RuntimeError("n8n failed to export the MCP-authored workflow")
        with tempfile.TemporaryDirectory() as temporary:
            local = Path(temporary) / "workflow.json"
            copied = subprocess.run(
                [self.docker, "cp", f"{self.container}:{remote}", str(local)],
                capture_output=True, text=True, timeout=30,
            )
            if copied.returncode:
                raise RuntimeError("Docker failed to copy the MCP-authored workflow export")
            value = json.loads(local.read_text(encoding="utf-8"))
        subprocess.run([self.docker, "exec", self.container, "rm", "-f", remote], capture_output=True)
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if not isinstance(value, dict):
            raise ValueError("Expected one exported n8n workflow")
        return value


def _mcp_trace(stdout):
    calls = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item") if isinstance(event, dict) else None
        if isinstance(item, dict) and item.get("type") == "mcp_tool_call" and item.get("server") == "n8n":
            calls.append(item)
    return calls
