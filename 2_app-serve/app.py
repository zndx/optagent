# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Serve the status snapshot over HTTP.

CML sets CDSW_APP_PORT and reverse-proxies 127.0.0.1. Locally the process
listens on port 8123. PORT overrides both.
"""

import html
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def project_root() -> Path:
    """Find the repository root when CML runs this file inside a session.

    A session executes the script in a notebook cell, so __file__ is unset.
    """

    for key in ("CDSW_PROJECT_DIR", "ML_PROJECT_DIR"):
        value = os.environ.get(key)
        if value:
            return Path(value)
    start = Path.cwd()
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    file_name = globals().get("__file__")
    if file_name:
        here = Path(file_name).resolve()
        for candidate in here.parents:
            if (candidate / "pyproject.toml").is_file():
                return candidate
    return start


ROOT = project_root()
sys.path.insert(0, str(ROOT / "src"))

from optagent.status import greeting_from_env, read_status, status_path


def app_port() -> int:
    return int(os.environ.get("PORT") or os.environ.get("CDSW_APP_PORT") or "8123")


def render_page(status: dict | None, greeting: str) -> str:
    if status is None:
        recorded = "The prepare job has not written a snapshot yet."
        shown = greeting
        version = ""
    else:
        recorded = f"Snapshot written at {status.get('written_at', '')}."
        shown = str(status.get("greeting", greeting))
        version = str(status.get("prototype_version", ""))
    version_line = f"<p>Prototype version {html.escape(version)}</p>" if version else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Optagent</title>
  <style>
    body {{
      margin: 0;
      font-family: "Source Sans 3", "Segoe UI", sans-serif;
      background: #f4f7f6;
      color: #1c2b24;
    }}
    main {{
      max-width: 40rem;
      margin: 0 auto;
      padding: 2rem 1.25rem 3rem;
    }}
    h1 {{ font-weight: 600; letter-spacing: -0.02em; }}
    .card {{
      background: white;
      border: 1px solid #d5e0da;
      border-radius: 8px;
      padding: 1rem 1.25rem;
      margin-top: 1rem;
    }}
    ol {{ padding-left: 1.2rem; }}
    a {{ color: #0b6b4a; }}
  </style>
</head>
<body>
  <main>
    <h1>Optagent</h1>
    <p>{html.escape(shown)}</p>
    {version_line}
    <div class="card">
      <p>{html.escape(recorded)}</p>
      <p><a href="/health">Health</a></p>
    </div>
    <div class="card">
      <p>Cloudera Machine Learning runs these steps from <code>.project-metadata.yaml</code>:</p>
      <ol>
        <li>Install dependencies</li>
        <li>Prepare project</li>
        <li>Serve this application</li>
      </ol>
    </div>
  </main>
</body>
</html>
"""


def response_for(method: str, path: str) -> tuple[int, str, bytes]:
    if method != "GET":
        return 405, "text/plain; charset=utf-8", b"method not allowed\n"
    route = urllib.parse.urlparse(path).path
    if route == "/health":
        return 200, "text/plain; charset=utf-8", b"ok\n"
    if route in ("/", "/index.html"):
        page = render_page(read_status(status_path(ROOT)), greeting_from_env())
        return 200, "text/html; charset=utf-8", page.encode("utf-8")
    return 404, "text/plain; charset=utf-8", b"not found\n"


def make_handler() -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, method: str) -> None:
            status, content_type, body = response_for(method, self.path)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            self._send("GET")

        def do_POST(self) -> None:
            self._send("POST")

        def log_message(self, fmt: str, *args) -> None:
            print(fmt % args, flush=True)

    return Handler


def serve(host: str = "127.0.0.1") -> None:
    class Server(ThreadingHTTPServer):
        allow_reuse_address = True

    server = Server((host, app_port()), make_handler())
    print(f"serving on http://{host}:{server.server_port}", flush=True)
    server.serve_forever()


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
