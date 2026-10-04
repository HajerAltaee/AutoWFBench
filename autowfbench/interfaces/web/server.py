from __future__ import annotations

import mimetypes
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from autowfbench.core.common import HTTPError, JsonHandler, read_json
from autowfbench.core.contracts import public_challenges


def handler_for(engine, control_token):
    class Handler(JsonHandler):
        def route(self, method):
            path = self.path.split("?", 1)[0]
            if method == "GET":
                if path == "/api/challenges":
                    return self.send(200, public_challenges())
                if path == "/api/runs":
                    return self.send(200, engine.list_runs())
                if path.startswith("/api/runs/"):
                    parts = path.strip("/").split("/")
                    if len(parts) == 3:
                        return self.send(200, engine.read(parts[2]))
                    if len(parts) == 4 and parts[3] in ("log", "scorecard", "package"):
                        filename = {"log": "run-log.json", "scorecard": "scorecard-result.json", "package": "package.json"}[parts[3]]
                        file = engine.directory(parts[2]) / filename
                        if not file.exists():
                            raise HTTPError(404, "Artifact not yet available")
                        return self.send(200, read_json(file))
                assets = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
                if path in assets:
                    file = Path(__file__).parent / assets[path]
                    return self.send_bytes(200, file.read_bytes(), mimetypes.guess_type(str(file))[0] or "text/plain")
            if method == "POST":
                self.auth(control_token)
                if path == "/api/runs":
                    data = self.body()
                    run_id = engine.submit(data["challenge_id"], data["solution"], data.get("seed", 0))
                    return self.send(202, {"run_id": run_id})
                parts = path.strip("/").split("/")
                if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "rescore":
                    run_id = parts[2]
                    if engine.read(run_id)["status"] in ("queued", "running", "judging"):
                        raise HTTPError(409, "Run is busy")
                    def rescore():
                        try:
                            engine.rescore(run_id)
                        except Exception as exc:
                            engine.update(run_id, status="judge_failed", judge_error=str(exc), score_0_10=None)
                    threading.Thread(target=rescore, daemon=True).start()
                    return self.send(202, {"run_id": run_id})
            raise HTTPError(404, "Not found")
    return Handler


def serve(engine, host, port, token):
    print(f"Dashboard: http://{host}:{port}\nControl token (for submissions/rescoring): {token}", flush=True)
    ThreadingHTTPServer((host, port), handler_for(engine, token)).serve_forever()
