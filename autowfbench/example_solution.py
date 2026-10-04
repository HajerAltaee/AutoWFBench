"""Scripted HTTP adapters demonstrating the submission protocol, not AI results."""
from __future__ import annotations

import threading
import uuid
from http.server import ThreadingHTTPServer

from .common import HTTPError, JsonHandler, http_json, now


def solve(request, variant="reference", cancelled=None):
    trace = []
    env = request["environment"]
    def tool(operation, **arguments):
        if cancelled and cancelled.is_set():
            raise RuntimeError("Cancelled")
        result = http_json(env["base_url"] + "/tools", {"operation": operation, "arguments": arguments}, env["access_token"])
        trace.append({"timestamp": now(), "kind": "tool_observation", "data": {"operation": operation, "ok": result["ok"]}})
        return result
    artifacts = []
    if request["challenge"]["id"] == "crm-lead-qualification":
        inquiry = tool("inquiry.read")["value"]
        tool("documents.read"); tool("research.read")
        facts = tool("customer.ask", questions=["What budget, timeline, monthly message volume, languages, CRM, and handoff requirements should we plan for?"])["value"]
        changes = {**facts, "status": "Qualified", "next_action": "discovery_call", "owner": "sales_coordinator"}
        update = tool("crm.update", changes=changes)
        if variant != "incomplete":
            if not update["ok"] and update["error"]["retryable"]:
                tool("crm.update", changes=changes)
            tool("followup.create", lead_id=inquiry["lead_id"], type="discovery_call", status="pending_scheduling")
            tool("customer.send", recipient=inquiry["contact"], body="Your WhatsApp use case, Arabic and English support, and human escalation needs align with our services. Salesforce integration requires assessment. Please share availability for a discovery call to confirm scope, pricing, and timeline before commitments.")
            lead = tool("crm.read")["value"]
            answer = f"The customer confirmed budget AED {facts['budget_aed']}, {facts['volume']} monthly messages, and a {facts['timeline_weeks']}-week target. Consulted service and qualification policy and company research. Retried the temporary CRM failure; final readback confirms {lead['status']}. Created one discovery follow-up pending scheduling and sent a response without guaranteeing scope, pricing, or delivery. Scheduling remains open."
        else:
            answer = "Customer requirements gathered. The CRM update failed; qualification and follow-up are incomplete."
    else:
        incident = tool("incident.read")["value"]
        source = tool("source.read")["value"]["content"]
        before = tool("tests.run")["value"]
        if variant != "incomplete":
            tool("checkout.patch", old="charge_card(currency, amount)", new="charge_card(amount, currency)")
            after = tool("tests.run")["value"]
            answer = f"The EUR branch passed currency before amount to charge_card, matching the deployment change and failed EUR order. Reversed those arguments only. Tests failed before the patch ({before['passed']}) and passed afterward ({after['passed']}); USD behavior and invalid-payment rejection remain intact. This is a simulated checkout repair, not a production deployment."
        else:
            answer = "EUR checkout fails because charge_card receives swapped arguments. The source has not been changed; the incident remains unresolved."
        artifacts = [{"name": "incident-summary.md", "media_type": "text/markdown", "content": "# Incident summary\n\n" + answer}]
    return {"protocol_version": "1.0", "run_id": request["run_id"], "status": "completed", "final_answer": answer, "artifacts": artifacts, "trace": trace}


def handler_for(variant="reference"):
    jobs, lock = {}, threading.RLock()
    class Handler(JsonHandler):
        def route(self, method):
            if method == "POST" and self.path == "/runs":
                request = self.body()
                execution_id = uuid.uuid4().hex
                cancel = threading.Event()
                with lock:
                    jobs[execution_id] = {"status": "running", "cancel": cancel}
                def work():
                    try:
                        result = solve(request, variant, cancel)
                    except Exception as exc:
                        result = {"protocol_version": "1.0", "run_id": request["run_id"], "status": "failed", "final_answer": str(exc), "artifacts": [], "trace": []}
                    with lock:
                        jobs[execution_id].update(status=result["status"], submission=result)
                threading.Thread(target=work, daemon=True).start()
                return self.send(202, {"execution_id": execution_id, "status": "running"})
            parts = self.path.strip("/").split("/")
            if len(parts) in (2,3) and parts[0] == "runs":
                with lock:
                    job = jobs.get(parts[1])
                    if not job:
                        raise HTTPError(404, "Unknown execution")
                    if method == "POST" and len(parts) == 3 and parts[2] == "cancel":
                        job["cancel"].set()
                        return self.send(200, {"accepted": True})
                    if method == "GET" and len(parts) == 2:
                        return self.send(200, {k:v for k,v in job.items() if k != "cancel"})
            raise HTTPError(404, "Not found")
    return Handler


def serve(host, port, variant):
    print(f"Scripted reference solution ({variant}): http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), handler_for(variant)).serve_forever()
