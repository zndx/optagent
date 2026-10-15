# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Serve the status snapshot over HTTP.

CML sets CDSW_APP_PORT and reverse-proxies 127.0.0.1. Locally the process
listens on port 9892, beside Signals :9889 and Gaius :9890.
PORT overrides both. CML sets CDSW_APP_PORT.
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
    return int(os.environ.get("PORT") or os.environ.get("CDSW_APP_PORT") or "9892")


def _chrome_controls(settings_active: bool = False) -> str:
    """Waffle, mode, and settings. Glyphs match Ægir: 9-dot, Phosphor sun/moon, Ant gear."""

    gear = " active" if settings_active else ""
    return """
    <div class="chrome-tools">
      <button type="button" id="waffle-toggle" class="chrome-icon" aria-label="Federated apps" aria-pressed="false" title="Federated primary UIs">
        <svg class="icon-waffle" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
          <circle cx="5" cy="5" r="1.7" fill="currentColor"/>
          <circle cx="12" cy="5" r="1.7" fill="currentColor"/>
          <circle cx="19" cy="5" r="1.7" fill="currentColor"/>
          <circle cx="5" cy="12" r="1.7" fill="currentColor"/>
          <circle cx="12" cy="12" r="1.7" fill="currentColor"/>
          <circle cx="19" cy="12" r="1.7" fill="currentColor"/>
          <circle cx="5" cy="19" r="1.7" fill="currentColor"/>
          <circle cx="12" cy="19" r="1.7" fill="currentColor"/>
          <circle cx="19" cy="19" r="1.7" fill="currentColor"/>
        </svg>
      </button>
      <button type="button" id="mode-toggle" class="chrome-icon" aria-label="Switch to light" title="Switch to light">
        <svg class="icon-sun" viewBox="0 0 256 256" width="16" height="16" aria-hidden="true" focusable="false">
          <path fill="currentColor" d="M116,36V20a12,12,0,0,1,24,0V36a12,12,0,0,1-24,0Zm80,92a68,68,0,1,1-68-68A68.07,68.07,0,0,1,196,128Zm-24,0a44,44,0,1,0-44,44A44.05,44.05,0,0,0,172,128ZM51.51,68.49a12,12,0,1,0,17-17l-12-12a12,12,0,0,0-17,17Zm0,119-12,12a12,12,0,0,0,17,17l12-12a12,12,0,1,0-17-17ZM196,72a12,12,0,0,0,8.49-3.51l12-12a12,12,0,0,0-17-17l-12,12A12,12,0,0,0,196,72Zm8.49,115.51a12,12,0,0,0-17,17l12,12a12,12,0,0,0,17-17ZM48,128a12,12,0,0,0-12-12H20a12,12,0,0,0,0,24H36A12,12,0,0,0,48,128Zm80,80a12,12,0,0,0-12,12v16a12,12,0,0,0,24,0V220A12,12,0,0,0,128,208Zm108-92H220a12,12,0,0,0,0,24h16a12,12,0,0,0,0-24Z"/>
        </svg>
        <svg class="icon-moon" viewBox="0 0 256 256" width="16" height="16" aria-hidden="true" focusable="false">
          <path fill="currentColor" d="M236.37,139.4a12,12,0,0,0-12-3A84.07,84.07,0,0,1,119.6,31.59a12,12,0,0,0-15-15A108.86,108.86,0,0,0,49.69,55.07,108,108,0,0,0,136,228a107.09,107.09,0,0,0,64.93-21.69,108.86,108.86,0,0,0,38.44-54.94A12,12,0,0,0,236.37,139.4Zm-49.88,47.74A84,84,0,0,1,68.86,69.51,84.93,84.93,0,0,1,92.27,48.29Q92,52.13,92,56A108.12,108.12,0,0,0,200,164q3.87,0,7.71-.27A84.79,84.79,0,0,1,186.49,187.14Z"/>
        </svg>
      </button>
      <a href="/settings" class="chrome-icon""" + gear + """" aria-label="Settings" title="Settings — deployment configuration">
        <svg class="icon-gear" viewBox="64 64 896 896" width="16" height="16" aria-hidden="true" focusable="false">
          <path fill="currentColor" d="M924.8 625.7l-65.5-56c3.1-19 4.7-38.4 4.7-57.8s-1.6-38.8-4.7-57.8l65.5-56a32.03 32.03 0 009.3-35.2l-.9-2.6a443.74 443.74 0 00-79.7-137.9l-1.8-2.1a32.12 32.12 0 00-35.1-9.5l-81.3 28.9c-30-24.6-63.5-44-99.7-57.6l-15.7-85a32.05 32.05 0 00-25.8-25.7l-2.7-.5c-52.1-9.4-106.9-9.4-159 0l-2.7.5a32.05 32.05 0 00-25.8 25.7l-15.8 85.4a351.86 351.86 0 00-99 57.4l-81.9-29.1a32 32 0 00-35.1 9.5l-1.8 2.1a446.02 446.02 0 00-79.7 137.9l-.9 2.6c-4.5 12.5-.8 26.5 9.3 35.2l66.3 56.6c-3.1 18.8-4.6 38-4.6 57.1 0 19.2 1.5 38.4 4.6 57.1L99 625.5a32.03 32.03 0 00-9.3 35.2l.9 2.6c18.1 50.4 44.9 96.9 79.7 137.9l1.8 2.1a32.12 32.12 0 0035.1 9.5l81.9-29.1c29.8 24.5 63.1 43.9 99 57.4l15.8 85.4a32.05 32.05 0 0025.8 25.7l2.7.5a449.4 449.4 0 00159 0l2.7-.5a32.05 32.05 0 0025.8-25.7l15.7-85a350 350 0 0099.7-57.6l81.3 28.9a32 32 0 0035.1-9.5l1.8-2.1c34.8-41.1 61.6-87.5 79.7-137.9l.9-2.6c4.5-12.3.8-26.3-9.3-35zM788.3 465.9c2.5 15.1 3.8 30.6 3.8 46.1s-1.3 31-3.8 46.1l-6.6 40.1 74.7 63.9a370.03 370.03 0 01-42.6 73.6L721 702.8l-31.4 25.8c-23.9 19.6-50.5 35-79.3 45.8l-38.1 14.3-17.9 97a377.5 377.5 0 01-85 0l-17.9-97.2-37.8-14.5c-28.5-10.8-55-26.2-78.7-45.7l-31.4-25.9-93.4 33.2c-17-22.9-31.2-47.6-42.6-73.6l75.5-64.5-6.5-40c-2.4-14.9-3.7-30.3-3.7-45.5 0-15.3 1.2-30.6 3.7-45.5l6.5-40-75.5-64.5c11.3-26.1 25.6-50.7 42.6-73.6l93.4 33.2 31.4-25.9c23.7-19.5 50.2-34.9 78.7-45.7l37.9-14.3 17.9-97.2c28.1-3.2 56.8-3.2 85 0l17.9 97 38.1 14.3c28.7 10.8 55.4 26.2 79.3 45.8l31.4 25.8 92.8-32.9c17 22.9 31.2 47.6 42.6 73.6L781.8 426l6.5 39.9zM512 326c-97.2 0-176 78.8-176 176s78.8 176 176 176 176-78.8 176-176-78.8-176-176-176zm79.2 255.2A111.6 111.6 0 01512 614c-29.9 0-58-11.7-79.2-32.8A111.6 111.6 0 01400 502c0-29.9 11.7-58 32.8-79.2C454 401.6 482.1 390 512 390c29.9 0 58 11.6 79.2 32.8A111.6 111.6 0 01624 502c0 29.9-11.7 58-32.8 79.2z"/>
        </svg>
      </a>
    </div>
    <aside id="waffle-rail" class="waffle-rail" hidden>
      <div class="waffle-rail-head"><span>Federation</span>
        <button type="button" id="waffle-close" class="chrome-icon" aria-label="Close">×</button>
      </div>
      <p class="waffle-empty">No peers advertising a primary UI.</p>
    </aside>
    """


