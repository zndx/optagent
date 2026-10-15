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

from optagent.config import load_runtime
from optagent.ledger import DATABASE, SURFACE, TIER0, TIER1
from optagent.status import greeting_from_env, read_status, status_path


def app_port() -> int:
    return int(os.environ.get("PORT") or os.environ.get("CDSW_APP_PORT") or "8123")


def _shell(active: str, body: str) -> str:
    def link(href: str, label: str) -> str:
        cls = " active" if active == href else ""
        return f'<a class="nav-link{cls}" href="{href}">{label}</a>'

    return f"""<!DOCTYPE html>
<html lang="en" data-mode="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Optagent</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; min-height: 100%; background: #f4f6f8; color: #1c2430;
      font-family: system-ui, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
    .chrome {{ display: flex; align-items: center; gap: 16px; height: 56px;
      padding: 0 20px; background: #101418; color: #e5e8ec; border-bottom: 1px solid #30363c; }}
    .chrome a {{ color: #9fa5ac; text-decoration: none; }}
    .chrome a:hover, .chrome a.active {{ color: #e5e8ec; }}
    .brand {{ color: #e5e8ec; font-weight: 600; font-size: 18px; letter-spacing: 0.04em; }}
    .nav {{ display: flex; gap: 16px; }}
    main {{ max-width: 52rem; margin: 0 auto; padding: 1.5rem 1.25rem 3rem; }}
    .card {{ background: white; border: 1px solid #d5dde6; border-radius: 8px;
      padding: 1rem 1.25rem; margin-top: 1rem; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid #e3e8ee; }}
    code {{ font-size: 0.92em; }}
    a {{ color: #0b6b4a; }}
  </style>
</head>
<body>
  <header class="chrome">
    <a class="brand" href="/">Optagent</a>
    <nav class="nav">
      {link("/", "Ledger")}
      {link("/tiers", "Tiers")}
      {link("/sessions", "Sessions")}
    </nav>
  </header>
  <main>
    {body}
  </main>
</body>
</html>
"""


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
    warehouse = None if status is None else status.get("warehouse")
    if not isinstance(warehouse, dict):
        warehouse_html = "<p>Warehouse status was not recorded.</p>"
    else:
        warehouse_html = (
            f"<p>Postgres {html.escape(str(warehouse.get('postgres', '')))}. "
            f"FDW {html.escape(str(warehouse.get('fdw', '')))}. "
            f"Server {html.escape(str(warehouse.get('server') or 'not configured'))}.</p>"
            "<p>Kudu foreign tables use access kudu_scan. "
            "Iceberg tables and UNION views use access impala_sql.</p>"
        )
    runtime = load_runtime()
    body = f"""
    <h1>Ledger</h1>
    <p>{html.escape(shown)}</p>
    {version_line}
    <p>Posture {html.escape(runtime.posture)}. Engine {html.escape(runtime.engine)}.</p>
    <div class="card">
      <p><code>{DATABASE}.{SURFACE}</code> is the transparent surface.
      Hot hours are <code>{TIER0}</code> on Kudu. Settled hours are <code>{TIER1}</code> on Iceberg.
      A hot hour still in tier0 is masked out of tier1.</p>
    </div>
    <div class="card">
      <p>{html.escape(recorded)}</p>
      <p><a href="/health">Health</a></p>
    </div>
    <div class="card">
      <p>Cloudera Machine Learning runs these steps from <code>.project-metadata.yaml</code>:</p>
      <ol>
        <li>Install dependencies</li>
        <li>Register Impala FDW</li>
        <li>Prepare project</li>
        <li>Serve this application</li>
      </ol>
    </div>
    <div class="card">
      {warehouse_html}
    </div>
    """
    return _shell("/", body)


def render_tiers() -> str:
    rows = (
        (TIER0, "Kudu", "kudu_scan", "INSERT and hot scan"),
        (TIER1, "Iceberg", "impala_sql", "Settled hours. Read only."),
        (SURFACE, "Impala view", "impala_sql", "tier0 UNION tier1, hot hours masked"),
    )
    rendered = "\n".join(
        "<tr>"
        + "".join(f"<td><code>{html.escape(cell)}</code></td>" for cell in row)
        + "</tr>"
        for row in rows
    )
    body = f"""
    <h1>Tiers</h1>
    <div class="card">
      <table>
        <thead><tr><th>Relation</th><th>Store</th><th>Access</th><th>Role</th></tr></thead>
        <tbody>{rendered}</tbody>
      </table>
    </div>
    <div class="card">
      <p>Writes land in <code>{TIER0}</code>. <code>{TIER1}</code> is registered in the catalog,
      not created with Impala <code>STORED AS ICEBERG</code>.</p>
    </div>
    """
    return _shell("/tiers", body)


def render_sessions() -> str:
    body = """
    <h1>Sessions</h1>
    <div class="card">
      <p>Session inspection starts from the agentsview checkout
      <code>../../rch/oss-agentsview</code>
      (<code>git@github.com:weathership/oss-agentsview.git</code>).</p>
      <p><code>go.work</code> and <code>ui/go.mod</code> replace
      <code>go.kenn.io/agentsview</code> with that working tree.
      <code>ui/package.json</code> links <code>agentsview-frontend</code> the same way.</p>
    </div>
    """
    return _shell("/sessions", body)


def response_for(method: str, path: str) -> tuple[int, str, bytes]:
    if method != "GET":
        return 405, "text/plain; charset=utf-8", b"method not allowed\n"
    route = urllib.parse.urlparse(path).path
    if route == "/health":
        return 200, "text/plain; charset=utf-8", b"ok\n"
    if route in ("/", "/index.html"):
        page = render_page(read_status(status_path(ROOT)), greeting_from_env())
        return 200, "text/html; charset=utf-8", page.encode("utf-8")
    if route == "/tiers":
        return 200, "text/html; charset=utf-8", render_tiers().encode("utf-8")
    if route == "/sessions":
        return 200, "text/html; charset=utf-8", render_sessions().encode("utf-8")
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
