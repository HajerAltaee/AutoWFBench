from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("AUTOWFBENCH_ROOT", Path(__file__).resolve().parents[1]))
MAX_BODY = 2_000_000


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text())


def save_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
        json.dump(value, f, indent=2, allow_nan=False)
        temp = f.name
    os.replace(temp, path)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http_json(url: str, payload=None, token=None, timeout=15, method=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.build_opener(NoRedirect).open(request, timeout=max(.01, timeout)) as response:
        raw = response.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            raise ValueError("Response exceeds size limit")
        return json.loads(raw)


class HTTPError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class JsonHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > MAX_BODY:
            raise HTTPError(413, "Request exceeds size limit")
        data = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(data, dict):
            raise HTTPError(400, "Expected a JSON object")
        return data

    def auth(self, token):
        actual = self.headers.get("Authorization", "")
        if not secrets.compare_digest(actual, "Bearer " + token):
            raise HTTPError(401, "Unauthorized")

    def send(self, status, value):
        self.send_bytes(status, json.dumps(value, allow_nan=False).encode(), "application/json")

    def send_bytes(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def dispatch(self, method):
        try:
            self.route(method)
        except HTTPError as exc:
            self.send(exc.status, {"error": exc.message})
        except (ValueError, KeyError, TypeError) as exc:
            self.send(400, {"error": str(exc)})
        except Exception as exc:
            self.send(500, {"error": type(exc).__name__ + ": " + str(exc)})

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")


def background_server(handler, host="127.0.0.1", port=0):
    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