def _chrome_css() -> str:
    return """
    html[data-theme="keiretsu"][data-mode="dark"],
    html[data-theme="keiretsu"]:not([data-mode="light"]) {
      color-scheme: dark;
      --color-kumo-canvas: #090b0e;
      --color-kumo-base: #101418;
      --color-kumo-elevated: #191d22;
      --color-kumo-line: #30363c;
      --color-kumo-fill: #30363c;
      --text-color-kumo-default: #d4d8dd;
      --text-color-kumo-strong: #e5e8ec;
      --text-color-kumo-subtle: #9fa5ac;
      --text-color-kumo-link: #96a2fc;
    }
    html[data-theme="keiretsu"][data-mode="light"] {
      color-scheme: light;
      --color-kumo-canvas: #eef1f4;
      --color-kumo-base: #f8f9fb;
      --color-kumo-elevated: #ffffff;
      --color-kumo-line: #d3d9df;
      --color-kumo-fill: #e4e8ed;
      --text-color-kumo-default: #25292f;
      --text-color-kumo-strong: #15191d;
      --text-color-kumo-subtle: #5d646b;
      --text-color-kumo-link: #4338ca;
    }
    .chrome-tools { margin-left: auto; display: flex; align-items: center; gap: 8px; }
    .chrome-icon {
      display: inline-flex; align-items: center; justify-content: center;
      width: 30px; height: 30px; border-radius: 6px; cursor: pointer;
      background: transparent; border: 1px solid var(--color-kumo-line);
      color: var(--text-color-kumo-subtle); text-decoration: none;
    }
    .chrome-icon:hover, .chrome-icon.active { color: var(--text-color-kumo-strong); background: var(--color-kumo-fill); }
    .icon-sun, .icon-moon { display: none; }
    html[data-mode="dark"] .icon-sun, html:not([data-mode="light"]) .icon-sun { display: block; }
    html[data-mode="light"] .icon-moon { display: block; }
    .waffle-rail {
      position: fixed; top: 56px; right: 0; z-index: 45; width: min(280px, 92vw);
      background: var(--color-kumo-base); color: var(--text-color-kumo-default);
      border-left: 1px solid var(--color-kumo-line); box-shadow: -8px 0 24px rgba(0,0,0,.25);
    }
    .waffle-rail[hidden] { display: none; }
    .waffle-rail-head {
      display: flex; align-items: center; justify-content: space-between;
      padding: 0.6rem 0.75rem; font-size: 0.78rem; letter-spacing: 0.06em;
      text-transform: uppercase; color: var(--text-color-kumo-subtle);
      border-bottom: 1px solid var(--color-kumo-line);
    }
    .waffle-empty { padding: 0.85rem; font-size: 0.82rem; color: var(--text-color-kumo-subtle); }
    """


