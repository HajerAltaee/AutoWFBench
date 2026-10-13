# Local mock lead import and follow-up plan

N8nComposer authored sapiens-mock-leads-flow.json for Admin's local, unscored exercise. The parent operator supplies the ten rows from mock-leads.json in Context and runs the flow against the existing isolated SimSpot server. The flow uses supplied now for all 48-hour decisions.

For each lead, it searches CRM by email and requires one exact case-insensitive match or creates a contact. It preserves existing identity, lifecycle stage and company association, updates only a changed job title, and verifies the contact read-back. It compares a stable source/company/discovery note with existing contact activities, bootstraps each supplied inbound message with a stable source ID, then reads /messages to identify the latest inbound customer message. A message is overdue only when its timestamp is strictly more than 48 hours before now. The flow skips recent, exactly 48-hour and no-message contacts. For overdue contacts it creates a personalized To-do using the latest message and CRM context, unless a task with the message-derived idempotency key already exists. It verifies the task in CRM and emits one per-lead submission. No emails are sent.

The intended cadence after local verification is every 24 hours. No live schedule or Scheduled Routine is created in this authoring step. The parent operator owns live execution, repeat-run verification against persistent CRM state, and any later scheduling decision. The server's contact, note, message and task APIs are local development contracts; no scored benchmark integration is claimed.

Parent review: Submit emits one overall submission containing ten per-lead outcomes.
The parent bounded the dynamic HTTP method and changed sendBody to a literal
boolean after an n8n import failure. See README.md and mock-verification.json for
execution evidence and its limits; the original authoring plan is not itself proof
of live success.
