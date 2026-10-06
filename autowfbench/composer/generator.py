"""Candidate generators that receive only public inputs and numeric history."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from autowfbench.composer.models import validate_candidate
from autowfbench.composer.principles import PRINCIPLES
from autowfbench.composer.tool_contracts import contracts_for
from autowfbench.core.common import save_json


CANDIDATE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        # Encoding the candidate as a string keeps this output schema strict
        # while allowing public tools to have challenge-specific argument keys.
        "candidate_json": {"type": "string"},
    },
    "required": ["candidate_json"],
    "additionalProperties": False,
    "$schema": "http://json-schema.org/draft-07/schema#",
}


FORMAT_GUIDE = """Return an object with exactly one field, `candidate_json`. Its
value must be a JSON-encoded string containing one declarative candidate object.

Each step has exactly: id, kind, operation, arguments, save_as, require_ok, when.
- kind=tool invokes one public capability.
- kind=local permits only set or regex_extract.
- Values may reference earlier results with {"$ref":"variable.value.path"}.
- Strings may interpolate earlier results with ${variable.value.path}.
- when is an AND-list such as [{"path":"update.ok","equals":false}].
- Tool results have {ok:true,value:...} or {ok:false,error:{code,message,retryable}}.
- Set arguments are {"value": ...}.
- regex_extract arguments are {"text": ..., "pattern": ...}; named regex groups
  and the full match are returned under value (value.match, value.<group>).
- require_ok=true ends the candidate as failed if the step result is not ok.
- The final answer and artifact content are templates using the same ${...} syntax.

Do not invent capabilities. Do not include Python, shell, benchmark files,
scorecards, evaluator assumptions, or hidden-data guesses. Keep every workflow
bounded, direct, and understandable.
"""


def _safe_history(history):
    """Copy only the already-sanitized Composer history fields."""
    allowed = {
        "candidate_id", "parent_candidate", "candidate_digest", "optimization_strategy",
        "hypothesis", "benchmark_runs", "aggregate", "accepted", "decision_reason",
        "structural_complexity",
    }
    return [{key: item[key] for key in allowed if key in item} for item in history]


def initial_prompt(challenge, candidate_id):
    public = {
        key: challenge[key]
        for key in ("id", "version", "name", "task", "limits", "capabilities", "completion")
        if key in challenge
    }
    payload = {
        "candidate_id": candidate_id,
        "public_challenge": public,
        "public_tool_contracts": contracts_for(public["capabilities"]),
        "fixed_principles": PRINCIPLES,
    }
    return (
        "You are the workflow Composer. Generate the initial candidate using only "
        "the public task, public tool contracts, and fixed principles below. This "
        "is not evaluator feedback. Set strategy to 'initial' and version to 0.1.0.\n\n"
        + FORMAT_GUIDE
        + "\nPUBLIC_INPUT_JSON:\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
    )


def child_prompt(challenge, candidate_id, parent, history):
    public = {
        key: challenge[key]
        for key in ("id", "version", "name", "task", "limits", "capabilities", "completion")
        if key in challenge
    }
    payload = {
        "candidate_id": candidate_id,
        "public_challenge": public,
        "public_tool_contracts": contracts_for(public["capabilities"]),
        "fixed_principles": PRINCIPLES,
        "parent_candidate": parent,
        "numeric_history": _safe_history(history),
    }
    return (
        "You are the workflow Composer. Inspect only your own parent candidate and "
        "the permitted numeric history. Choose exactly one targeted strategy from "
        "correctness, reliability, efficiency, or simplicity. Produce one child "
        "candidate, not a full rewrite without a reason. The strategy and hypothesis "
        "must explain the intended change using only fixed principles and permitted "
        "numbers. Never infer hidden scorecard logic.\n\n"
        + FORMAT_GUIDE
        + "\nPUBLIC_AND_COMPOSER_INPUT_JSON:\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
    )


class CodexGenerator:
    """Run an isolated Codex generation session in a Composer-owned workspace."""

    def __init__(self, model, workspace, binary=None, timeout=180):
        if not model:
            raise ValueError("Pin a Composer model")
        self.model = model
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.binary = binary or os.environ.get("CODEX_BIN") or shutil.which("codex")
        if not self.binary:
            raise ValueError("Codex CLI not found")
        self.timeout = timeout

    def _generate(self, prompt, challenge_id, candidate_id, expected_strategy=None):
        with tempfile.TemporaryDirectory(prefix="generation-", dir=self.workspace) as directory:
            root = Path(directory)
            schema, output = root / "candidate.schema.json", root / "candidate.json"
            save_json(schema, CANDIDATE_OUTPUT_SCHEMA)
            (root / "prompt.txt").write_text(prompt, encoding="utf-8")
            command = [
                self.binary, "exec", "--model", self.model, "--sandbox", "read-only",
                "--skip-git-repo-check", "--ephemeral", "--output-schema", str(schema),
                "-o", str(output), "-",
            ]
            env = {k: v for k, v in os.environ.items() if not k.startswith("AWB_")}
            completed = subprocess.run(command, input=prompt, text=True, cwd=root, env=env, capture_output=True, timeout=self.timeout, shell=False)
            if completed.returncode:
                raise RuntimeError(f"Composer model exited {completed.returncode}: {completed.stderr[-1000:]}")
            envelope = json.loads(output.read_text(encoding="utf-8"))
            if set(envelope) != {"candidate_json"} or not isinstance(envelope["candidate_json"], str):
                raise ValueError("Composer model returned an invalid output envelope")
            candidate = json.loads(envelope["candidate_json"])
        validate_candidate(candidate, expected_challenge=challenge_id, expected_id=candidate_id)
        if expected_strategy and candidate["strategy"] != expected_strategy:
            raise ValueError(f"Expected strategy {expected_strategy}")
        return candidate

    def initial(self, challenge, candidate_id="c000"):
        return self._generate(initial_prompt(challenge, candidate_id), challenge["id"], candidate_id, "initial")

    def child(self, challenge, candidate_id, parent, history):
        candidate = self._generate(child_prompt(challenge, candidate_id, parent, history), challenge["id"], candidate_id)
        if candidate["strategy"] == "initial":
            raise ValueError("Child candidate must choose one optimization strategy")
        return candidate