def _chrome_script() -> str:
    return """
    <script>
    (function () {
      var root = document.documentElement;
      var btn = document.getElementById('mode-toggle');
      function paint(mode) {
        if (!btn) return;
        var toLight = mode !== 'light';
        var next = toLight ? 'Switch to light' : 'Switch to dark';
        btn.title = next;
        btn.setAttribute('aria-label', next);
      }
      function apply(mode) {
        root.setAttribute('data-mode', mode);
        try { localStorage.setItem('cldr-color-mode', mode); } catch (e) {}
        paint(mode);
      }
      var saved = null;
      try { saved = localStorage.getItem('cldr-color-mode'); } catch (e) {}
      if (saved === 'light' || saved === 'dark') apply(saved);
      else paint(root.getAttribute('data-mode') || 'dark');
      if (btn) btn.addEventListener('click', function () {
        apply(root.getAttribute('data-mode') === 'light' ? 'dark' : 'light');
      });
      var waffle = document.getElementById('waffle-toggle');
      var rail = document.getElementById('waffle-rail');
      var close = document.getElementById('waffle-close');
      function shut() {
        if (!rail || !waffle) return;
        rail.setAttribute('hidden', '');
        waffle.setAttribute('aria-pressed', 'false');
        waffle.classList.remove('active');
      }
      if (waffle && rail) waffle.addEventListener('click', function () {
        var opening = rail.hasAttribute('hidden');
        if (opening) {
          rail.removeAttribute('hidden');
          waffle.setAttribute('aria-pressed', 'true');
          waffle.classList.add('active');
        } else shut();
      });
      if (close) close.addEventListener('click', shut);
    })();
    </script>
    """


