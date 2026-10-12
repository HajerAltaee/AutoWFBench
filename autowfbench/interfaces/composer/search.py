"""Generate native workflows using public contracts; repair on development runs only."""
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from autowfbench.interfaces.composer.n8n import N8nRuntime
from autowfbench.interfaces.composer.graph import SCHEMA, compile_graph
from autowfbench.core.common import ROOT, background_server, digest, http_json, read_json, save_json
from autowfbench.core.contracts import load_challenge
from autowfbench.interfaces.solution import handler_for as solution_handler
from autowfbench.runtime.engine import Engine, EnvironmentProcess
from autowfbench.runtime.judge import Judge, handler_for as judge_handler

MODEL = "gpt-6.1-sol"
PROMPT = """Compose the smallest reliable native n8n workflow for this task and the public simApp APIs.
Return a typed graph {name,nodes}; the harness compiles only n8n boilerplate, never business logic.
Do not call tools or inspect files. The supplied development preview is read-only example data;
your workflow MUST re-read current data at execution. Never hard-code customer facts, source
code, IDs, amounts or outcomes. Use documented field names directly; no fuzzy schema parsers.
Every business action is an HTTP node. Code nodes only transform data, decide and report.

Each node has name, kind (http/code/if), operation, code, expression, next, on_false.
Unused string fields are empty strings and unused edge lists are []. All fields are required.
The compiler supplies Start -> Context -> your first node. Context contains
{run_id,challenge,environment:{base_url,access_token},limits}. Do not define Start or Context.
Connections use node names: next is the single successor (true branch for If), on_false
is the false successor for If only. Multiple paths can converge directly into a node.
Every handled path must reach a terminal Code node named Submit, with next:[],on_false:[].

HTTP: operation is one documented operation. expression is an n8n object expression,
e.g. ={{ {} }} for no arguments, or ={{ {changes:$('Assess').first().json.changes,
idempotency_key:$('Context').first().json.run_id+':update'} }}. Headers and URL are supplied
by the compiler. A response replaces the current item and has {ok:true,value} or
{ok:false,error:{code,message,retryable}}; value can itself be an array.
Code: code is JavaScript returning [{json: object}]. Access current data with
$input.first().json and prior outputs with $('Node Name').first().json. Check
$('Node Name').isExecuted before referencing a node on a branch that may not run.
If: expression must evaluate to a boolean, e.g. ={{ $json.ok === true }}.
No shell, filesystem, imports, require, $env, external services, static state or credentials.

Inspect every action result. Retry only retryable errors, at most three total attempts,
using the SAME idempotency key and arguments. Ambiguous writes may already have committed.
Read back and compare state before dependent actions or success claims. Permanent failures:
stop dependent writes, verify unchanged state, report the block honestly and perform any
independent communication the task requires. When verification tests are available, run them before the write attempt and again after
the attempt sequence, including a blocked sequence. Explain
business next steps in plain language, never internal status codes alone. No invented success.
Optimize calls and transformation code. Use the actual public policy and observed test/source
results for decisions; do not add speculative compatibility rules. Output the full graph.

PUBLIC_INPUT:
"""


def public_input(challenge_id):
    # Acquire public docs and read-only development observations; never grader internals.
    process = EnvironmentProcess(challenge_id, 0)
    try:
        apps = http_json(process.public_url + "/apps", token=process.run_token)
        preview = [{"operation":op["operation"], "result":http_json(process.public_url+op["path"], {}, process.run_token)} for op in apps["operations"] if op["operation"].endswith(".read") and not op["arguments"].get("required")]
    finally:
        process.close()
    return {"challenge": load_challenge(challenge_id)["definition"], "apps": apps, "development_preview":preview, "submission_schema": read_json(ROOT / "benchmark/schemas/submission.schema.json")}


