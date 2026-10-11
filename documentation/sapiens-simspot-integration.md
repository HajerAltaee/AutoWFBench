# Sapiens and SimSpot integration

## Confirmed boundary

The customer-discovery objective is part of the authored workflow. A customer Sapi
owns a Scheduled Routine whose saved prompt contains that objective and the selected
customer persona. When the Routine runs, Sapiens delivers the objective through its
existing turn-delivery behavior. No separate completed-turn relay, callback or new
public Sapiens API is required.

SimSpot remains the authoritative CRM SimApp. AutoWFBench starts fresh SimSpot state
for each benchmark run and the n8n workflow uses only the documented, authenticated
SimApp operations. Sapiens does not receive the run-scoped SimSpot token and does not
write evaluator state.

## Existing contracts

- Sapiens Routine ownership and scheduling use `routines`, `routine_create`,
  `routine_update`, `routine_pause` and `routine_resume`.
- Each case fixture supplies a repeatable Routine objective describing which customer
  facts may be revealed for the discovery topics asked.
- AutoWFBench exposes `GET /apps` and typed
  `POST /apps/{app}/{operation}` calls using a run-scoped bearer token.
- SimSpot owns contacts, discovery state, follow-ups and customer-message evidence.
- AutoWFBench freezes authoritative events and state before evaluation.

## Repeatable customer behaviour

The five Routine objectives cover:

1. an interested founder whose budget remains unclear;
2. an enterprise contact who is not the decision-maker;
3. an existing customer represented by a duplicate inbound contact;
4. a privacy-conscious customer allowing structured summary fields only; and
5. a high-value customer whose confirmed requirements replace the initial scope.

For deterministic local and scored evaluation, the AutoWFBench customer SimApp
mirrors the facts and topic-gating defined by the same case objective. This keeps
benchmark state reproducible while Sapiens tests validate the real Routine scheduling
and delivery mechanism separately.

## Security and privacy

- Keep Sapiens and SimSpot on local interfaces during development.
- Never place SimSpot bearer tokens, authorization headers or evaluator data in a
  Routine prompt, chat history, artifact or retained log.
- Ask only allowlisted discovery topics from the active challenge package.
- Store only fields permitted by the customer's explicit consent scope.
- Do not treat Sapiens prose as authoritative CRM state; verify SimSpot readback.

## Windows verification

- Sapiens Routine contract suite: 15 tests passed.
- Sapiens Windows suite: 8 tests passed.
- AutoWFBench suite: 45 tests passed.
- Docker n8n completed all five SimSpot cases on Windows with 8/8 deterministic
  points and ten business calls per case; judging was disabled.

No Linux or WSL installation is required on the host. Docker Desktop supplies the
Linux container used for n8n, while Sapiens and AutoWFBench retain their supported
Windows execution paths.