_AGENTS_TABS = (
    ("/", "Sessions"),
    ("/usage", "Usage"),
    ("/activity", "Activity"),
    ("/trends", "Trends"),
    ("/recall", "Recall"),
    ("/pinned", "Pinned"),
    ("/quality", "Quality"),
    ("/trash", "Trash"),
    ("/recent-edits", "Recent Edits"),
    ("/data", "Data"),
)


def _sample_choice(query: str, cookie_header: str | None, default: bool) -> tuple[bool, str | None]:
    """Query wins, then the cookie, then the deployment default."""

    chosen = urllib.parse.parse_qs(query).get("sample", [None])[0]
    if chosen is not None:
        enabled = chosen.lower() in {"1", "on", "true"}
        return enabled, "on" if enabled else "off"
    if cookie_header:
        for part in cookie_header.split(";"):
            key, _, value = part.strip().partition("=")
            if key == "optagent-sample-mode" and value in {"on", "off"}:
                return value == "on", None
    return default, None


def render_agentsview(active: str, sample=None) -> str:
    """AgentsView home. Sample mode lists the workspace snapshot instead of an empty archive."""

    tabs = "\n".join(
        f'<a class="tab{" active" if href == active else ""}" href="{href}">{html.escape(label)}</a>'
        for href, label in _AGENTS_TABS
    )
    cards = (
        ("Sessions", "0"),
        ("Messages", "0"),
        ("Projects", "0"),
        ("Active days", "0"),
        ("Messages / session", "–"),
        ("Concentration", "0.0%"),
    )
    card_html = "\n".join(
        f'<article class="metric"><p>{html.escape(label)}</p><strong>{html.escape(value)}</strong></article>'
        for label, value in cards
    )
    if active == "/" and sample is not None:
        rows = "\n".join(
            "<tr>"
            f"<td>{html.escape(member.project)}</td>"
            f"<td>{html.escape(member.kind)}</td>"
            f"<td>{html.escape(member.name)}</td>"
            "</tr>"
            for member in sample.members
        )
        main = f"""
        <h1>Sample workspace</h1>
        <p class="empty">signals-snapshot {html.escape(sample.snapshot_id)}. Sequence {sample.sequence_number}. Pointers only. Impala is not contacted.</p>
        <table>
          <thead><tr><th>Project</th><th>Kind</th><th>Name</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
        """
        side = "\n".join(
            f'<p class="side-empty">{html.escape(project)}</p>' for project in sample.projects
        )
    elif active == "/":
        main = f"""
        <h1>Sessions</h1>
        <div class="metrics">{card_html}</div>
        <p class="empty">No data for this period</p>
        """
        side = '<p class="side-empty">No sessions</p>'
    elif active == "/settings":
        from optagent.config import load_runtime

        runtime = load_runtime()
        uri = runtime.traces_s3_uri
        shown = html.escape(uri) if uri else "not set"
        enabled = sample is not None
        nxt = "off" if enabled else "on"
        label = "Turn sample mode off" if enabled else "Turn sample mode on"
        state = "On" if enabled else "Off"
        endpoint = html.escape(runtime.snapshot_endpoint) if runtime.snapshot_endpoint else "AWS S3"
        snapshot_uri = html.escape(runtime.snapshot_s3_uri)
        main = f"""
        <h1>Settings</h1>
        <article class="metric"><p>Sample mode</p><strong>{state}</strong></article>
        <p class="empty"><a href="/settings?sample={nxt}">{label}</a></p>
        <article class="metric"><p>Workspace snapshot</p><strong>{snapshot_uri}</strong></article>
        <p class="empty">Object storage endpoint {endpoint}. RustFS on the workstation. AWS S3 in the AMP.</p>
        <article class="metric"><p>Trace archive</p><strong>{shown}</strong></article>
        <p class="empty">The full session archive stays out of sample mode. Sample mode reads the snapshot pointer.</p>
        """
        side = '<p class="side-empty">No sessions</p>'
    else:
        title = dict(_AGENTS_TABS).get(active, "Settings")
        main = f"""
        <h1>{html.escape(title)}</h1>
        <p class="empty">No data for this period</p>
        """
        side = '<p class="side-empty">No sessions</p>'
    gear_on = active == "/settings"
    return f"""<!DOCTYPE html>
<html lang="en" data-theme="keiretsu" data-mode="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>agentsview</title>
  <style>
    * {{ box-sizing: border-box; }}
    {_chrome_css()}
    html, body {{ margin: 0; height: 100%; background: var(--color-kumo-canvas); color: var(--text-color-kumo-default);
      font-family: system-ui, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
    body {{ display: flex; flex-direction: column; min-height: 100%; }}
    .top {{ display: flex; align-items: center; gap: 12px; min-height: 52px;
      padding: 0 12px; background: var(--color-kumo-base); border-bottom: 1px solid var(--color-kumo-line); }}
    .brand {{ font-weight: 650; letter-spacing: -0.02em; color: var(--text-color-kumo-strong); text-decoration: none; }}
    .tabs {{ display: flex; gap: 4px; overflow-x: auto; }}
    .tab {{ color: var(--text-color-kumo-subtle); text-decoration: none; padding: 6px 8px; border-radius: 6px;
      white-space: nowrap; font-size: 14px; }}
    .tab.active {{ background: var(--color-kumo-fill); color: var(--text-color-kumo-strong); }}
    .search {{ border: 1px solid var(--color-kumo-line); border-radius: 6px;
      padding: 6px 8px; min-width: 12rem; color: var(--text-color-kumo-subtle); background: var(--color-kumo-canvas); font-size: 13px; }}
    .frame {{ display: flex; flex: 1; min-height: 0; }}
    .sidebar {{ width: 280px; background: var(--color-kumo-base); border-right: 1px solid var(--color-kumo-line); padding: 12px; }}
    .sidebar h2 {{ font-size: 13px; margin: 0 0 8px; color: var(--text-color-kumo-subtle); font-weight: 600; }}
    .side-empty {{ color: var(--text-color-kumo-subtle); font-size: 14px; padding: 12px 0; }}
    main {{ flex: 1; padding: 20px; overflow: auto; }}
    main h1 {{ font-size: 20px; font-weight: 650; margin: 0 0 16px; color: var(--text-color-kumo-strong); }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }}
    .metric {{ background: var(--color-kumo-elevated); border: 1px solid var(--color-kumo-line); border-radius: 8px; padding: 12px; }}
    .metric p {{ margin: 0; color: var(--text-color-kumo-subtle); font-size: 12px; }}
    .metric strong {{ display: block; margin-top: 6px; font-size: 22px; font-weight: 650; }}
    .empty {{ margin-top: 20px; color: var(--text-color-kumo-subtle); }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--color-kumo-line); }}
    .status {{ height: 28px; display: flex; align-items: center; gap: 12px;
      padding: 0 12px; background: var(--color-kumo-base); border-top: 1px solid var(--color-kumo-line);
      color: var(--text-color-kumo-subtle); font-size: 12px; }}
    .status a {{ color: var(--text-color-kumo-link); }}
    @media (max-width: 720px) {{
      .search {{ display: none; }}
      .frame {{ flex-direction: column; }}
      .sidebar {{ width: auto; border-right: 0; border-bottom: 1px solid var(--color-kumo-line); }}
    }}
  </style>
</head>
<body>
  <header class="top">
    <a class="brand" href="/">agentsview</a>
    <nav class="tabs">{tabs}</nav>
    <div class="search" role="search">Search sessions and messages...</div>
    {_chrome_controls(gear_on)}
  </header>
  <div class="frame">
    <aside class="sidebar">
      <h2>Sessions</h2>
      {side}
    </aside>
    <main>{main}</main>
  </div>
  <footer class="status">
    <span>No sessions</span>
    <a href="/ledger">Ledger</a>
  </footer>
  {_chrome_script()}
</body>
</html>
"""


