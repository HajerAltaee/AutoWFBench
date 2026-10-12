"""Public input contracts for the experimental UI, independent of storage/HTTP."""
from datetime import date, time
import re


class InvalidInput(ValueError):
    pass


def fields(payload, allowed, required=()):
    if not isinstance(payload, dict) or set(payload) - set(allowed):
        raise InvalidInput("Unexpected fields")
    if set(required) - set(payload):
        raise InvalidInput("Missing required fields")


def text(value, label, limit=200, required=True):
    if not isinstance(value, str) or len(value) > limit:
        raise InvalidInput(f"{label} must be text of at most {limit} characters")
    value = value.strip()
    if required and not value:
        raise InvalidInput(f"{label} is required")
    return value


def contact_changes(payload):
    fields(payload, ("first_name", "last_name", "job_title", "email", "lifecycle_stage"))
    if not payload:
        raise InvalidInput("Provide at least one change")
    result = {key: text(value, key, required=key != "job_title") for key, value in payload.items()}
    if "email" in result:
        validate_email(result["email"])
    if "lifecycle_stage" in result and result["lifecycle_stage"] not in ("Lead", "Opportunity", "Customer"):
        raise InvalidInput("Unsupported lifecycle stage")
    return result


def validate_email(email):
    # Deliberately a small local validation contract, not HubSpot's complete validator.
    if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[A-Za-z]{2,}", email) or email.lower().endswith(".example"):
        raise InvalidInput("Enter a valid email address")


def new_contact(payload):
    fields(payload, ("email", "first_name", "last_name"), ("email", "first_name", "last_name"))
    record = {key: text(payload[key], key) for key in ("email", "first_name", "last_name")}
    validate_email(record["email"])
    return record


def activity(payload, kind):
    if kind == "note":
        fields(payload, ("body", "include_company"), ("body",))
        include_company = payload.get("include_company", True)
        if not isinstance(include_company, bool):
            raise InvalidInput("include_company must be a boolean")
        return {"body": text(payload["body"], "Note", 10000), "include_company": include_company}
    fields(payload, ("title", "body", "due_date", "due_time", "task_type", "priority", "include_company"), ("title", "due_date"))
    if not isinstance(payload.get("include_company", True), bool):
        raise InvalidInput("include_company must be a boolean")
    result = {
        "title": text(payload["title"], "Task title", 300),
        "body": text(payload.get("body", ""), "Task description", 10000, False),
        "due_date": text(payload["due_date"], "Activity date", 10),
        "due_time": text(payload.get("due_time", "08:00"), "Time", 5),
        "task_type": payload.get("task_type", "To-do"),
        "priority": payload.get("priority", "None"),
        "status": "Not started", "assigned_to": "Demo Operator",
        "include_company": payload.get("include_company", True),
    }
    try:
        if date.fromisoformat(result["due_date"]).isoformat() != result["due_date"]:
            raise ValueError()
        if not re.fullmatch(r"\d{2}:\d{2}", result["due_time"]):
            raise ValueError()
        time.fromisoformat(result["due_time"])
    except ValueError as exc:
        raise InvalidInput("Use a valid activity date and HH:MM time") from exc
    if result["task_type"] not in ("To-do", "Call", "Email") or result["priority"] not in ("None", "Low", "Medium", "High"):
        raise InvalidInput("Unsupported task type or priority")
    return result
