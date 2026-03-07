#!/usr/bin/env python3
"""
Codex Guardian — Dashboard Server

Usage:
    python server.py         # starts on port 8080
    PORT=9000 python server.py

Then open http://localhost:8080 in your browser.
"""

import http.server
import json
import os
import sys

PORT         = int(os.environ.get("PORT", 8080))
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DASHBOARD    = os.path.join(PROJECT_ROOT, "dashboard")
AUDIT_LOG    = os.path.join(PROJECT_ROOT, "audit_log.json")

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".js":   "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".ico":  "image/x-icon",
    ".png":  "image/png",
    ".svg":  "image/svg+xml",
}


class Handler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/api/audit":
            self._api_audit()
        elif path in ("/", "/index.html"):
            self._file(os.path.join(DASHBOARD, "index.html"))
        else:
            rel  = path.lstrip("/")
            full = os.path.join(DASHBOARD, rel)
            if os.path.isfile(full):
                self._file(full)
            else:
                self.send_error(404)

    # ── /api/audit ────────────────────────────────────────────
    def _api_audit(self):
        entries = []
        if os.path.isfile(AUDIT_LOG):
            with open(AUDIT_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

        body = json.dumps(entries, indent=2).encode("utf-8")
        self._respond(200, "application/json; charset=utf-8", body, no_cache=True)

    # ── static files ──────────────────────────────────────────
    def _file(self, filepath):
        ext   = os.path.splitext(filepath)[1].lower()
        ctype = MIME.get(ext, "application/octet-stream")
        try:
            with open(filepath, "rb") as f:
                body = f.read()
            self._respond(200, ctype, body)
        except IOError:
            self.send_error(404)

    # ── helper ────────────────────────────────────────────────
    def _respond(self, code, ctype, body, *, no_cache=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if no_cache:
            self.send_header("Cache-Control", "no-cache, no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Only log API calls, suppress static-file noise during demo
        if args and "/api/" in str(args[0]):
            print(f"  [{args[1]}] {args[0]}")


if __name__ == "__main__":
    with http.server.HTTPServer(("", PORT), Handler) as httpd:
        print()
        print("  ⬡  Codex Guardian — Command Center")
        print(f"  →  http://localhost:{PORT}")
        print("      (Ctrl+C to stop)\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Server stopped.")
            sys.exit(0)
