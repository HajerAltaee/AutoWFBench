"""Loopback-only HTTP transport for the experimental local UI."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .contracts import InvalidInput
from .state import COMPANIES, Store

ASSETS = Path(__file__).parent / "static"


def handler_for(store, public_port=None):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format, *args):
            pass

        def respond(self, status, value, mime="application/json"):
            body = json.dumps(value).encode() if mime == "application/json" else value
            self.send_response(status)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def run_request(self):
            try:
                port = public_port or self.server.server_port
                host = self.headers.get("Host", "")
                if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                    return self.respond(403, {"error": "Loopback Host required"})
                parsed = urlsplit(self.path)
                parts = parsed.path.strip("/").split("/")
                if self.command == "GET":
                    files = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
                    if parsed.path in files:
                        name, mime = files[parsed.path]
                        return self.respond(200, (ASSETS / name).read_bytes(), mime)
                    if parsed.path == "/api/contacts":
                        query = parse_qs(parsed.query)
                        return self.respond(200, store.contacts(query.get("q", [""])[0], query.get("stage", [""])[0]))
                    if parsed.path == "/api/companies":
                        return self.respond(200, COMPANIES)
                    if len(parts) in (3, 4) and parts[:2] == ["api", "contacts"]:
                        if len(parts) == 3:
                            return self.respond(200, store.contact(parts[2]))
                        if parts[3] == "activities":
                            return self.respond(200, store.activities(parts[2]))
                        if parts[3] == "messages":
                            return self.respond(200, store.customer_messages(parts[2]))
                elif self.command in ("PATCH", "POST"):
                    # Browser writes must be same-origin; JSON prevents simple cross-site form posts.
                    if self.headers.get("Origin") != f"http://{host}":
                        return self.respond(403, {"error": "Same-origin Origin required"})
                    if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
                        return self.respond(415, {"error": "Use application/json"})
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 65536:
                        return self.respond(413, {"error": "JSON body must be 1–65536 bytes"})
                    payload = json.loads(self.rfile.read(length))
                    if parts[:2] == ["api", "contacts"]:
                        if len(parts) == 2 and self.command == "POST":
                            return self.respond(201, store.create_contact(payload))
                        if len(parts) == 3 and self.command == "PATCH":
                            return self.respond(200, store.update(parts[2], payload))
                        if len(parts) == 4 and self.command == "POST" and parts[3] in ("notes", "tasks", "messages"):
                            kind = {"notes": "note", "tasks": "task", "messages": "message"}[parts[3]]
                            return self.respond(201, store.create_activity(parts[2], kind, payload))
                return self.respond(404, {"error": "Not found"})
            except KeyError:
                self.respond(404, {"error": "Contact not found"})
            except InvalidInput as exc:
                self.respond(400, {"error": str(exc)})
            except (ValueError, UnicodeError):
                self.respond(400, {"error": "Invalid input"})
            except Exception:
                self.respond(500, {"error": "Local storage operation failed"})

        do_GET = do_POST = do_PATCH = run_request

    return Handler


def make_server(store, port=8765, bind="127.0.0.1", public_port=None):
    if bind not in ("127.0.0.1", "0.0.0.0"):
        raise ValueError("Unsupported bind address")
    return ThreadingHTTPServer((bind, port), handler_for(store, public_port))


def main():
    parser = argparse.ArgumentParser(description="Experimental SimSpot UI; not scored integration or proven HubSpot parity")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--bind", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1")
    parser.add_argument("--store", type=Path, default=Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "AutoWFBench" / "simspot-ui.sqlite3")
    args = parser.parse_args()
    server = make_server(Store(args.store), args.port, args.bind)
    print(f"Experimental SimSpot UI: http://127.0.0.1:{server.server_port}/", flush=True)
    print(f"Persistent fictional data: {args.store.resolve()}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
