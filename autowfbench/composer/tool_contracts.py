"""Public tool descriptions supplied to candidate generators.

These descriptions mirror the public Solution API documentation. They contain
no fixtures, scorecard data, verifier logic, or evaluator feedback.
"""

TOOL_CONTRACTS = {
    "inquiry.read": "Arguments: {}. Returns the public inquiry, lead ID, and authorized contact.",
    "documents.read": "Arguments: {}. Returns service, qualification, and communication policies.",
    "research.read": "Arguments: {}. Returns public company-profile research and contact authority.",
    "customer.ask": "Arguments: {questions: [nonempty strings]}. Returns customer qualification facts.",
    "crm.read": "Arguments: {}. Returns the current lead snapshot.",
    "crm.update": "Arguments: {changes: object}. May return a retryable failure; only public writable fields are accepted.",
    "followup.create": "Arguments: {lead_id, type, status}. Creates a follow-up.",
    "customer.send": "Arguments: {recipient, body}. Sends the final response to the authorized contact.",
    "incident.read": "Arguments: {}. Returns incident, deployment, and patch-contract evidence.",
    "source.read": "Arguments: {}. Returns the constrained checkout source.",
    "checkout.patch": "Arguments: {old: exact source fragment, new: replacement}. Applies one constrained replacement.",
    "tests.run": "Arguments: {}. Runs the public checkout simulator tests.",
}


def contracts_for(capabilities):
    return {name: TOOL_CONTRACTS.get(name, "Public capability; arguments are not documented.") for name in capabilities}
