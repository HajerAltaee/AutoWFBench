"""Compare physical source rows against a Git revision (blank lines included)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
revision = sys.argv[1] if len(sys.argv) > 1 else "d4576156a606910ff8fe1283b8ff86b53d43d704"


def category(name):
    path = Path(name)
    if name.startswith("autowfbench/") and path.suffix in (".py", ".js", ".css", ".html"):
        return "Application"
    if name.startswith(("schemas/", "benchmark/schemas/")) and path.suffix == ".json":
        return "Schemas"


before = {key: 0 for key in ("Application", "Schemas")}
after = before.copy()
for name in subprocess.check_output(["git", "ls-tree", "-r", "--name-only", revision], cwd=ROOT, text=True).splitlines():
    if key := category(name):
        before[key] += len(subprocess.check_output(["git", "show", f"{revision}:{name}"], cwd=ROOT).splitlines())
for path in (ROOT / "autowfbench").rglob("*"):
    if path.is_file() and (key := category(path.relative_to(ROOT).as_posix())):
        after[key] += len(path.read_bytes().splitlines())
for path in (ROOT / "benchmark/schemas").glob("*.json"):
    after["Schemas"] += len(path.read_bytes().splitlines())
before["Combined"], after["Combined"] = sum(before.values()), sum(after.values())
for key in before:
    print(f"{key}: {before[key]} -> {after[key]} rows ({(1 - after[key] / before[key]):.1%} reduction)")
