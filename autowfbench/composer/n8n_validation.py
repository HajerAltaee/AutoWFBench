"""Deterministic validation for Composer-generated native n8n workflows."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from typing import Any


N8N_VERSION = "2.42.3"
N8N_IMAGE = "n8nio/n8n@sha256:240eaa2a3d491adac5817aa4c3f1c521bb18ec79f6e448517158d5220ee0f37b"
ALLOWED_NODE_VERSIONS = {
    "n8n-nodes-base.manualTrigger": {1},
    "n8n-nodes-base.httpRequest": {4, 4.1, 4.2},
    "n8n-nodes-base.if": {2, 2.1, 2.2},
    "n8n-nodes-base.set": {3, 3.1, 3.2, 3.3, 3.4},
    "n8n-nodes-base.merge": {3, 3.1, 3.2},
}
TOP_LEVEL_FIELDS = {"id", "name", "nodes", "connections", "settings", "active"}
NODE_FIELDS = {
    "id", "name", "type", "typeVersion", "position", "parameters", "disabled",
    "executeOnce", "alwaysOutputData", "retryOnFail", "maxTries", "waitBetweenTries", "onError",
}
NODE_REFERENCE_PATTERNS = (
    re.compile(r"\$\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    re.compile(r"\$node\[\s*['\"]([^'\"]+)['\"]\s*\]"),
)
SECRET_KEY = re.compile(r"(?:password|secret|api[_-]?key|access[_-]?token|credential)", re.I)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str

    def as_dict(self):
        return asdict(self)


def _walk(value: Any, path="$."):
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, f"{path}{key}.")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}].")


def _issue(issues, code, path, message):
    issues.append(ValidationIssue(code, path, message))


def parse_workflow_json(text: str):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Workflow output must be nonempty JSON text")
    if len(text) > 500_000:
        raise ValueError("Workflow JSON exceeds 500000 characters")
    return json.loads(text, object_pairs_hook=_reject_duplicate_keys)


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def validate_n8n_workflow(workflow, challenge):
    """Return stable, public validation errors; an empty list means statically valid."""
    issues: list[ValidationIssue] = []
    if not isinstance(workflow, dict):
        return [ValidationIssue("WORKFLOW_NOT_OBJECT", "$", "Workflow must be a JSON object")]
    missing = TOP_LEVEL_FIELDS - set(workflow)
    extra = set(workflow) - TOP_LEVEL_FIELDS
    if missing:
        _issue(issues, "MISSING_WORKFLOW_FIELDS", "$", f"Missing fields: {sorted(missing)}")
    if extra:
        _issue(issues, "UNSUPPORTED_WORKFLOW_FIELDS", "$", f"Unsupported generated fields: {sorted(extra)}")
    if issues:
        return issues
    try:
        uuid.UUID(str(workflow["id"]))
    except (ValueError, TypeError, AttributeError):
        _issue(issues, "INVALID_WORKFLOW_ID", "$.id", "Workflow id must be a UUID accepted by the pinned n8n runtime")
    if not isinstance(workflow["name"], str) or not workflow["name"].strip():
        _issue(issues, "INVALID_WORKFLOW_NAME", "$.name", "Workflow name must be nonempty")
    if workflow["active"] is not False:
        _issue(issues, "WORKFLOW_MUST_BE_INACTIVE", "$.active", "Generated workflows must be imported inactive")
    if not isinstance(workflow["settings"], dict):
        _issue(issues, "INVALID_SETTINGS", "$.settings", "settings must be an object")
    nodes = workflow["nodes"]
    if not isinstance(nodes, list) or not 2 <= len(nodes) <= 80:
        _issue(issues, "INVALID_NODES", "$.nodes", "nodes must contain 2-80 node objects")
        return issues
    names, ids, by_name = set(), set(), {}
    for index, node in enumerate(nodes):
        path = f"$.nodes[{index}]"
        if not isinstance(node, dict):
            _issue(issues, "NODE_NOT_OBJECT", path, "Node must be an object")
            continue
        required = {"id", "name", "type", "typeVersion", "position", "parameters"}
        if required - set(node):
            _issue(issues, "MISSING_NODE_FIELDS", path, f"Missing fields: {sorted(required - set(node))}")
            continue
        if set(node) - NODE_FIELDS:
            _issue(issues, "UNSUPPORTED_NODE_FIELDS", path, f"Unsupported fields: {sorted(set(node) - NODE_FIELDS)}")
        name, node_id, node_type, version = node["name"], node["id"], node["type"], node["typeVersion"]
        if not isinstance(name, str) or not name:
            _issue(issues, "INVALID_NODE_NAME", path + ".name", "Node name must be nonempty")
        elif name in names:
            _issue(issues, "DUPLICATE_NODE_NAME", path + ".name", f"Duplicate node name: {name}")
        else:
            names.add(name); by_name[name] = node
        try:
            uuid.UUID(str(node_id))
        except (ValueError, TypeError, AttributeError):
            _issue(issues, "INVALID_NODE_ID", path + ".id", "Node id must be a UUID")
        if node_id in ids:
            _issue(issues, "DUPLICATE_NODE_ID", path + ".id", f"Duplicate node id: {node_id}")
        ids.add(node_id)
        if node_type not in ALLOWED_NODE_VERSIONS:
            _issue(issues, "DISALLOWED_NODE_TYPE", path + ".type", f"Node type is not allowed: {node_type}")
        elif version not in ALLOWED_NODE_VERSIONS[node_type]:
            _issue(issues, "UNSUPPORTED_NODE_VERSION", path + ".typeVersion", f"Unsupported {node_type} version: {version}")
        if not isinstance(node["parameters"], dict):
            _issue(issues, "INVALID_NODE_PARAMETERS", path + ".parameters", "parameters must be an object")
        if not isinstance(node["position"], list) or len(node["position"]) != 2 or not all(isinstance(v, (int, float)) for v in node["position"]):
            _issue(issues, "INVALID_NODE_POSITION", path + ".position", "position must be two numbers")
        if "credentials" in node:
            _issue(issues, "CREDENTIALS_FORBIDDEN", path + ".credentials", "Generated workflows must not embed credential bindings")
    triggers = [node for node in nodes if isinstance(node, dict) and node.get("type") == "n8n-nodes-base.manualTrigger"]
    if len(triggers) != 1:
        _issue(issues, "INVALID_TRIGGER_COUNT", "$.nodes", "Exactly one Manual Trigger is required for adapter execution")
    connections = workflow["connections"]
    if not isinstance(connections, dict):
        _issue(issues, "INVALID_CONNECTIONS", "$.connections", "connections must be an object")
        return issues
    adjacency = {name: set() for name in names}
    for source, groups in connections.items():
        if source not in names:
            _issue(issues, "UNKNOWN_CONNECTION_SOURCE", f"$.connections.{source}", f"Unknown source node: {source}")
            continue
        if not isinstance(groups, dict) or set(groups) - {"main"} or "main" not in groups or not isinstance(groups["main"], list):
            _issue(issues, "INVALID_CONNECTION_GROUP", f"$.connections.{source}", "Only a main connection array is supported")
            continue
        for output_index, branch in enumerate(groups["main"]):
            if not isinstance(branch, list):
                _issue(issues, "INVALID_CONNECTION_BRANCH", f"$.connections.{source}.main[{output_index}]", "Connection branch must be an array")
                continue
            for edge_index, edge in enumerate(branch):
                edge_path = f"$.connections.{source}.main[{output_index}][{edge_index}]"
                if not isinstance(edge, dict) or set(edge) != {"node", "type", "index"}:
                    _issue(issues, "INVALID_CONNECTION", edge_path, "Connection requires exactly node, type, and index")
                    continue
                target = edge["node"]
                if target not in names:
                    _issue(issues, "UNKNOWN_CONNECTION_TARGET", edge_path + ".node", f"Unknown target node: {target}")
                else:
                    adjacency[source].add(target)
                if edge["type"] != "main" or type(edge["index"]) is not int or edge["index"] < 0:
                    _issue(issues, "INVALID_CONNECTION_PORT", edge_path, "Only nonnegative main input indexes are supported")
    if triggers:
        start = triggers[0].get("name")
        seen, stack = set(), [start]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current); stack.extend(adjacency.get(current, ()))
        for name in sorted(names - seen):
            _issue(issues, "UNREACHABLE_NODE", "$.nodes", f"Node is unreachable from the trigger: {name}")
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or not isinstance(node.get("parameters"), dict):
            continue
        encoded = json.dumps(node["parameters"], ensure_ascii=False)
        for pattern in NODE_REFERENCE_PATTERNS:
            for reference in pattern.findall(encoded):
                if reference not in names:
                    _issue(issues, "UNKNOWN_NODE_REFERENCE", f"$.nodes[{index}].parameters", f"Expression references unknown node: {reference}")
        if node.get("type") == "n8n-nodes-base.httpRequest":
            _validate_http_node(issues, node, index, set(challenge.get("capabilities", ())))
    for path, value in _walk(workflow):
        if isinstance(value, dict):
            for key, item in value.items():
                if SECRET_KEY.search(str(key)) and isinstance(item, str) and item and "$env." not in item:
                    _issue(issues, "EMBEDDED_SECRET", path + str(key), "Secrets and credentials must come from adapter-provided environment variables")
    return issues


def _validate_http_node(issues, node, index, capabilities):
    path, parameters = f"$.nodes[{index}].parameters", node["parameters"]
    required = {"method", "url", "sendHeaders", "headerParameters", "sendBody", "specifyBody", "jsonBody", "options"}
    if required - set(parameters):
        _issue(issues, "MISSING_HTTP_PARAMETERS", path, f"Missing HTTP Request parameters: {sorted(required - set(parameters))}")
        return
    if parameters.get("method") != "POST":
        _issue(issues, "INVALID_HTTP_METHOD", path + ".method", "Benchmark tools require POST")
    if "$env.AWB_ENV_BASE_URL" not in str(parameters.get("url")) or "/tools" not in str(parameters.get("url")):
        _issue(issues, "INVALID_TOOL_URL", path + ".url", "Tool URL must derive from $env.AWB_ENV_BASE_URL and end in /tools")
    if "$env.AWB_ENV_ACCESS_TOKEN" not in json.dumps(parameters.get("headerParameters")):
        _issue(issues, "INVALID_TOOL_AUTH", path + ".headerParameters", "Authorization must derive from $env.AWB_ENV_ACCESS_TOKEN")
    body = parameters.get("jsonBody")
    if not isinstance(body, str):
        _issue(issues, "INVALID_TOOL_BODY", path + ".jsonBody", "jsonBody must be an n8n expression string")
        return
    mentioned = {capability for capability in capabilities if capability in body}
    if len(mentioned) != 1:
        _issue(issues, "INVALID_CAPABILITY_OPERATION", path + ".jsonBody", "Each HTTP Request must identify exactly one public challenge capability")


def issues_as_dicts(issues):
    return [issue.as_dict() for issue in issues]
