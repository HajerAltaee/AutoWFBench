"""Public simApp contracts; no grading rules or scenario fixtures."""
import copy


def obj(properties=None, required=None):
    properties = properties or {}
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required, "additionalProperties": False}


TEXT = {"type": "string", "minLength": 1}
NUMBER = {"type": "number", "minimum": 0}
FACTS = {
    "budget_aed": {"type": ["number", "null"], "minimum": 0},
    "timeline_weeks": {"type": ["integer", "null"], "minimum": 1},
    "volume": {"type": ["integer", "null"], "minimum": 0},
    "languages": {"type": "array", "items": TEXT, "minItems": 1},
    "crm": TEXT, "channel": TEXT, "human_handoff": {"type": "boolean"},
}
ROUTES = {
    "qualified": {"status": "Qualified", "next_action": "discovery_call", "owner": "sales_coordinator"},
    "not_qualified": {"status": "NotQualified", "next_action": "close_lost", "owner": "sales_coordinator"},
    "needs_review": {"status": "NeedsReview", "next_action": "clarify_requirements", "owner": "sales_coordinator"},
}
POLICY = {
    "qualification": {"minimum_budget_aed": 100000, "maximum_timeline_weeks": 16},
    "supported": {"channel": ["WhatsApp"], "languages": ["Arabic", "English"], "human_handoff": True},
    "subject_to_assessment": ["Salesforce", "HubSpot"],
    "routes": ROUTES,
    "decision": "Missing/null facts => needs_review. Otherwise budget below minimum, timeline above maximum, unsupported channel/language or CRM => not_qualified. Otherwise qualified; CRM integration still needs assessment.",
    "followup": {"qualified": "discovery_call", "not_qualified": "close_lost", "needs_review": "clarify_requirements", "status": "pending"},
    "communication": "Do not guarantee price, deployment, accuracy or compliance. State the actual route, open questions and next step. On permanent write failure, do not create a follow-up; report the block and contact the customer honestly.",
}
CHANGE_FIELDS = {**FACTS, **{k: {"enum": sorted({v[k] for v in ROUTES.values()})} for k in ("status", "next_action", "owner")}}
LEAD = obj({"lead_id": TEXT, "company": TEXT, "contact": TEXT, "status": TEXT, **{k:v for k,v in CHANGE_FIELDS.items() if k != "status"}}, ["lead_id", "company", "contact", "status"])

DISCOVERY_TOPICS = [
    "role_authority", "goals", "pain_points", "stakeholders", "budget",
    "timeline", "constraints", "data_consent", "current_customer",
    "requirements_confirmation",
]
DISCOVERY_FACTS = {
    "role": TEXT,
    "decision_authority": {"type": ["boolean", "null"]},
    "goals": {"type": "array", "items": TEXT},
    "pain_points": {"type": "array", "items": TEXT},
    "stakeholders": {"type": "array", "items": TEXT},
    "budget_status": {"enum": ["approved", "unclear", "unknown"]},
    "budget_aed": {"type": ["number", "null"], "minimum": 0},
    "timeline_weeks": {"type": ["integer", "null"], "minimum": 1},
    "needs": {"type": "array", "items": TEXT},
    "constraints": {"type": "array", "items": TEXT},
    "current_customer": {"type": "boolean"},
    "consent": {"enum": ["full", "summary_only", "minimal"]},
    "requirements_revision": {"type": "integer", "minimum": 1},
}
DISCOVERY_CHANGES = {
    "lifecycle_stage": {"enum": ["Lead", "Opportunity", "Customer"]},
    "discovery_status": {"enum": ["New", "ActiveCustomer", "DiscoveryIncomplete", "StakeholderNeeded", "PrivacyReview", "ExistingCustomerExpansion", "DiscoveryComplete"]},
    "role": TEXT,
    "decision_authority": {"type": ["boolean", "null"]},
    "budget_status": DISCOVERY_FACTS["budget_status"],
    "budget_aed": DISCOVERY_FACTS["budget_aed"],
    "timeline_weeks": DISCOVERY_FACTS["timeline_weeks"],
    "needs": DISCOVERY_FACTS["needs"],
    "stakeholders": DISCOVERY_FACTS["stakeholders"],
    "privacy_scope": DISCOVERY_FACTS["consent"],
    "discovery_summary": {"type": ["string", "null"]},
    "requirements_revision": DISCOVERY_FACTS["requirements_revision"],
}
CONTACT = obj({
    "contact_id": TEXT, "email": TEXT, "company_id": TEXT, "name": TEXT,
    **DISCOVERY_CHANGES,
}, ["contact_id", "email", "company_id", "name", "lifecycle_stage", "discovery_status"])


