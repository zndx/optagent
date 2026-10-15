import { Switch } from "@cloudflare/kumo";
import { useEffect, useState } from "react";

import { applyColorMode, type ColorMode } from "./theme/colorMode";

type Member = {
  project: string;
  kind: string;
  name: string;
  "metadata-location": string;
};

type Brand = {
  id: string;
  display_name: string;
  logo_href: string;
  logo_href_light?: string;
  favicon_href?: string;
  logo_alt: string;
  has_logo: boolean;
};

type Panel = { id: string; title: string; project: string; kind: string; body: string };
type SummaryGroup = { id: string; title: string; items: string[] };
type SummaryDoc = { groups?: SummaryGroup[]; panels?: Panel[]; foot?: string; "snapshot-id"?: string };

type Workspace = {
  sample_mode: boolean;
  sample_mode_source: string;
  snapshot_s3_uri: string;
  snapshot_endpoint: string;
  color_mode: ColorMode;
  brand_id: string;
  brand: Brand;
  brands: Brand[];
  snapshot: { "snapshot-id": string; "sequence-number": number; members: Member[] } | null;
};

const NAV = [
  { href: "/", label: "Landing" },
  { href: "/sessions", label: "Sessions" },
  { href: "/summary", label: "Summary" },
  { href: "/terminal", label: "Terminal" },
  { href: "/settings", label: "Settings" },
];

function pathName(): string {
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  return NAV.some((item) => item.href === path) ? path : "/";
}

function applyFavicon(href: string): void {
  if (!href) return;
  let link = document.querySelector<HTMLLinkElement>('link[rel="icon"][data-optagent-brand="1"]');
  if (!link) {
    link = document.createElement("link");
    link.rel = "icon";
    link.type = "image/svg+xml";
    link.dataset.optagentBrand = "1";
    document.head.appendChild(link);
  }
  link.href = href;
}

export default function App() {
  const route = pathName();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [summary, setSummary] = useState<SummaryDoc>({});
  const [section, setSection] = useState("all");
  const [lens, setLens] = useState("all");
  const [traces, setTraces] = useState("Phoenix project is not connected.");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  function applyWorkspace(data: Workspace) {
    setWorkspace(data);
    if (data.color_mode === "light" || data.color_mode === "dark") applyColorMode(data.color_mode);
    applyFavicon(data.brand?.favicon_href || data.brand?.logo_href || "");
  }

  useEffect(() => {
    fetch("/api/optagent/v1/workspace")
      .then((response) => {
        if (!response.ok) throw new Error(`workspace ${response.status}`);
        return response.json() as Promise<Workspace>;
      })
      .then((data) => {
        applyWorkspace(data);
        setBusy(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "workspace unavailable");
        setBusy(false);
      });
  }, []);

  useEffect(() => {
    if (route !== "/summary") return;
    fetch("/api/optagent/v1/summary")
      .then((response) => response.json())
      .then((data: SummaryDoc) => setSummary(data))
      .catch(() => setSummary({}));
  }, [route]);

  useEffect(() => {
    if (route !== "/sessions") return;
    fetch("/api/optagent/v1/sessions")
      .then((response) => response.json())
      .then((data: { note?: string }) => setTraces(data.note || "Phoenix project is not connected."))
      .catch(() => setTraces("Phoenix project is not connected."));
  }, [route]);

  async function post(path: string, payload: object) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(`${path} ${response.status}`);
      applyWorkspace((await response.json()) as Workspace);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "settings failed");
    } finally {
      setBusy(false);
    }
  }

  const mode = workspace?.color_mode === "light" ? "light" : "dark";
  const logoHref =
    mode === "light" && workspace?.brand.logo_href_light
      ? workspace.brand.logo_href_light
      : workspace?.brand.logo_href;
  return (
    <div className="flex min-h-screen flex-col">
      <header className="atelier-chrome">
        <a className="brand" href="/">
          {logoHref ? (
            <img
              className="brand-logo"
              src={logoHref}
              alt={workspace?.brand.logo_alt || "OptAgent"}
              height={28}
            />
          ) : null}
          <span className="brand-name">OptAgent</span>
        </a>
        <nav className="nav" aria-label="Primary">
          {NAV.map((item) => (
            <a key={item.href} href={item.href} className={route === item.href ? "active" : undefined}>
              {item.label}
            </a>
          ))}
        </nav>
        <a className="chrome-icon" href="/settings" aria-label="Settings" title="Settings">
          <Gear />
        </a>
      </header>
      <main className="shell-main">
        {route === "/" && <Landing />}
        {route === "/sessions" && <Sessions note={traces} />}
        {route === "/summary" && (
          <Summary
            summary={summary}
            section={section}
            lens={lens}
            onSection={setSection}
            onLens={setLens}
          />
        )}
        {route === "/terminal" && <Terminal />}
        {route === "/settings" && (
          <Settings
            workspace={workspace}
            busy={busy}
            mode={mode}
            onTheme={(dark) => void post("/api/optagent/v1/theme", { mode: dark ? "dark" : "light" })}
            onBrand={(brandId) => void post("/api/optagent/v1/brand", { brand_id: brandId })}
            onSample={(enabled) => void post("/api/optagent/v1/sample-mode", { enabled })}
          />
        )}
        {error ? (
          <p className="px-6 text-sm" style={{ color: "var(--color-kumo-danger, #f28881)" }}>
            {error}
          </p>
        ) : null}
      </main>
    </div>
  );
}