def _sapiens_generate(directory, prompt):
    """Submit once through Chief; observing again resumes the same accepted turn."""
    script = Path(os.environ.get("SAPIENS_CLI", "")).resolve()
    if not script.is_file():
        raise ValueError("Set SAPIENS_CLI to the Sapiens checkout's sapiens4 Python entrypoint")
    url = os.environ.get("SAPIENS4_URL", "http://127.0.0.1:4174")
    timeout = int(os.environ.get("SAPIENS_COMPOSER_TIMEOUT", "1800"))
    if timeout <= 0:
        raise ValueError("SAPIENS_COMPOSER_TIMEOUT must be positive")
    command = [sys.executable, str(script), "--url", url, "--format", "json"]
    env = {k:v for k,v in os.environ.items() if not k.startswith(("AWB_", "AUTOWFBENCH_"))}
    env["PYTHONUTF8"] = "1"
    receipt_path = directory / "sapiens-request.json"
    identity = {"prompt_digest":digest(prompt), "cli":str(script), "url":url}

    def invoke(args, label, seconds):
        with (directory / (label + "-stderr.log")).open("w", encoding="utf-8") as err:
            result = subprocess.run(command + args, cwd=script.parent, env=env,
                                    stdout=subprocess.PIPE, stderr=err, text=True,
                                    encoding="utf-8", timeout=seconds)
        try:
            envelope = json.loads(result.stdout)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("Sapiens returned invalid JSON; inspect the host before resubmitting") from exc
        save_json(directory / (label + ".json"), envelope)
        if not isinstance(envelope, dict) or envelope.get("schema_version") != 1:
            raise RuntimeError("Unsupported Sapiens CLI envelope")
        if result.returncode or envelope.get("ok") is not True:
            raise RuntimeError("Sapiens did not complete successfully; inspect " + str(directory / (label + ".json")))
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("Sapiens CLI returned no structured result")
        return data

    if receipt_path.exists():
        receipt = read_json(receipt_path)
        if receipt.get("identity") != identity:
            raise ValueError("Sapiens host, CLI or prompt changed; use a fresh output directory")
    else:
        receipt = {"identity":identity, "state":"submitting"}
        # Exclusive creation also prevents concurrent callers from submitting twice.
        with receipt_path.open("x", encoding="utf-8") as handle:
            json.dump(receipt, handle)
        request = (
            "Chief: coordinate the existing N8nComposer specialist (create one only if needed). "
            "This is workflow authoring only, not execution or benchmarking. "
            f"Read the public authoring request at {directory / 'prompt.txt'} and JSON schema at {directory / 'schema.json'}. "
            f"Write ONLY the schema-conforming typed graph JSON to {directory / 'response.json'}. "
            "Do not write raw native n8n JSON. Do not inspect repository sources, credentials, "
            "benchmark internals or other runs. Do not edit other files, run tests or execute workflows. "
            "The specialist may read these two files and write that one output; unrelated workspace "
            "changes are not part of this task. Report completion only after the file is saved."
        )
        try:
            accepted = invoke(["chat", request, "--sapi", "chief"], "sapiens-submit", 60)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Sapiens submission outcome unknown; inspect Chief history. Do not resubmit automatically") from exc
        if any(not isinstance(accepted.get(key), str) or not accepted[key] for key in ("id", "agent")):
            raise RuntimeError("Sapiens receipt has no turn/agent ID; inspect Chief history before resubmitting")
        receipt.update(state="accepted", id=accepted["id"], agent=accepted["agent"])
        save_json(receipt_path, receipt)
    if receipt["state"] == "submitting":
        raise RuntimeError("Previous Sapiens submission outcome is unknown; inspect Chief history, do not resubmit")
    if receipt["state"] != "completed":
        try:
            observed = invoke(["conversation", "watch", receipt["id"], "--sapi", receipt["agent"]], "sapiens-watch", timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Sapiens observation timed out; host work may continue. Re-run in this directory to observe turn " + receipt["id"]) from exc
        if observed.get("id") != receipt["id"] or observed.get("state") != "Completed":
            raise RuntimeError("Sapiens has not confirmed completion of the accepted turn; inspect sapiens-watch.json")
        receipt["state"] = "completed"
        save_json(receipt_path, receipt)
    if not (directory / "response.json").is_file():
        raise RuntimeError("Sapiens completed without saving response.json")
    save_json(directory / "provenance.json", {"provider":"sapiens", "model":"host-configured",
              "prompt_digest":digest(prompt), "turn_id":receipt["id"], "agent":receipt["agent"]})


def generate(public, directory, previous=None, feedback=None, *, provider=None):
    provider = provider or os.environ.get("AWB_COMPOSER_PROVIDER", "codex")
    if provider not in ("codex", "sapiens"):
        raise ValueError("AWB_COMPOSER_PROVIDER must be codex or sapiens")
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    prompt = PROMPT + json.dumps(public)
    if provider == "sapiens":
        prompt = prompt.replace("Do not call tools or inspect files.",
                                "Author using only this request and the supplied graph schema; do not inspect other files.")
    if previous is not None or feedback:
        prompt += "\nRepair using these development observations. Return the full typed graph, not raw n8n JSON.\n" + json.dumps({"previous_native_workflow":previous,"feedback":feedback})
    prompt_path = directory / "prompt.txt"
    if prompt_path.exists() and prompt_path.read_text(encoding="utf-8") != prompt:
        raise ValueError("Existing generation used a different prompt/provider; use a fresh output directory")
    if provider == "codex" and (directory / "sapiens-request.json").exists():
        raise ValueError("Existing Sapiens generation; use a fresh output directory")
    if provider == "codex" and (directory / "response.json").exists():
        if not prompt_path.exists():
            raise ValueError("Existing response has no authoring prompt; use a fresh output directory")
        workflow = compile_graph(read_json(directory / "response.json"), public["apps"])
        save_json(directory / "workflow.json", workflow)
        return workflow
    if provider == "sapiens" and (directory / "response.json").exists() and not (directory / "sapiens-request.json").exists():
        raise ValueError("Existing response has no Sapiens receipt; use a fresh output directory")
    prompt_path.write_text(prompt, encoding="utf-8")
    schema = SCHEMA
    save_json(directory / "schema.json", schema)
    if provider == "sapiens":
        _sapiens_generate(directory, prompt)
        workflow = compile_graph(json.loads((directory / "response.json").read_text(encoding="utf-8")), public["apps"])
        save_json(directory / "workflow.json", workflow)
        return workflow
    binary = os.environ.get("CODEX_BIN") or shutil.which("codex")
    if not binary:
        raise ValueError("Set CODEX_BIN to the authenticated Codex CLI")
    command = [binary, "exec", "--ignore-user-config", "--model", MODEL, "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral", "-c", 'model_reasoning_effort="medium"', "-c", "features.shell_tool=false", "-c", "features.unified_exec=false", "-c", "features.multi_agent=false", "-c", "web_search=\"disabled\"", "--output-schema", str((directory / "schema.json").resolve()), "--json", "-o", str((directory / "response.json").resolve()), "-"]
    env = {k:v for k,v in os.environ.items() if not k.startswith(("AWB_", "AUTOWFBENCH_"))}
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="composer-") as cwd, (directory / "events.jsonl").open("w") as out, (directory / "stderr.log").open("w") as err:
        proc = subprocess.run(command, input=prompt, text=True, cwd=cwd, env=env, stdout=out, stderr=err, timeout=600)
    save_json(directory / "provenance.json", {"provider":"codex","model":MODEL,"prompt_digest":digest(prompt),"seconds":round(time.monotonic()-started,3),"returncode":proc.returncode})
    if proc.returncode:
        raise RuntimeError("codex exec failed; see " + str(directory / "stderr.log"))
    workflow = compile_graph(read_json(directory / "response.json"), public["apps"])
    save_json(directory / "workflow.json", workflow)
    return workflow


