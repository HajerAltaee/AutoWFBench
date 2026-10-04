"""Check the benchmark owner's fixed baseline; specialists must not update it."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
lock = json.loads((ROOT / "benchmark-lock.json").read_text())
changed = []
for name, expected in lock["files"].items():
    path = ROOT / name
    actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    if actual != expected:
        changed.append(name)
if changed:
    raise SystemExit("Protected benchmark files changed: " + ", ".join(changed))
print(f"Benchmark lock verified: {len(lock['files'])} protected files.")
