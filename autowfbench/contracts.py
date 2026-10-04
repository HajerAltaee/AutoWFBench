from __future__ import annotations

from functools import lru_cache

import fastjsonschema

from .common import ROOT, digest, read_json


@lru_cache(maxsize=16)
def validator(name):
    return fastjsonschema.compile(read_json(ROOT / "schemas" / (name + ".schema.json")), use_default=False)


def validate(name, value):
    validator(name)(value)
    return value


def load_challenge(challenge_id):
    if challenge_id not in {p.name for p in (ROOT / "challenges").iterdir() if p.is_dir()}:
        raise ValueError("Unknown challenge")
    root = ROOT / "challenges" / challenge_id
    package = {key: read_json(root / filename) for key, filename in (
        ("definition", "definition.json"), ("environment", "environment.json"), ("scorecard", "scorecard.json"))}
    package["environment"]["implementation_digest"] = digest((ROOT / "autowfbench/environment.py").read_text())
    validate("scorecard", package["scorecard"])
    definition = package["definition"]
    if definition["id"] != challenge_id:
        raise ValueError("Challenge ID mismatch")
    if sum(c["weight"] for c in package["scorecard"]["criteria"]) != 10:
        raise ValueError("Example challenge weights must sum to 10")
    ids = [c["id"] for c in package["scorecard"]["criteria"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate criterion IDs")
    package["hashes"] = {k: digest(v) for k, v in package.items()}
    return package


def public_challenges():
    return [load_challenge(p.name)["definition"] for p in sorted((ROOT / "challenges").iterdir()) if p.is_dir()]