function Landing() {
  return (
    <section className="page">
      <h1>OptAgent</h1>
      <p className="muted">A workspace for agent traces, snapshot lineups, and a terminal. The live warehouse stays where it is.</p>
      <div className="card-row">
        <a className="frame-card" href="/sessions"><strong>Sessions</strong><span>Arize Phoenix agent tracing</span></a>
        <a className="frame-card" href="/summary"><strong>Summary</strong><span>Lineup of rich-text panels</span></a>
        <a className="frame-card" href="/terminal"><strong>Terminal</strong><span>Embedded Ghostty</span></a>
        <a className="frame-card" href="/settings"><strong>Settings</strong><span>Brand, theme, sample mode</span></a>
      </div>
    </section>
  );
}

function Sessions({ note }: { note: string }) {
  return (
    <section className="page">
      <h1>Sessions</h1>
      <p className="muted">Arize Phoenix agent tracing. Traces stay in Phoenix and are not copied here.</p>
      <div className="frame-card">
        <strong>Phoenix</strong>
        <span>{note}</span>
        <table>
          <thead>
            <tr>
              <th>Project</th>
              <th>Spans</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={2}>No Phoenix project is connected.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Summary({
  summary,
  section,
  lens,
  onSection,
  onLens,
}: {
  summary: SummaryDoc;
  section: string;
  lens: string;
  onSection: (id: string) => void;
  onLens: (id: string) => void;
}) {
  const groups = summary.groups ?? [];
  const panels = (summary.panels ?? []).filter((panel) => {
    if (section !== "all" && panel.project !== section) return false;
    if (lens !== "all" && panel.kind !== lens) return false;
    return true;
  });
  return (
    <div className="sum-page">
      <aside className="sum-rail" aria-label="Summary lineup">
        <div className="sum-rail-head">
          <button type="button" className="sum-week-btn">
            {summary["snapshot-id"] ? summary["snapshot-id"].slice(0, 8) : "sample"}
          </button>
        </div>
        {groups.map((group) => (
          <div className="sum-group" key={group.id}>
            <div className="sum-group-title">{group.title}</div>
            <button
              type="button"
              className={(group.id === "lens" ? lens : section) === "all" ? "sum-tab active" : "sum-tab"}
              onClick={() => (group.id === "lens" ? onLens("all") : onSection("all"))}
            >
              All
            </button>
            {group.items.map((item) => {
              const active = (group.id === "lens" ? lens : section) === item;
              return (
                <button
                  key={item}
                  type="button"
                  className={active ? "sum-tab active" : "sum-tab"}
                  onClick={() => (group.id === "lens" ? onLens(item) : onSection(item))}
                >
                  {item}
                </button>
              );
            })}
          </div>
        ))}
        <div className="sum-rail-foot muted">{summary.foot || "federation.project=optagent"}</div>
      </aside>
      <section className="sum-trail" aria-label="Lineup">
        {panels.length === 0 ? <p className="muted">No panels in this lineup.</p> : null}
        {panels.map((panel) => (
          <article className="sum-panel" key={panel.id}>
            <header className="sum-panel-head">
              <h2>{panel.title}</h2>
              <span className="muted sum-panel-meta">
                {panel.project} · {panel.kind}
              </span>
            </header>
            <div className="sum-panel-body rich-body">{panel.body}</div>
            <footer className="muted sum-panel-id">{panel.id}</footer>
          </article>
        ))}
      </section>
    </div>
  );
}

function Terminal() {
  return (
    <div className="term-full">
      <div className="term-status">Ghostty not connected</div>
      <div id="terminal-wrap">
        <div id="terminal">
          {`OptAgent terminal frame\n\nThis is the Ghostty embed slot used by Gaius:\nterm-full → terminal-wrap → #terminal\n\nThe PTY bridge is not attached.`}
        </div>
      </div>
    </div>
  );
}

function Settings({
  workspace,
  busy,
  mode,
  onTheme,
  onBrand,
  onSample,
}: {
  workspace: Workspace | null;
  busy: boolean;
  mode: ColorMode;
  onTheme: (dark: boolean) => void;
  onBrand: (brandId: string) => void;
  onSample: (enabled: boolean) => void;
}) {
  return (
    <section className="page">
      <h1>Settings</h1>
      <p className="muted">Deployment brand. Session theme and sample mode. The product name stays OptAgent.</p>
      <section className="settings-card" id="theme">
        <h2>Theme</h2>
        <Switch
          label="Dark theme"
          checked={mode === "dark"}
          disabled={busy || workspace === null}
          onCheckedChange={onTheme}
        />
      </section>
      <section className="settings-card" id="branding">
        <h2>Branding</h2>
        <p className="muted">Logo pack only. Weathership, then Cloudera, then Custom.</p>
        <div className="brand-grid" role="radiogroup" aria-label="Logo brand pack">
          {(workspace?.brands ?? []).map((brand) => (
            <button
              key={brand.id}
              type="button"
              role="radio"
              aria-checked={workspace?.brand_id === brand.id}
              disabled={busy || !brand.has_logo}
              className={workspace?.brand_id === brand.id ? "brand-card selected" : "brand-card"}
              onClick={() => onBrand(brand.id)}
            >
              <span className="brand-card-preview">
                {brand.has_logo ? (
                  <img
                    src={mode === "light" && brand.logo_href_light ? brand.logo_href_light : brand.logo_href}
                    alt={brand.logo_alt}
                    height={28}
                  />
                ) : (
                  <span>{brand.display_name}</span>
                )}
              </span>
              <span className="brand-card-name">{brand.display_name}</span>
              <span className="muted">{brand.id}</span>
            </button>
          ))}
        </div>
      </section>
      <section className="settings-card">
        <h2>Sample mode</h2>
        <Switch
          label="Sample mode"
          labelTooltip="Use the signals-snapshot pointer. Impala is not contacted."
          checked={workspace?.sample_mode ?? false}
          disabled={busy || workspace === null}
          onCheckedChange={onSample}
        />
        <p className="muted">Snapshot {workspace?.snapshot_s3_uri}</p>
      </section>
    </section>
  );
}

function Gear() {
  return (
    <svg className="icon-gear" viewBox="64 64 896 896" width="18" height="18" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        d="M924.8 625.7l-65.5-56c3.1-19 4.7-38.4 4.7-57.8s-1.6-38.8-4.7-57.8l65.5-56a32.03 32.03 0 009.3-35.2l-.9-2.6a443.74 443.74 0 00-79.7-137.9l-1.8-2.1a32.12 32.12 0 00-35.1-9.5l-81.3 28.9c-30-24.6-63.5-44-99.7-57.6l-15.7-85a32.05 32.05 0 00-25.8-25.7l-2.7-.5c-52.1-9.4-106.9-9.4-159 0l-2.7.5a32.05 32.05 0 00-25.8 25.7l-15.8 85.4a351.86 351.86 0 00-99 57.4l-81.9-29.1a32 32 0 00-35.1 9.5l-1.8 2.1a446.02 446.02 0 00-79.7 137.9l-.9 2.6c-4.5 12.5-.8 26.5 9.3 35.2l66.3 56.6c-3.1 18.8-4.6 38-4.6 57.1 0 19.2 1.5 38.4 4.6 57.1L99 625.5a32.03 32.03 0 00-9.3 35.2l.9 2.6c18.1 50.4 44.9 96.9 79.7 137.9l1.8 2.1a32.12 32.12 0 0035.1 9.5l81.9-29.1c29.8 24.5 63.1 43.9 99 57.4l15.8 85.4a32.05 32.05 0 0025.8 25.7l2.7.5a449.4 449.4 0 00159 0l2.7-.5a32.05 32.05 0 0025.8-25.7l15.7-85a350 350 0 0099.7-57.6l81.3 28.9a32 32 0 0035.1-9.5l1.8-2.1c34.8-41.1 61.6-87.5 79.7-137.9l.9-2.6c4.5-12.3.8-26.3-9.3-35zM788.3 465.9c2.5 15.1 3.8 30.6 3.8 46.1s-1.3 31-3.8 46.1l-6.6 40.1 74.7 63.9a370.03 370.03 0 01-42.6 73.6L721 702.8l-31.4 25.8c-23.9 19.6-50.5 35-79.3 45.8l-38.1 14.3-17.9 97a377.5 377.5 0 01-85 0l-17.9-97.2-37.8-14.5c-28.5-10.8-55-26.2-78.7-45.7l-31.4-25.9-93.4 33.2c-17-22.9-31.2-47.6-42.6-73.6l75.5-64.5-6.5-40c-2.4-14.9-3.7-30.3-3.7-45.5 0-15.3 1.2-30.6 3.7-45.5l6.5-40-75.5-64.5c11.3-26.1 25.6-50.7 42.6-73.6l93.4 33.2 31.4-25.9c23.7-19.5 50.2-34.9 78.7-45.7l37.9-14.3 17.9-97.2c28.1-3.2 56.8-3.2 85 0l17.9 97 38.1 14.3c28.7 10.8 55.4 26.2 79.3 45.8l31.4 25.8 92.8-32.9c17 22.9 31.2 47.6 42.6 73.6L781.8 426l6.5 39.9zM512 326c-97.2 0-176 78.8-176 176s78.8 176 176 176 176-78.8 176-176-78.8-176-176-176zm79.2 255.2A111.6 111.6 0 01512 614c-29.9 0-58-11.7-79.2-32.8A111.6 111.6 0 01400 502c0-29.9 11.7-58 32.8-79.2C454 401.6 482.1 390 512 390c29.9 0 58 11.6 79.2 32.8A111.6 111.6 0 01624 502c0 29.9-11.7 58-32.8 79.2z"
      />
    </svg>
  );
}
