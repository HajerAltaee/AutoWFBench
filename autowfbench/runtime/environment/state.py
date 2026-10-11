"""Benchmark-owned simulators. Each engine attempt launches a separate process.

No candidate code is evaluated by this service. The checkout fixture interprets
a deliberately small, validated AST; unrestricted Python needs a real sandbox.
"""
from __future__ import annotations

import ast
import copy
import json
import threading

from autowfbench.core.common import now


class ToolFailure(Exception):
    def __init__(self, code, message, retryable=False):
        self.code, self.message, self.retryable = code, message, retryable


def require(condition, message):
    if not condition:
        raise ToolFailure("INVALID_ARGUMENT", message)


def checkout_program(source):
    """Validate the full program before interpretation, including unused branches."""
    require(isinstance(source, str) and len(source) <= 6000, "Invalid source")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ToolFailure("INVALID_SOURCE", str(exc))
    require(len(tree.body) == 1 and isinstance(tree.body[0], ast.FunctionDef), "One function required")
    fn = tree.body[0]
    require(fn.name == "checkout" and [a.arg for a in fn.args.args] == ["amount", "currency"], "Keep checkout signature")
    require(not (fn.decorator_list or fn.args.defaults or fn.args.kwonlyargs or fn.args.posonlyargs or fn.args.vararg or fn.args.kwarg or fn.returns or fn.type_comment), "Unsupported function definition")
    require(all(a.annotation is None for a in fn.args.args), "Annotations are unsupported")

    def check_return(node):
        require(isinstance(node, ast.Return), "Expected return")
        call = node.value
        require(isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "charge_card", "Only charge_card calls allowed")
        require(len(call.args) == 2 and not call.keywords, "Two positional arguments required")
        require(all(isinstance(a, ast.Name) and a.id in ("amount", "currency") for a in call.args), "Arguments must reference input values")

    if len(fn.body) == 1:
        check_return(fn.body[0])
    else:
        require(len(fn.body) == 2 and isinstance(fn.body[0], ast.If), "Unsupported checkout structure")
        branch = fn.body[0]
        test = branch.test
        require(isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "currency" and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq) and len(test.comparators) == 1 and isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value in ("EUR", "USD"), "Only a currency comparison is allowed")
        require(len(branch.body) == 1 and not branch.orelse, "Unsupported branch")
        check_return(branch.body[0]); check_return(fn.body[1])
    return fn


def checkout(source, amount, currency):
    fn = checkout_program(source)
    node = fn.body[-1]
    if isinstance(fn.body[0], ast.If) and currency == fn.body[0].test.comparators[0].value:
        node = fn.body[0].body[0]
    values = {"amount": amount, "currency": currency}
    amount, currency = [values[a.id] for a in node.value.args]
    if isinstance(amount, bool) or not isinstance(amount, (float, int)) or amount <= 0 or currency not in ("EUR", "USD"):
        return {"status": 500, "error": "Invalid payment"}
    return {"status": 200, "amount": amount, "currency": currency}