def shape(value):
    """Expose response field names/types without pinning runtime business values."""
    if isinstance(value, dict):
        return obj({k:shape(v) for k,v in value.items()})
    if isinstance(value, list):
        return {"type":"array", "items":shape(value[0])}
    return {"type": "boolean" if isinstance(value, bool) else "number" if isinstance(value, (int,float)) else "string"}


def operation(app, name, doc, arguments, result):
    return {"app": app, "operation": name, "method": "POST", "path": "/apps/" + app + "/" + name, "doc": doc, "arguments": arguments, "result": result}


CRM = [
    operation("messaging", "inquiry.read", "Read the inquiry and authorized contact.", obj(), obj({"lead_id": TEXT, "contact": TEXT, "body": TEXT})),
    operation("policy", "documents.read", "Read qualification rules, routes and communication constraints.", obj(), shape(POLICY)),
    operation("research", "research.read", "Read company evidence and contact authority.", obj(), obj({"company": TEXT, "industry": TEXT, "contact_authority": TEXT, "sources": {"type": "array", "items": TEXT}})),
    operation("messaging", "customer.ask", "Ask for all seven qualification fields in one clear message. Null means unknown; never invent it.", obj({"questions": {"type": "array", "items": TEXT, "minItems": 1, "maxItems": 7}}), obj(FACTS)),
    operation("crm", "crm.read", "Read the current lead; compare fields after any write before dependent actions.", obj(), LEAD),
    operation("crm", "crm.update", "Update only provided fields. Use one idempotency key per intended change. Retry only retryable errors, at most three attempts. An ambiguous response may have committed; reuse the key and read back. Permanent errors leave state unchanged.", obj({"changes": {**obj(CHANGE_FIELDS, []), "minProperties": 1}, "idempotency_key": TEXT}), LEAD),
    operation("crm", "followup.create", "After verified lead update create exactly one route-appropriate follow-up. Reusing the same key never duplicates it.", obj({"lead_id": TEXT, "type": {"enum": ["discovery_call", "close_lost", "clarify_requirements"]}, "status": {"const": "pending"}, "idempotency_key": TEXT}), obj({"followup_id": TEXT})),
    operation("crm", "followup.read", "Read all follow-ups for this run to verify delivery and detect duplicates.", obj(), {"type": "array", "items": obj({"followup_id": TEXT, "lead_id": TEXT, "type": TEXT, "status": TEXT})}),
    operation("messaging", "customer.send", "Send one concise final message to the inquiry contact; provide an idempotency key.", obj({"recipient": TEXT, "body": TEXT, "idempotency_key": TEXT}), obj({"sent": {"type": "boolean"}, "message_id": TEXT})),
]
SIMSPOT = [
    operation("messaging", "inquiry.read", "Read the inbound discovery request and authorized contact. The contact and company identifiers are immutable.", obj(), obj({"incoming_contact_id": TEXT, "email": TEXT, "company_id": TEXT, "body": TEXT})),
    operation("policy", "discovery.guide.read", "Read the discovery topics, consent rules, routing rules and allowed follow-ups. Ask rather than infer missing facts.", obj(), obj({
        "required_topics": {"type": "array", "items": {"enum": DISCOVERY_TOPICS}},
        "consent_rules": obj({"full": {"type": "array", "items": TEXT}, "summary_only": {"type": "array", "items": TEXT}, "minimal": {"type": "array", "items": TEXT}}),
        "routes": obj({k: obj({"lifecycle_stage": TEXT, "discovery_status": TEXT, "followup": TEXT}) for k in ("existing_customer", "privacy", "stakeholder", "unclear_budget", "complete")}),
    })),
    operation("simspot", "contacts.search", "Search before writing so an existing customer or duplicate is updated instead of creating another contact.", obj({"email": TEXT, "company_id": TEXT}, []), {"type": "array", "items": CONTACT}),
    operation("messaging", "customer.ask", "Ask explicit discovery topics. Use a separate requirements_confirmation round after the initial discovery so changed requirements replace stale ones.", obj({"topics": {"type": "array", "items": {"enum": DISCOVERY_TOPICS}, "minItems": 1, "uniqueItems": True}}), obj(DISCOVERY_FACTS)),
    operation("simspot", "contact.read", "Read a SimSpot contact by immutable ID; use after writes to verify the stored state.", obj({"contact_id": TEXT}), CONTACT),
    operation("simspot", "contact.update", "Update the selected existing contact only. Respect consent_rules, reuse an idempotency key for retries, and read back before dependent actions.", obj({"contact_id": TEXT, "changes": {**obj(DISCOVERY_CHANGES, []), "minProperties": 1}, "idempotency_key": TEXT}), CONTACT),
    operation("simspot", "followup.create", "After verified contact readback, create exactly one route-appropriate follow-up.", obj({"contact_id": TEXT, "type": {"enum": ["clarify_budget", "stakeholder_intro", "account_review", "privacy_review", "solution_workshop"]}, "status": {"const": "pending"}, "idempotency_key": TEXT}), obj({"followup_id": TEXT})),
    operation("simspot", "followup.read", "Read all SimSpot follow-ups to verify the intended task and detect duplicates.", obj(), {"type": "array", "items": obj({"followup_id": TEXT, "contact_id": TEXT, "type": TEXT, "status": TEXT})}),
    operation("messaging", "customer.send", "Send one concise final response to the inquiry email. State confirmed facts, open questions, privacy handling and the real next step without unsupported commitments.", obj({"recipient": TEXT, "body": TEXT, "idempotency_key": TEXT}), obj({"sent": {"type": "boolean"}, "message_id": TEXT})),
]
CHECKOUT = [
    operation("incidents", "incident.read", "Read failed orders, recent deployment and patch contract. Do not assume the affected currency.", obj(), obj({"failed_orders": {"type": "array", "items": obj({"order_id": TEXT, "amount": NUMBER, "currency": TEXT})}, "deployment": TEXT, "patch_contract": TEXT})),
    operation("repository", "source.read", "Read checkout.py from the run's isolated simulated repository.", obj(), obj({"path": TEXT, "content": TEXT})),
    operation("repository", "checkout.patch", "Replace one unique old source fragment with new. Keep changes minimal. Reuse the idempotency key for at most three retryable attempts; permanent errors require reporting a block. Ambiguous responses may have committed. Read back before claiming repair.", obj({"old": TEXT, "new": TEXT, "idempotency_key": TEXT}), obj({"updated": TEXT})),
    operation("tests", "tests.run", "Run public EUR/USD positive and invalid-input tests. Observe failure before editing and verify after. Payment validation must remain intact.", obj(), obj({"passed": {"type": "boolean"}, "cases": {"type": "array", "items": obj({"name":TEXT, "passed":{"type":"boolean"}, "actual":obj({"status":{"type":"integer"}, "amount":NUMBER, "currency":TEXT, "error":TEXT}, ["status"])}, ["name","passed"])}})),
]


def catalog(kind):
    operations = {"crm": CRM, "simspot": SIMSPOT, "checkout": CHECKOUT}.get(kind)
    if operations is None:
        raise ValueError("Unknown simApp implementation")
    return {"version": "2.0.0", "doc": "simApps use the run-scoped Bearer token. POST each path with the argument object. HTTP 200 wraps business results as {ok:true,value:<result schema>} or {ok:false,error:{code,message,retryable}}. Inspect ok. GET /apps returns this catalog. Read operations are side-effect free. Instances are reset for every run. Never access /admin. Runtime data, not example constants, must drive decisions.", "operations": copy.deepcopy(operations)}