def evaluate(workflow, challenge_id, seeds, directory, runtime, judge_model=MODEL, repeats=1):
    directory.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    judge = background_server(judge_handler(Judge("codex", judge_model, directory / "judge", timeout=300), token)) if judge_model else None
    def execute(request, cancel):
        return runtime.execute(workflow, request, cancel, directory / "n8n" / request["run_id"])
    solution = background_server(solution_handler(executor=execute))
    manifest = {"id":"autowfbench-composer", "name":"AutoWFBench composer", "version":digest(workflow)[:12], "runtime":"n8n-2.42.3", "description":"Generated from task and public simApps; authoring provider recorded in generation provenance", "auth_env":"", "endpoint":f"http://127.0.0.1:{solution.server_port}"}
    engine = Engine(directory / "runs", f"http://127.0.0.1:{judge.server_port}" if judge else None, token)
    results, feedback = [], []
    def run_case(case):
        seed, repeat = case
        rid = engine.submit(challenge_id, manifest, seed, background=False)
        result = engine.read(rid)
        result["repeat"] = repeat
        log_path = engine.directory(rid) / "run-log.json"
        log = read_json(log_path) if log_path.exists() else {}
        observations = [e["data"] for e in log.get("events",[]) if e["source"] == "environment" or e["kind"] == "execution_error"]
        visible = {"seed":seed,"score":result["score_0_10"],"status":result["status"],"observations":observations,"submission":log.get("submission")}
        print(json.dumps({"challenge":challenge_id,"seed":seed,"repeat":repeat,"status":result["status"],"score":result["score_0_10"],"calls":result.get("tool_calls"),"seconds":result.get("duration_seconds")}), flush=True)
        return result, visible
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            for result, visible in pool.map(run_case, [(seed, repeat) for seed in seeds for repeat in range(repeats)]):
                results.append(result)
                feedback.append(visible)
    finally:
        solution.shutdown(); solution.server_close()
        if judge:
            judge.shutdown(); judge.server_close()
    scores = [r["score_0_10"] for r in results]
    complete = all(s is not None for s in scores) and bool(scores)
    summary = {"challenge":challenge_id,"workflow_digest":digest(workflow),"seeds":list(seeds),"repeats":repeats,"score":min(scores) if complete else None,"mean":round(sum(scores)/len(scores),2) if complete else None,"score_rule":"minimum across all cases and repeats; failures retained; missing judge means unscored", "runs":results}
    save_json(directory / "summary.json", summary)
    return summary, feedback