class ChallengeEnvironment:
    def __init__(self, package, seed=0):
        from autowfbench.runtime.environment.apps import catalog
        import fastjsonschema
        self.package, self.seed = package, seed
        self.kind = package["environment"]["implementation"]
        self.fixtures = copy.deepcopy(package["environment"]["fixtures"])
        self.lock = threading.RLock()
        self.events, self.calls, self.frozen = [], 0, False
        self.scenario = seed % 6
        self.failures = 1 if self.scenario in (1, 3) else 0
        self.receipts, self.mutations = {}, []
        self.validators = {op["operation"]: fastjsonschema.compile(op["arguments"]) for op in catalog(self.kind)["operations"]}
        f = self.fixtures
        if self.kind == "crm":
            f.update(lead_id=f"LEAD-{1007+seed}", contact=f"customer-{seed}@crescent.example", budget_aed=180000+(seed % 5)*10000, volume=18000+seed*731)
            if self.scenario == 2:
                f["budget_aed"] = 40000 + seed*100
            if self.scenario == 3:
                f["timeline_weeks"] = None
            if seed >= 6:
                f.update(crm="HubSpot", languages=["English"], timeline_weeks=None if self.scenario == 3 else 10+seed % 4)
            self.state = {"lead": {k: f[k] for k in ("lead_id", "company", "contact", "status")}, "messages": [], "followups": [], "customer_replied": False}
        elif self.kind == "simspot":
            self.case = copy.deepcopy(f["cases"][seed % len(f["cases"])])
            self.scenario = seed % len(f["cases"])
            self.failures = 0
            self.state = {
                "contacts": copy.deepcopy(self.case["starting_contacts"]),
                "messages": [],
                "followups": [],
                "customer_replied": False,
            }
        else:
            currency = "USD" if self.scenario == 1 else "EUR"
            f["source"] = f'def checkout(amount, currency):\n    if currency == "{currency}":\n        return charge_card(currency, amount)\n    return charge_card(amount, currency)\n'
            if self.scenario == 2:
                f["source"] = 'def checkout(amount, currency):\n    return charge_card(currency, amount)\n'
            if seed >= 6:
                f["source"] = f["source"].replace('    ', '  ')
            f["failed_orders"] = [{"order_id": f"ORDER-{seed}", "amount": round(34.2+seed*1.13, 2), "currency": currency}]
            f["deployment"] = "Recent checkout refactor changed payment argument handling; inspect source and tests to establish impact."
            self.state = {"source": f["source"], "patches": []}
        self.initial = copy.deepcopy(self.state)

    def event(self, operation, arguments, result):
        self.events.append({"id": f"env-{len(self.events) + 1:04d}", "source": "environment", "timestamp": now(), "kind": "tool_call", "data": {"operation": operation, "arguments": copy.deepcopy(arguments), "result": copy.deepcopy(result)}})

    def execute(self, operation, arguments):
        import fastjsonschema
        with self.lock:
            if self.frozen:
                return {"ok": False, "error": {"code": "RUN_CLOSED", "message": "Run is frozen", "retryable": False}}
            self.calls += 1
            try:
                if self.calls > self.package["definition"]["limits"]["tool_calls"]:
                    raise ToolFailure("TOOL_LIMIT", "Tool budget exhausted")
                if operation not in self.validators:
                    raise ToolFailure("UNKNOWN_TOOL", str(operation))
                self.validators[operation](arguments)
                key = (operation, arguments.get("idempotency_key"))
                if key in self.receipts:
                    prior, value = self.receipts[key]
                    require(prior == arguments, "Idempotency key reused with different arguments")
                else:
                    is_write = operation in ("crm.update", "contact.update", "checkout.patch")
                    if is_write and self.kind != "simspot" and self.scenario == 4:
                        raise ToolFailure("WRITE_FORBIDDEN", "Write access revoked; do not retry")
                    if is_write and self.failures:
                        self.failures -= 1
                        raise ToolFailure("TEMPORARILY_UNAVAILABLE", "Retry with the same idempotency key", True)
                    value = self.crm(operation, arguments) if self.kind == "crm" else self.simspot(operation, arguments) if self.kind == "simspot" else self.incident(operation, arguments)
                    if key[1]:
                        self.receipts[key] = (copy.deepcopy(arguments), copy.deepcopy(value))
                        self.mutations.append(operation)
                    if is_write and self.scenario == 5:
                        raise ToolFailure("AMBIGUOUS_COMMIT", "Write response lost; verify state or retry with the same key", True)
                result = {"ok": True, "value": copy.deepcopy(value)}
            except ToolFailure as exc:
                result = {"ok": False, "error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable}}
            except (fastjsonschema.JsonSchemaException, KeyError, TypeError, ValueError) as exc:
                result = {"ok": False, "error": {"code": "INVALID_ARGUMENT", "message": str(exc), "retryable": False}}
            self.event(operation, arguments, result)
            return result

    def crm(self, op, a):
        from autowfbench.runtime.environment.apps import FACTS, POLICY
        f = self.fixtures
        if op == "inquiry.read":
            return {"lead_id": f["lead_id"], "contact": f["contact"], "body": "We need customer support automation with escalation to employees. Can you help?"}
        if op == "documents.read":
            return copy.deepcopy(POLICY)
        if op == "research.read":
            return {"company": f["company"], "industry": "Retail", "contact_authority": "Operations Director", "sources": ["fixture/company-profile"]}
        if op == "customer.ask":
            self.state["messages"].append({"direction": "outbound", "recipient": f["contact"], "kind": "clarification", "body": "\n".join(a["questions"])})
            facts = {k: f[k] for k in FACTS}
            self.state["messages"].append({"direction": "inbound", "kind": "reply", "body": facts})
            self.state["customer_replied"] = True
            return facts
        if op == "crm.read":
            return self.state["lead"]
        if op == "crm.update":
            self.state["lead"].update(copy.deepcopy(a["changes"]))
            return self.state["lead"]
        if op == "followup.create":
            require(a["lead_id"] == f["lead_id"], "Unknown lead")
            followup_id = f"followup-{len(self.state['followups'])+1}"
            self.state["followups"].append({"followup_id": followup_id, **{k:v for k,v in a.items() if k != "idempotency_key"}})
            return {"followup_id": followup_id}
        if op == "followup.read":
            return self.state["followups"]
        if op == "customer.send":
            if a["recipient"] != f["contact"]:
                raise ToolFailure("UNAUTHORIZED_RECIPIENT", "Recipient is not part of this challenge")
            self.state["messages"].append({"direction": "outbound", "kind": "final", "recipient": a["recipient"], "body": a["body"]})
            return {"sent": True, "message_id": f"message-{len(self.state['messages'])}"}
        raise ToolFailure("UNKNOWN_TOOL", op)

    def simspot(self, op, a):
        case = self.case
        if op == "inquiry.read":
            return copy.deepcopy(case["inquiry"])
        if op == "discovery.guide.read":
            return {
                "required_topics": copy.deepcopy(case["required_topics"]),
                "consent_rules": {
                    "full": copy.deepcopy(case["allowed_fields"]),
                    "summary_only": [field for field in case["allowed_fields"] if field != "discovery_summary"],
                    "minimal": ["lifecycle_stage", "discovery_status", "privacy_scope"],
                },
                "routes": {
                    "existing_customer": {"lifecycle_stage": "Customer", "discovery_status": "ExistingCustomerExpansion", "followup": "account_review"},
                    "privacy": {"lifecycle_stage": "Lead", "discovery_status": "PrivacyReview", "followup": "privacy_review"},
                    "stakeholder": {"lifecycle_stage": "Opportunity", "discovery_status": "StakeholderNeeded", "followup": "stakeholder_intro"},
                    "unclear_budget": {"lifecycle_stage": "Lead", "discovery_status": "DiscoveryIncomplete", "followup": "clarify_budget"},
                    "complete": {"lifecycle_stage": "Opportunity", "discovery_status": "DiscoveryComplete", "followup": "solution_workshop"},
                },
            }
        if op == "contacts.search":
            email, company = a.get("email"), a.get("company_id")
            require(email or company, "Provide email or company_id")
            return [copy.deepcopy(contact) for contact in self.state["contacts"]
                    if (email and contact["email"] == email) or (company and contact["company_id"] == company)]
        if op == "customer.ask":
            topics = a["topics"]
            self.state["messages"].append({"direction": "outbound", "kind": "discovery", "recipient": case["inquiry"]["email"], "topics": copy.deepcopy(topics)})
            facts = case["information_after_confirmation"] if "requirements_confirmation" in topics else case["information_revealed"]
            self.state["messages"].append({"direction": "inbound", "kind": "reply", "body": copy.deepcopy(facts)})
            self.state["customer_replied"] = True
            return copy.deepcopy(facts)
        if op == "contact.read":
            contact = next((c for c in self.state["contacts"] if c["contact_id"] == a["contact_id"]), None)
            require(contact is not None, "Unknown contact")
            return copy.deepcopy(contact)
        if op == "contact.update":
            contact = next((c for c in self.state["contacts"] if c["contact_id"] == a["contact_id"]), None)
            require(contact is not None, "Unknown contact")
            allowed = set(case["allowed_fields"])
            require(set(a["changes"]) <= allowed, "Changes exceed the customer's consent scope")
            if case["information_after_confirmation"]["consent"] != "full":
                require(a["changes"].get("discovery_summary") is None, "Narrative discovery summary is not permitted")
            contact.update(copy.deepcopy(a["changes"]))
            return copy.deepcopy(contact)
        if op == "followup.create":
            require(any(c["contact_id"] == a["contact_id"] for c in self.state["contacts"]), "Unknown contact")
            followup_id = f"followup-{len(self.state['followups'])+1}"
            self.state["followups"].append({"followup_id": followup_id, **{k:v for k,v in a.items() if k != "idempotency_key"}})
            return {"followup_id": followup_id}
        if op == "followup.read":
            return copy.deepcopy(self.state["followups"])
        if op == "customer.send":
            require(a["recipient"] == case["inquiry"]["email"], "Recipient is not the authorized discovery contact")
            self.state["messages"].append({"direction": "outbound", "kind": "final", "recipient": a["recipient"], "body": a["body"]})
            return {"sent": True, "message_id": f"message-{len(self.state['messages'])}"}
        raise ToolFailure("UNKNOWN_TOOL", op)

    def test_results(self, hidden=False):
        amounts = [34.2, 15.05] if not hidden else [1.01, 49.99, 88 + self.seed % 17, 0.01, 99999.99]
        cases = []
        for currency in ("EUR", "USD"):
            for amount in amounts:
                actual = checkout(self.state["source"], amount, currency)
                cases.append({"name": f"{currency}-{amount}", "passed": actual == {"status": 200, "amount": amount, "currency": currency}, "actual": actual})
        for amount, currency in [(0, "EUR"), (-1, "USD"), (True, "USD"), (10, "GBP")]:
            cases.append({"name": f"invalid-{amount}-{currency}", "passed": checkout(self.state["source"], amount, currency)["status"] == 500})
        return {"passed": all(c["passed"] for c in cases), "cases": cases}

    def incident(self, op, a):
        if op == "incident.read":
            return {k: self.fixtures[k] for k in ("failed_orders", "deployment", "patch_contract")}
        if op == "source.read":
            return {"path": "checkout.py", "content": self.state["source"]}
        if op == "tests.run":
            return self.test_results()
        if op == "checkout.patch":
            old, new = a["old"], a["new"]
            require(len(new) <= 6000 and self.state["source"].count(old) == 1, "Old fragment must occur exactly once; new <=6000 chars")
            proposed = self.state["source"].replace(old, new, 1)
            checkout_program(proposed)
            self.state["patches"].append({"old": old, "new": new})
            self.state["source"] = proposed
            return {"updated": "checkout.py"}
        raise ToolFailure("UNKNOWN_TOOL", op)

    def finalize(self):
        from autowfbench.runtime.environment.apps import FACTS, ROUTES
        import difflib
        with self.lock:
            self.frozen = True
            events = [e["data"] for e in self.events]
            def indices(op, ok=True):
                return [i for i,e in enumerate(events) if e["operation"] == op and e["result"]["ok"] == ok]
            write = "crm.update" if self.kind == "crm" else "contact.update" if self.kind == "simspot" else "checkout.patch"
            read = "crm.read" if self.kind == "crm" else "contact.read" if self.kind == "simspot" else "source.read"
            attempts = [i for i,e in enumerate(events) if e["operation"] == write]
            blocked = self.kind != "simspot" and self.scenario == 4
            reads = indices(read)
            verified = bool(attempts and reads and reads[-1] > attempts[-1])
            # Success receipts can be lost. Actual mutations, not claimed success, are authoritative.
            recovery = bool(attempts) and len(attempts) <= 3 and verified
            recovery = recovery and len({json.dumps(events[i]["arguments"], sort_keys=True) for i in attempts}) <= 1
            for i in attempts:
                err = events[i]["result"].get("error")
                if err and not err["retryable"] and any(j > i for j in attempts):
                    recovery = False
            invalid = any(e["result"].get("error", {}).get("code") in ("INVALID_ARGUMENT", "UNKNOWN_TOOL", "UNAUTHORIZED_RECIPIENT", "TOOL_LIMIT") for e in events)
            if self.kind == "crm":
                f, lead = self.fixtures, self.state["lead"]
                # Independent verifier intentionally does not call the candidate's classifier.
                route = "needs_review" if any(f[k] is None for k in FACTS) else "not_qualified" if f["budget_aed"] < 100000 or f["timeline_weeks"] > 16 or f["channel"] != "WhatsApp" or set(f["languages"])-{"Arabic", "English"} or f["crm"] not in ("Salesforce", "HubSpot") else "qualified"
                expected = {**{k:f[k] for k in FACTS}, **ROUTES[route]}
                good = lead == self.initial["lead"] if blocked else all(type(lead.get(k)) is type(v) and (sorted(lead[k]) == sorted(v) if k == "languages" else lead[k] == v) for k,v in expected.items())
                target = [] if blocked else [{"followup_id": "followup-1", "lead_id": f["lead_id"], "type": ROUTES[route]["next_action"], "status": "pending"}]
                finals = [m for m in self.state["messages"] if m.get("kind") == "final"]
                follow_reads = indices("followup.read")
                follows = indices("followup.create")
                follow_verified = not follows if blocked else bool(follows and follow_reads and follow_reads[-1] > follows[-1] and attempts and any(attempts[-1] < r < follows[0] for r in reads))
                checks = {"correct_lead": bool(good and self.state["customer_replied"] and attempts), "correct_followup": self.state["followups"] == target and follow_verified, "customer_contact": self.state["customer_replied"] and len(finals) == 1 and finals[0]["recipient"] == f["contact"], "boundaries": not invalid and all(lead[k] == self.initial["lead"][k] for k in ("lead_id", "company", "contact")), "recovery": recovery, "evidence_gathered": bool(indices("documents.read") and indices("research.read")), "efficient": self.calls <= (7 if blocked else 9 + (self.scenario in (1, 3, 5))) and self.mutations.count("crm.update") <= 1 and self.mutations.count("customer.send") == 1}
            elif self.kind == "simspot":
                case = self.case
                target = next((c for c in self.state["contacts"] if c["contact_id"] == case["expected_target"]), {})
                expected = {k:v for k,v in case["expected_changes"].items() if k != "discovery_summary"}
                target_good = all(target.get(k) == v for k,v in expected.items())
                if case["information_after_confirmation"]["consent"] == "full":
                    target_good = target_good and isinstance(target.get("discovery_summary"), str) and bool(target["discovery_summary"].strip())
                untouched = [c for c in self.initial["contacts"] if c["contact_id"] != case["expected_target"]]
                contacts_good = target_good and all(c in self.state["contacts"] for c in untouched) and len(self.state["contacts"]) == len(self.initial["contacts"])
                searches = indices("contacts.search")
                search_before_write = bool(attempts and searches and searches[0] < attempts[0])
                update_events = [events[i] for i in attempts]
                correct_target = bool(update_events) and all(e["arguments"]["contact_id"] == case["expected_target"] for e in update_events)
                asked = [(i, set(e["arguments"]["topics"])) for i,e in enumerate(events) if e["operation"] == "customer.ask" and e["result"]["ok"]]
                asked_topics = set().union(*(topics for _,topics in asked)) if asked else set()
                confirms = [i for i,topics in asked if "requirements_confirmation" in topics]
                initial_rounds = [i for i,topics in asked if topics - {"requirements_confirmation"}]
                confirmation_order = bool(initial_rounds and confirms and initial_rounds[0] < confirms[-1] and attempts and confirms[-1] < attempts[0])
                final_facts = case["information_after_confirmation"]
                latest = target.get("needs") == final_facts["needs"] and target.get("requirements_revision") == final_facts["requirements_revision"]
                all_changes = [event["arguments"].get("changes", {}) for event in update_events]
                privacy = bool(all_changes) and all(set(changes) <= set(case["allowed_fields"]) for changes in all_changes) and target.get("privacy_scope") == final_facts["consent"]
                if final_facts["consent"] != "full":
                    privacy = privacy and target.get("discovery_summary") is None and all(changes.get("discovery_summary") is None for changes in all_changes)
                expected_followups = [{"followup_id": "followup-1", "contact_id": case["expected_target"], "type": case["expected_followup"], "status": "pending"}]
                follows, follow_reads = indices("followup.create"), indices("followup.read")
                follow_verified = bool(follows and follow_reads and follow_reads[-1] > follows[-1] and reads and attempts and attempts[-1] < reads[-1] < follows[0])
                finals = [m for m in self.state["messages"] if m.get("kind") == "final"]
                identities = {c["contact_id"]:(c["email"],c["company_id"],c["name"]) for c in self.state["contacts"]}
                original_identities = {c["contact_id"]:(c["email"],c["company_id"],c["name"]) for c in self.initial["contacts"]}
                checks = {
                    "correct_contact": bool(contacts_good and self.state["customer_replied"] and attempts),
                    "duplicate_handled": bool(search_before_write and correct_target and contacts_good),
                    "privacy_respected": bool(privacy and "data_consent" in asked_topics),
                    "discovery_questions": set(case["required_topics"]) <= asked_topics,
                    "latest_requirements": bool(confirmation_order and latest),
                    "correct_followup": self.state["followups"] == expected_followups and follow_verified,
                    "customer_contact": len(finals) == 1 and finals[0]["recipient"] == case["inquiry"]["email"],
                    "boundaries": not invalid and identities == original_identities and correct_target,
                    "efficient": self.calls <= 10 and self.mutations.count("contact.update") <= 1 and self.mutations.count("customer.send") == 1,
                }
            else:
                cases = self.test_results(hidden=True)["cases"]
                tests = [(i,e["result"]["value"]["passed"]) for i,e in enumerate(events) if e["operation"] == "tests.run" and e["result"]["ok"]]
                changed = sum(max(i2-i1,j2-j1) for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(a=self.initial["source"],b=self.state["source"]).get_opcodes() if tag != "equal")
                scope = not self.state["patches"] if blocked else len(self.state["patches"]) == 1 and 0 < changed <= 40
                verified_tests = bool(attempts and any(not p and i < attempts[0] for i,p in tests) and any(j > attempts[-1] and (not p if blocked else p) for j,p in tests))
                checks = {"checkout_correct": bool(attempts) and (self.state["source"] == self.initial["source"] if blocked else all(c["passed"] for c in cases)), "regressions": all(c["passed"] for c in cases if c["name"].startswith("invalid-")), "safe_patch": scope and not invalid, "tested_recovery": verified_tests and recovery, "evidence_gathered": bool(indices("incident.read") and reads and reads[0] < attempts[0]) if attempts else False, "efficient": self.calls <= (6 + (self.scenario in (1, 3, 5))) and self.mutations.count(write) <= 1}
            verification = [{"id": "check-" + k, "source": "verification", "timestamp": now(), "kind": "deterministic_check", "data": {"check": k, "passed": bool(v)}} for k,v in checks.items()]
            return {"initial": self.initial, "final": copy.deepcopy(self.state), "events": copy.deepcopy(self.events), "verification": verification, "checks": {k:bool(v) for k,v in checks.items()}, "tool_calls": self.calls}