def _shell(active: str, body: str) -> str:
    def link(href: str, label: str) -> str:
        cls = " active" if active == href else ""
        return f'<a class="nav-link{cls}" href="{href}">{label}</a>'

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="keiretsu" data-mode="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Optagent</title>
  <style>
    * {{ box-sizing: border-box; }}
    {_chrome_css()}
    html, body {{ margin: 0; min-height: 100%; background: var(--color-kumo-canvas); color: var(--text-color-kumo-default);
      font-family: system-ui, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
    .chrome {{ display: flex; align-items: center; gap: 16px; min-height: 56px;
      padding: 0 20px; background: var(--color-kumo-base); color: var(--text-color-kumo-default);
      border-bottom: 1px solid var(--color-kumo-line); }}
    .chrome a.nav-link, .chrome a.brand {{ color: var(--text-color-kumo-subtle); text-decoration: none; }}
    .chrome a.nav-link:hover, .chrome a.nav-link.active, .chrome a.brand {{ color: var(--text-color-kumo-strong); }}
    .brand {{ font-weight: 600; font-size: 18px; letter-spacing: 0.04em; }}
    .nav {{ display: flex; gap: 16px; }}
    main {{ max-width: 52rem; margin: 0 auto; padding: 1.5rem 1.25rem 3rem; }}
    .card {{ background: var(--color-kumo-elevated); border: 1px solid var(--color-kumo-line); border-radius: 8px;
      padding: 1rem 1.25rem; margin-top: 1rem; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--color-kumo-line); }}
    code {{ font-size: 0.92em; }}
    main a {{ color: var(--text-color-kumo-link); }}
  </style>
</head>
<body>
  <header class="chrome">
    <a class="brand" href="/">Optagent</a>
    <nav class="nav">
      {link("/ledger", "Ledger")}
      {link("/tiers", "Tiers")}
      {link("/sessions", "Sessions")}
    </nav>
    {_chrome_controls()}
  </header>
  <main>
    {body}
  </main>
  {_chrome_script()}
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
    return _shell("/ledger", body)


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


def _page(route: str, sample) -> tuple[int, str, bytes]:
    if route == "/health":
        return 200, "text/plain; charset=utf-8", b"ok\n"
    if route in ("/", "/index.html"):
        return 200, "text/html; charset=utf-8", render_agentsview("/", sample).encode("utf-8")
    if route == "/ledger":
        page = render_page(read_status(status_path(ROOT)), greeting_from_env())
        return 200, "text/html; charset=utf-8", page.encode("utf-8")
    agents_paths = {href for href, _label in _AGENTS_TABS}
    if route in agents_paths:
        return 200, "text/html; charset=utf-8", render_agentsview(route, sample).encode("utf-8")
    if route == "/tiers":
        return 200, "text/html; charset=utf-8", render_tiers().encode("utf-8")
    if route == "/sessions":
        return 200, "text/html; charset=utf-8", render_sessions().encode("utf-8")
    if route == "/settings":
        return 200, "text/html; charset=utf-8", render_agentsview("/settings", sample).encode("utf-8")
    return 404, "text/plain; charset=utf-8", b"not found\n"


def response_for(
    method: str,
    path: str,
    headers: dict | None = None,
) -> tuple[int, str, bytes, list[tuple[str, str]]]:
    if method != "GET":
        return 405, "text/plain; charset=utf-8", b"method not allowed\n", []
    parsed = urllib.parse.urlparse(path)
    from optagent.config import load_runtime
    from optagent.snapshot import resolve_snapshot

    runtime = load_runtime()
    cookie = None if headers is None else headers.get("Cookie")
    enabled, written = _sample_choice(parsed.query, cookie, runtime.sample_mode)
    sample = resolve_snapshot(runtime.snapshot_s3_uri) if enabled else None
    status, content_type, body = _page(parsed.path, sample)
    extra: list[tuple[str, str]] = []
    if written is not None:
        extra.append(
            (
                "Set-Cookie",
                f"optagent-sample-mode={written}; Path=/; SameSite=Lax",
            )
        )
    return status, content_type, body, extra


def make_handler() -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, method: str) -> None:
            status, content_type, body, extra = response_for(
                method,
                self.path,
                {key: value for key, value in self.headers.items()},
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for key, value in extra:
                self.send_header(key, value)
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
