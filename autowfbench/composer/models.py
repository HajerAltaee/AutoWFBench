"""Strict Composer-owned contracts and black-box observations."""
from __future__ import annotations

import json
import math
import re
import statistics
from dataclasses import asdict, dataclass
from typing import Any

from autowfbench.core.common import digest
from autowfbench.composer.principles import MUTATION_STRATEGIES

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
STRATEGIES = ("initial",) + MUTATION_STRATEGIES
OBSERVATION_STATUSES = {"completed", "timeout", "unscored", "failed", "simulated"}


def _exact_keys(value, required, optional=()):
    if not isinstance(value, dict):
        raise ValueError("Expected an object")
    missing = set(required) - set(value)
    extra = set(value) - set(required) - set(optional)
    if missing or extra:
        raise ValueError(f"Object keys mismatch; missing={sorted(missing)}, extra={sorted(extra)}")


def _json_value(value: Any, depth=0):
    if depth > 20:
        raise ValueError("Candidate value nesting is too deep")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Candidate numbers must be finite")
        return
    if isinstance(value, list):
        if len(value) > 200:
            raise ValueError("Candidate arrays are too large")
        for item in value:
            _json_value(item, depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 200:
            raise ValueError("Candidate objects are too large")
        if "$ref" in value:
            _exact_keys(value, ("$ref",))
            if not isinstance(value["$ref"], str) or not value["$ref"]:
                raise ValueError("$ref must be a nonempty path")
            return
        for key, item in value.items():
            if not isinstance(key, str) or key.startswith("$"):
                raise ValueError("Candidate object keys must be ordinary strings")
            _json_value(item, depth + 1)
        return
    raise ValueError(f"Unsupported candidate value: {type(value).__name__}")


def validate_candidate(candidate, expected_challenge=None, expected_id=None):
    """Validate the constrained declarative workflow representation."""
    _exact_keys(candidate, ("schema_version", "candidate_id", "challenge_id", "version", "strategy", "hypothesis", "steps", "final"))
    if candidate["schema_version"] != "1.0":
        raise ValueError("Unsupported candidate schema")
    for field in ("candidate_id", "challenge_id"):
        if not isinstance(candidate[field], str) or not IDENTIFIER.fullmatch(candidate[field]):
            raise ValueError(f"Invalid {field}")
    if expected_challenge and candidate["challenge_id"] != expected_challenge:
        raise ValueError("Candidate challenge mismatch")
    if expected_id and candidate["candidate_id"] != expected_id:
        raise ValueError("Candidate ID mismatch")
    if not isinstance(candidate["version"], str) or not candidate["version"]:
        raise ValueError("Candidate version is required")
    if candidate["strategy"] not in STRATEGIES:
        raise ValueError("Unknown optimization strategy")
    if not isinstance(candidate["hypothesis"], str) or not candidate["hypothesis"]:
        raise ValueError("Candidate hypothesis is required")
    steps = candidate["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 80:
        raise ValueError("Candidate must contain 1-80 steps")
    step_ids, variables = set(), set()
    for step in steps:
        _exact_keys(step, ("id", "kind", "operation", "arguments", "save_as", "require_ok", "when"))
        if not isinstance(step["id"], str) or not IDENTIFIER.fullmatch(step["id"]) or step["id"] in step_ids:
            raise ValueError("Step IDs must be unique identifiers")
        step_ids.add(step["id"])
        if step["kind"] not in ("tool", "local"):
            raise ValueError("Step kind must be tool or local")
        if not isinstance(step["operation"], str) or not step["operation"]:
            raise ValueError("Step operation is required")
        if step["kind"] == "local" and step["operation"] not in ("set", "regex_extract"):
            raise ValueError("Unsupported local operation")
        _json_value(step["arguments"])
        if not isinstance(step["save_as"], str) or not IDENTIFIER.fullmatch(step["save_as"]) or step["save_as"] in variables:
            raise ValueError("save_as values must be unique identifiers")
        variables.add(step["save_as"])
        if type(step["require_ok"]) is not bool:
            raise ValueError("require_ok must be boolean")
        if not isinstance(step["when"], list) or len(step["when"]) > 10:
            raise ValueError("when must be a bounded condition list")
        for condition in step["when"]:
            _exact_keys(condition, ("path", "equals"))
            if not isinstance(condition["path"], str) or not condition["path"]:
                raise ValueError("Condition path is required")
            _json_value(condition["equals"])
    final = candidate["final"]
    _exact_keys(final, ("answer", "artifacts"))
    if not isinstance(final["answer"], str):
        raise ValueError("Final answer template must be a string")
    if not isinstance(final["artifacts"], list) or len(final["artifacts"]) > 20:
        raise ValueError("Final artifacts must be a bounded list")
    for artifact in final["artifacts"]:
        _exact_keys(artifact, ("name", "media_type", "content"))
        if not all(isinstance(artifact[k], str) and artifact[k] for k in ("name", "media_type")) or not isinstance(artifact["content"], str):
            raise ValueError("Invalid artifact template")
    encoded = json.dumps(candidate, allow_nan=False)
    if len(encoded) > 200_000:
        raise ValueError("Candidate exceeds size limit")
    return candidate


def candidate_digest(candidate):
    validate_candidate(candidate)
    return digest(candidate)


def structural_complexity(candidate):
    validate_candidate(candidate)
    return len(candidate["steps"]) + sum(len(step["when"]) for step in candidate["steps"]) + sum(step["kind"] == "local" for step in candidate["steps"])


@dataclass(frozen=True)
class NumericObservation:
    """The complete information permitted to cross into the Composer."""

    candidate_id: str
    run_id: str
    score_0_10: float | None
    tool_calls: int | None
    duration_seconds: float | None
    status: str
    seed: int
    simulated: bool = False

    def __post_init__(self):
        if self.status not in OBSERVATION_STATUSES:
            raise ValueError("Invalid coarse observation status")
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("Observation run ID is required")
        if self.score_0_10 is not None and not 0 <= self.score_0_10 <= 10:
            raise ValueError("Score must be within 0-10")
        if self.tool_calls is not None and (type(self.tool_calls) is not int or self.tool_calls < 0):
            raise ValueError("Invalid tool-call count")
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise ValueError("Invalid duration")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("Invalid seed")

    def as_dict(self):
        return asdict(self)

    @classmethod
    def from_engine_result(cls, candidate_id, result):
        """Project a potentially sensitive engine result through an allowlist."""
        score = result.get("score_0_10")
        termination = result.get("termination_reason")
        raw_status = result.get("status")
        if termination == "timeout":
            status = "timeout"
        elif score is not None and raw_status == "complete":
            status = "completed"
        elif score is None and raw_status in ("awaiting_llm_judge", "judge_failed", "judging"):
            status = "unscored"
        else:
            status = "failed"
        return cls(
            candidate_id=candidate_id,
            run_id=str(result["run_id"]),
            score_0_10=float(score) if score is not None else None,
            tool_calls=int(result["tool_calls"]) if result.get("tool_calls") is not None else None,
            duration_seconds=float(result["duration_seconds"]) if result.get("duration_seconds") is not None else None,
            status=status,
            seed=int(result.get("seed", 0)),
        )


def aggregate_observations(observations):
    values = list(observations)
    if not values:
        raise ValueError("At least one observation is required")
    scores = [o.score_0_10 for o in values if o.score_0_10 is not None]
    calls = [o.tool_calls for o in values if o.tool_calls is not None]
    durations = [o.duration_seconds for o in values if o.duration_seconds is not None]
    successful = [o for o in values if o.status in ("completed", "simulated") and o.score_0_10 is not None]
    return {
        "attempts": len(values),
        "scored_attempts": len(scores),
        "completion_rate": len(successful) / len(values),
        "mean_score": statistics.mean(scores) if scores else None,
        "median_score": statistics.median(scores) if scores else None,
        "median_tool_calls": statistics.median(calls) if calls else None,
        "median_duration_seconds": statistics.median(durations) if durations else None,
    }
