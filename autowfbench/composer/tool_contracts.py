"""Public tool descriptions supplied to candidate generators.

These descriptions mirror the public Solution API documentation. They contain
no fixtures, scorecard data, verifier logic, or evaluator feedback.
"""

TOOL_CONTRACTS = {
    "inquiry.read": "Arguments: {}. Returns the public inquiry, lead ID, and authorized contact. Result envelope: {ok: true, value} or {ok: false, error}.",
    "documents.read": "Arguments: {}. Returns service, qualification, and communication policies.",
    "research.read": "Arguments: {}. Returns public company-profile research and contact authority.",
    "customer.ask": "Arguments: {questions: [nonempty strings]}. Returns customer qualification facts.",
    "crm.read": "Arguments: {}. Returns the current lead snapshot.",
    "crm.update": "Arguments: {changes: object}. Writable fields are status, budget_aed, timeline_weeks, volume, languages, crm, channel, human_handoff, next_action, and owner. Preserve protected identity fields. Results use the application envelope {ok: true, value} or {ok: false, error: {retryable, ...}} even when HTTP status is 200.",
    "followup.create": "Arguments: {lead_id, type, status}. For a discovery-call follow-up use type='discovery_call' and status='pending_scheduling'. Returns an application-level result envelope.",
    "customer.send": "Arguments: {recipient, body}. Sends the final response only to the authorized contact and returns an application-level result envelope.",
    "incident.read": "Arguments: {}. Returns incident, deployment, and patch-contract evidence.",
    "source.read": "Arguments: {}. Returns the constrained checkout source.",
    "checkout.patch": "Arguments: {old: exact source fragment, new: replacement}. Applies one constrained replacement.",
    "tests.run": "Arguments: {}. Runs the public checkout simulator tests.",
}


def contracts_for(capabilities):
    return {name: TOOL_CONTRACTS.get(name, "Public capability; arguments are not documented.") for name in capabilities}
