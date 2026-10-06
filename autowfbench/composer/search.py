"""Reproducible black-box candidate search and conservative selection."""
from __future__ import annotations

import json
from pathlib import Path

from autowfbench.composer.models import (
    aggregate_observations,
    candidate_digest,
    structural_complexity,
    validate_candidate,
)
from autowfbench.composer.principles import PRINCIPLES
from autowfbench.core.common import now, save_json


class ExperimentStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        (self.root / "candidates").mkdir(parents=True, exist_ok=True)

    def initialize(self, challenge, config):
        public = {key: challenge[key] for key in ("id", "version", "name", "task", "limits", "capabilities", "completion") if key in challenge}
        save_json(self.root / "public-challenge.json", public)
        save_json(self.root / "principles.json", PRINCIPLES)
        save_json(self.root / "config.json", config)

    def candidate(self, value):
        save_json(self.root / "candidates" / f"{value['candidate_id']}.json", value)

    def history(self, records):
        save_json(self.root / "history.json", records)


def select(parent_record, child_record, score_epsilon=0.01, duration_epsilon=0.001, minimum_performance_samples=2):
    parent, child = parent_record["aggregate"], child_record["aggregate"]
    if child["completion_rate"] < parent["completion_rate"]:
        return False, "Rejected: execution completion rate regressed."
    if child["mean_score"] is None:
        return False, "Rejected: child produced no aggregate benchmark score."
    if parent["mean_score"] is None:
        return True, "Accepted: child produced a score while the parent was unscored."
    delta = child["mean_score"] - parent["mean_score"]
    if delta > score_epsilon:
        return True, f"Accepted: aggregate score improved by {delta:.4f}."
    if delta < -score_epsilon:
        return False, f"Rejected: aggregate score regressed by {abs(delta):.4f}."
    if min(parent["attempts"], child["attempts"]) < minimum_performance_samples:
        return False, "Rejected: scores were equivalent and repeated measurements are required before cost-based selection."
    parent_calls, child_calls = parent["median_tool_calls"], child["median_tool_calls"]
    if parent_calls is not None and child_calls is not None and child_calls < parent_calls:
        return True, "Accepted: equivalent score with fewer median tool calls across repeated measurements."
    if parent_calls is not None and child_calls is not None and child_calls > parent_calls:
        return False, "Rejected: equivalent score with more median tool calls."
    parent_duration, child_duration = parent["median_duration_seconds"], child["median_duration_seconds"]
    if parent_duration is not None and child_duration is not None and child_duration + duration_epsilon < parent_duration:
        return True, "Accepted: equivalent score and calls with lower median duration across repeated measurements."
    if child_record["structural_complexity"] < parent_record["structural_complexity"]:
        return True, "Accepted: equivalent measured outcomes with lower candidate-owned structural complexity."
    return False, "Rejected: no permitted metric or candidate-owned complexity improvement."


class ComposerSearch:
    def __init__(self, challenge, generator, evaluator, store, iterations=2, seeds=(0,), repeats=2, score_epsilon=0.01):
        if iterations < 1 or repeats < 1 or not seeds:
            raise ValueError("Composer budgets must be positive")
        self.challenge, self.generator, self.evaluator = challenge, generator, evaluator
        self.store = store if isinstance(store, ExperimentStore) else ExperimentStore(store)
        self.iterations, self.seeds, self.repeats, self.score_epsilon = iterations, tuple(seeds), repeats, score_epsilon

    def _evaluate(self, candidate):
        observations = []
        for seed in self.seeds:
            for repeat in range(self.repeats):
                observations.append(self.evaluator.evaluate(candidate, seed, repeat))
        return observations

    def _record(self, candidate, parent, observations, accepted, reason):
        return {
            "candidate_id": candidate["candidate_id"],
            "parent_candidate": parent,
            "candidate_digest": candidate_digest(candidate),
            "optimization_strategy": candidate["strategy"],
            "hypothesis": candidate["hypothesis"],
            "benchmark_runs": [item.as_dict() for item in observations],
            "aggregate": aggregate_observations(observations),
            "structural_complexity": structural_complexity(candidate),
            "accepted": accepted,
            "decision_reason": reason,
        }

    def run(self):
        config = {
            "created_at": now(),
            "iterations": self.iterations,
            "seeds": list(self.seeds),
            "repeats": self.repeats,
            "score_epsilon": self.score_epsilon,
            "selection_order": ["completion_rate", "aggregate_score", "median_tool_calls", "median_duration", "structural_complexity"],
        }
        self.store.initialize(self.challenge, config)
        history = []
        incumbent = self.generator.initial(self.challenge, "c000")
        validate_candidate(incumbent, expected_challenge=self.challenge["id"], expected_id="c000")
        self.store.candidate(incumbent)
        observations = self._evaluate(incumbent)
        incumbent_record = self._record(incumbent, None, observations, True, "Accepted as the initial generated baseline.")
        history.append(incumbent_record)
        self.store.history(history)
        for index in range(1, self.iterations):
            candidate_id = f"c{index:03d}"
            child = self.generator.child(self.challenge, candidate_id, incumbent, history)
            validate_candidate(child, expected_challenge=self.challenge["id"], expected_id=candidate_id)
            self.store.candidate(child)
            child_observations = self._evaluate(child)
            provisional = self._record(child, incumbent["candidate_id"], child_observations, False, "Pending selection")
            accepted, reason = select(incumbent_record, provisional, self.score_epsilon)
            provisional.update(accepted=accepted, decision_reason=reason)
            history.append(provisional)
            if accepted:
                incumbent, incumbent_record = child, provisional
            self.store.history(history)
        save_json(self.store.root / "result.json", {"incumbent_candidate": incumbent["candidate_id"], "history": history})
        return history
