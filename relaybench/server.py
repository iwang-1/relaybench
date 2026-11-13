import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine import execute, replay
from .model import local_policy

ASSETS = Path(__file__).with_name("static")
FILES = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
         "/style.css": ("style.css", "text/css")}
RUN = re.compile(r"/api/runs/([0-9a-f]{32})(/replay)?")


def server(port, store, model=None):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, mime="application/json"):
            if mime == "application/json":
                body = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; object-src 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in FILES:
                file, mime = FILES[self.path]
                return self.reply(200, (ASSETS / file).read_bytes(), mime)
            if self.path == "/api/config":
                return self.reply(200, {"model": model})
            if self.path == "/api/runs":
                return self.reply(200, store.recent())
            match = RUN.fullmatch(self.path)
            if match and not match[2]:
                trace = store.read(match[1])
                if trace:
                    return self.reply(200, trace)
            self.reply(404, {"error": "not found"})

        def do_POST(self):
            port = self.server.server_port
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host") not in hosts or self.headers.get("Origin") not in (
                    None, "http://" + self.headers.get("Host", "")):
                return self.reply(403, {"error": "local origin required"})
            if self.headers.get_content_type() != "application/json":
                return self.reply(415, {"error": "expected application/json"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= 4096:
                    return self.reply(413, {"error": "request too large"})
                data = json.loads(self.rfile.read(size)) if size else {}
                if not isinstance(data, dict):
                    raise ValueError("expected object")
                if self.path == "/api/runs":
                    if set(data) != {"seed", "policy", "fault"}:
                        raise ValueError("expected seed, policy and fault")
                    use_model = model if data["policy"] == "ollama" else None
                    trace = execute(**data, decide=local_policy(model) if use_model else None, model=use_model)
                    return self.reply(201, {"id": store.save(trace), "trace": trace})
                match = RUN.fullmatch(self.path)
                if match and match[2]:
                    trace = store.read(match[1])
                    if trace:
                        return self.reply(200, replay(trace))
                self.reply(404, {"error": "not found"})
            except (ValueError, TypeError, RecursionError) as exc:
                self.reply(400, {"error": str(exc)})
            except RuntimeError as exc:
                self.reply(502, {"error": str(exc)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