def compose(challenge_id, directory, attempts=3, target=9):
    directory = directory.resolve()
    public = public_input(challenge_id)
    save_json(directory / "public-input.json", public)
    runtime = N8nRuntime()
    previous, feedback, best, best_score = None, None, None, -1
    for attempt in range(1, attempts+1):
        root = directory / f"attempt-{attempt}"
        print(f"Composing {challenge_id}, attempt {attempt}", flush=True)
        try:
            previous = generate(public, root, previous, feedback)
            summary, feedback = evaluate(previous, challenge_id, [0, 2, 4], root / "development", runtime)
            score = summary["score"]
            if score is not None and score > best_score:
                best, best_score = previous, score
                save_json(directory / "workflow.json", best)
                save_json(directory / "selection.json", {"attempt":attempt,"development_score":score,"workflow_digest":digest(best)})
            if score is not None and score >= target:
                break
        except (ValueError, KeyError) as exc:
            feedback = {"validation_error":str(exc), "raw_candidate":read_json(root / "response.json") if (root / "response.json").exists() else None, "prior_observations":feedback}
            save_json(root / "validation-error.json", feedback)
            if (root / "workflow.json").exists():
                previous = read_json(root / "workflow.json")
    if best is None:
        raise RuntimeError("No scored candidate; all attempts retained in " + str(directory))
    return best
