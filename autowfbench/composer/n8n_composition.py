"""Composition-first observations and bounded iteration policy for native n8n."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from autowfbench.composer.n8n_validation import issues_as_dicts, validate_n8n_workflow
from autowfbench.core.common import save_json


@dataclass(frozen=True)
class Structure:
    nodes: int
    edges: int
    branches: int
    code_characters: int
    retry_nodes: int
    duplicate_shapes: int
    cycles: int

    def as_dict(self):
        return asdict(self)


def workflow_structure(workflow):
    nodes = workflow.get("nodes", []) if isinstance(workflow, dict) else []
    connections = workflow.get("connections", {}) if isinstance(workflow, dict) else {}
    edges = branches = 0
    graph = {node.get("name"): set() for node in nodes if isinstance(node, dict) and node.get("name")}
    for source, groups in connections.items():
        outputs = groups.get("main", []) if isinstance(groups, dict) else []
        branches += max(0, len(outputs) - 1)
        for output in outputs:
            if not isinstance(output, list):
                continue
            edges += len(output)
            for edge in output:
                if isinstance(edge, dict) and edge.get("node") in graph:
                    graph.setdefault(source, set()).add(edge["node"])
    shapes = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        shape = (node.get("type"), json.dumps(node.get("parameters", {}), sort_keys=True))
        shapes[shape] = shapes.get(shape, 0) + 1
    return Structure(
        nodes=len(nodes), edges=edges, branches=branches,
        code_characters=sum(len(str(node.get("parameters", {}).get("jsCode", ""))) for node in nodes if isinstance(node, dict)),
        retry_nodes=sum(bool(node.get("retryOnFail")) for node in nodes if isinstance(node, dict)),
        duplicate_shapes=sum(count - 1 for count in shapes.values() if count > 1),
        cycles=_cycle_count(graph),
    )


def _cycle_count(graph):
    visiting, visited, cycles = set(), set(), 0

    def visit(node):
        nonlocal cycles
        if node in visiting:
            cycles += 1
            return
        if node in visited:
            return
        visiting.add(node)
        for target in graph.get(node, ()):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
    return cycles


def failure_category(errors):
    codes = {error.get("code", "") for error in errors}
    if not errors:
        return "completed"
    if "UNBOUNDED_CONTROL_FLOW" in codes:
        return "control_flow"
    if "N8N_EXECUTION_TIMEOUT" in codes or any("timed out" in error.get("message", "").lower() for error in errors):
        return "execution_timeout"
    if any(code.startswith("N8N_IMPORT") for code in codes):
        return "import"
    if any(code.startswith("N8N_EXECUTION") for code in codes):
        return "execution"
    return "validation"


def repair_mode(category):
    return "architectural_replan" if category in {"control_flow", "execution_timeout"} else "targeted_local_repair"


def structural_regression(previous, current, previous_status, current_status):
    """Reject large relative growth unless it advances execution status."""
    rank = {"validation": 0, "import": 1, "control_flow": 1, "execution": 2, "execution_timeout": 2, "completed": 3}
    if rank.get(current_status, 0) > rank.get(previous_status, 0):
        return False
    node_growth = current.nodes / max(1, previous.nodes)
    edge_growth = current.edges / max(1, previous.edges)
    duplicate_growth = current.duplicate_shapes - previous.duplicate_shapes
    return (node_growth > 2 or edge_growth > 2) and duplicate_growth > 2


class McpCompositionRunner:
    def __init__(self, generator_factory, runtime, output_dir, max_iterations=3):
        self.generator_factory = generator_factory
        self.runtime = runtime
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=False)
        self.max_iterations = max_iterations

    def run(self, challenge):
        records = []
        workflow_id = None
        feedback = None
        accepted = None
        for number in range(1, self.max_iterations + 1):
            iteration_dir = self.output_dir / f"iteration-{number:02d}"
            generator = self.generator_factory(iteration_dir)
            workflow, provenance = generator.generate(
                challenge, existing_workflow_id=workflow_id, iteration_feedback=feedback,
            )
            workflow_id = workflow["id"]
            structure = workflow_structure(workflow)
            started = time.monotonic()
            errors = issues_as_dicts(validate_n8n_workflow(workflow, challenge))
            validation_status = "failed" if errors else "passed"
            import_status = "not_run"
            execution_status = "not_run"
            if not errors:
                import_errors = self.runtime.validate_import(workflow, iteration_dir / "runtime-import")
                errors.extend(import_errors)
                import_status = "failed" if import_errors else "passed"
            if not errors:
                execution_errors = self.runtime.validate_execution(workflow, iteration_dir / "workflow.json", challenge)
                errors.extend(execution_errors)
                execution_status = "failed" if execution_errors else "completed"
            duration = round(time.monotonic() - started, 4)
            category = failure_category(errors)
            regression = False
            if accepted:
                regression = structural_regression(
                    Structure(**accepted["structure"]), structure,
                    accepted["failure_category"], category,
                )
            record = {
                "iteration": number,
                "workflow_id": workflow_id,
                "workflow_digest": provenance["workflow_digest"],
                "hypothesis": provenance.get("hypothesis"),
                "repair_scope": provenance.get("repair_scope"),
                "composition_plan": provenance.get("composition_plan", []),
                "validation_status": validation_status,
                "import_status": import_status,
                "execution_status": execution_status,
                "execution_duration_seconds": duration,
                "failure_category": category,
                "errors": errors,
                "structure": structure.as_dict(),
                "structural_regression": regression,
                "manually_edited": False,
            }
            save_json(iteration_dir / "iteration-observation.json", record)
            records.append(record)
            if not regression:
                accepted = record
            if execution_status == "completed":
                save_json(self.output_dir / "history.json", records)
                save_json(self.output_dir / "final.json", record)
                return workflow, records
            feedback = {
                "failure_category": "structural_regression" if regression else category,
                "repair_mode": "architectural_replan" if regression else repair_mode(category),
                "errors": errors,
                "current_structure": structure.as_dict(),
                "accepted_iteration": accepted,
                "instruction": (
                    "Restore the accepted workflow version before making a smaller repair; the last change was an obvious structural regression."
                    if regression else "Preserve working nodes and change only what the failure requires."
                ),
            }
        save_json(self.output_dir / "history.json", records)
        raise RuntimeError(f"No executable MCP workflow after {self.max_iterations} bounded iterations")
