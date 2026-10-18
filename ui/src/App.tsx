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
type LineupRoot = { id: string; title: string; live?: boolean; entries?: string[] };
type LineupConcept = { iri: string; code: string; label: string; definition: string };
type LineupTable = { name: string; location: string };
type TracingProject = {
  project: string;
  traces: number;
  sessions: number;
  tokens: number;
  grounded: number;
  augmented: number;
  series: { day: string; traces: number }[];
  genera: { code: string; count: number }[];
  top_iris: { iri: string; count: number }[];
  latency_ms: number | null;
  total_cost: number | null;
  errors: number | null;
};
type LineupSessionItem = {
  name: string;
  output: string;
  rich: { text: string; iri?: string; label?: string }[];
  generated_at: number;
  augmented_at: number | null;
};
type LineupDoc = {
  pin: string;
  checkout?: string;
  pin_matches?: boolean;
  release_installed: boolean;
  roots: LineupRoot[];
  lexicon: LineupConcept[];
  schema: LineupTable[];
  tracing: { window: string; projects: TracingProject[] };
  sessions: { id: string; traces: number; items: LineupSessionItem[] }[];
  published: string[];
};
type SummaryDoc = {
  groups?: SummaryGroup[];
  panels?: Panel[];
  foot?: string;
  "snapshot-id"?: string;
  lineup?: LineupDoc;
};

type AgentProfile = {
  name: string;
  display_name: string;
  tenant: string;
  description: string;
  is_default: boolean;
  model: string | null;
  "metadata-location"?: string;
};

type AgentSession = {
  id: string;
  tenant: string;
  profile: string;
  title: string;
  source: string;
  category: "chats" | "automation" | string;
  is_active: boolean;
  archived: boolean;
  message_count: number;
  tool_call_count: number;
  preview: string;
};

type ExplorerSession = {
  id: string;
  project: string;
  activity: string;
  name: string;
  t0: number;
  t1: number;
  trace_count: number;
};
type ExplorerTrace = { trace_id: string; name: string; t: number; span_kind: string };
type TraceDetail = {
  trace_id: string;
  name: string;
  t: number;
  project: string;
  session: string;
  activity: string;
  span_kind: string;
  input: string;
  output: string;
  rich?: { text: string; iri?: string; label?: string }[];
  attributes: Record<string, string | number | unknown>;
};

type SessionsDoc = {
  note?: string;
  connected?: boolean;
  tenants?: { id: string; display_name: string }[];
  profiles?: AgentProfile[];
  sessions?: AgentSession[];
  phoenix?: { projects?: string[]; sessions?: ExplorerSession[] };
  stats?: {
    total: number;
    active: number;
    archived: number;
    messages: number;
    profiles: number;
    tenants: number;
    by_source: Record<string, number>;
  };
};

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
  loaded_snapshot_id?: string;
};

const NAV = [
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
  const [sessionsDoc, setSessionsDoc] = useState<SessionsDoc>({});
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  function applyWorkspace(data: Workspace) {
    setWorkspace(data);
    if (data.color_mode === "light" || data.color_mode === "dark") applyColorMode(data.color_mode);
    applyFavicon(data.brand?.favicon_href || data.brand?.logo_href || "");
  }

  function reloadWorkspace() {
    return fetch("/api/optagent/v1/workspace")
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
  }

  useEffect(() => {
    void reloadWorkspace();
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
      .then((data: SessionsDoc) => setSessionsDoc(data))
      .catch(() => setSessionsDoc({}));
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
        <div className="chrome-right">
          <a
            className={route === "/settings" ? "chrome-icon-btn active" : "chrome-icon-btn"}
            href="/settings"
            aria-label="Settings"
            title="Settings"
          >
            <Gear />
          </a>
        </div>
      </header>
      <main className="shell-main">
        {route === "/" && <Landing workspace={workspace} onRefresh={() => void reloadWorkspace()} />}
        {route === "/sessions" && (
          <Sessions
            doc={sessionsDoc}
            onRefresh={() => {
              fetch("/api/optagent/v1/sessions")
                .then((response) => response.json())
                .then((data: SessionsDoc) => setSessionsDoc(data))
                .catch(() => setSessionsDoc({}));
            }}
          />
        )}
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
            onSnapshot={async (file) => {
              setBusy(true);
              setError("");
              try {
                const response = await fetch("/api/optagent/v1/snapshot", {
                  method: "POST",
                  headers: { "Content-Type": "application/gzip" },
                  body: file,
                });
                if (!response.ok) {
                  const detail = await response.json().catch(() => null);
                  const message = detail && typeof detail.error === "string" ? detail.error : `snapshot ${response.status}`;
                  throw new Error(message);
                }
                applyWorkspace((await response.json()) as Workspace);
              } catch (err: unknown) {
                setError(err instanceof Error ? err.message : "snapshot upload failed");
              } finally {
                setBusy(false);
              }
            }}
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

const WINDOWS = [
  ["24h", "Last 24 hours"],
  ["7d", "Last 7 days"],
  ["30d", "Last 30 days"],
  ["90d", "Last 90 days"],
  ["365d", "Last year"],
  ["all", "All history"],
] as const;

const DOW = ["", "Mon", "", "Wed", "", "Fri", ""];

function countBy(members: Member[], key: "project" | "kind"): [string, number][] {
  const counts = new Map<string, number>();
  for (const member of members) {
    const name = member[key];
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

type ActivityPoint = { t: number; project: string; activity: string; session: string; name: string };

const WINDOW_MS: Record<string, number> = {
  "24h": 86_400_000,
  "7d": 7 * 86_400_000,
  "30d": 30 * 86_400_000,
  "90d": 90 * 86_400_000,
  "365d": 365 * 86_400_000,
};

function heatLevel(count: number, max: number): string {
  if (!count || !max) return "cog-h0";
  const share = count / max;
  if (share > 0.75) return "cog-h4";
  if (share > 0.5) return "cog-h3";
  if (share > 0.25) return "cog-h2";
  return "cog-h1";
}

function ArchiveCognition({
  points,
  projects,
  onRefresh,
}: {
  points: ActivityPoint[];
  projects: string[];
  onRefresh: () => void;
}) {
  const [project, setProject] = useState("");
  const [activity, setActivity] = useState("");
  const [windowId, setWindowId] = useState("365d");
  const now = Date.now();
  const earliest = points.reduce((min, point) => Math.min(min, point.t || now), now);
  const start = windowId === "all" ? earliest : now - (WINDOW_MS[windowId] ?? WINDOW_MS["365d"]);
  const scoped = points.filter((point) => {
    if (project && point.project !== project) return false;
    return point.t >= start && point.t <= now;
  });
  const visible = activity ? scoped.filter((point) => point.activity === activity) : scoped;
  const activities = [...new Set(scoped.map((point) => point.activity).filter(Boolean))].sort();
  const sessions = new Map<string, { id: string; project: string; activity: string; name: string; count: number }>();
  for (const point of visible) {
    const current = sessions.get(point.session) ?? { id: point.session, project: point.project, activity: point.activity, name: point.name, count: 0 };
    current.count += 1;
    if (point.name) current.name = point.name;
    sessions.set(point.session, current);
  }
  const top = [...sessions.values()].sort((a, b) => b.count - a.count || a.id.localeCompare(b.id)).slice(0, 8);
  const byProject = countPairs(visible.map((point) => point.project));
  const byActivity = countPairs(visible.map((point) => point.activity || "span"));
  const activeDays = new Set(visible.map((point) => new Date(point.t).toISOString().slice(0, 10))).size;
  const stats: [string, string, string][] = [
    [String(new Set(visible.map((point) => point.project)).size), "Projects", "in this window"],
    [String(sessions.size), "Sessions", "prefixed ids"],
    [String(visible.length), "Traces", "one span tree"],
    [String(activeDays), "Active days", "UTC"],
    [String(byActivity.length), "Activities", byActivity.map(([name]) => name).slice(0, 3).join(" · ")],
    [String(top[0]?.count ?? 0), "Busiest session", top[0]?.id ?? ""],
  ];
  const heat = buildHeat(visible, windowId, start, now);
  return (
    <div className="cog-page">
      <aside className="cog-rail" aria-label="Snapshot projects">
        <div className="cog-rail-head">
          <span className="cog-kicker">{visible.length} TRACES</span>
          <select className="cog-select" aria-label="Project" value={project} onChange={(event) => { setProject(event.target.value); setActivity(""); }}>
            <option value="">All projects</option>
            {projects.map((name) => (
              <option key={name} value={name}>
                {name} · {points.filter((point) => point.project === name && point.t >= start && point.t <= now).length}
              </option>
            ))}
          </select>
        </div>
        <ul className="cog-rail-list">
          <li>
            <button type="button" className={activity === "" ? "cog-rail-item active" : "cog-rail-item"} onClick={() => setActivity("")}>
              <div className="cog-rail-title">All activity</div>
            </button>
          </li>
          {activities.map((name) => (
            <li key={name}>
              <button type="button" className={activity === name ? "cog-rail-item active" : "cog-rail-item"} onClick={() => setActivity(name)}>
                <div className="cog-rail-title">{name}</div>
                <div className="cog-rail-meta">
                  <span className="cog-type">{name.toUpperCase()}</span>
                  <span className="muted">{scoped.filter((point) => point.activity === name).length}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
        <div className="cog-rail-foot mono muted">signals-snapshot · {projects.length} projects</div>
      </aside>
      <section className="cog-main">
        <div className="cog-toolbar">
          <label className="cog-toolbar-label">
            Window
            <select className="cog-select" aria-label="Window" value={windowId} onChange={(event) => setWindowId(event.target.value)}>
              {WINDOWS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <button type="button" className="btn" onClick={onRefresh}>Refresh</button>
          <span className="pill">snapshot</span>
        </div>
        <div className="cog-stats" aria-label="Snapshot totals">
          {stats.map(([value, label, sub]) => (
            <div className="landing-stat" key={label}>
              <div className="landing-stat-value">{value}</div>
              <div className="landing-stat-label">{label}</div>
              {sub ? <div className="muted cog-stat-sub">{sub}</div> : null}
            </div>
          ))}
        </div>
        <div className="cog-panel">
          <div className="cog-panel-head">
            <h2>Activity</h2>
            <span className="muted">{WINDOWS.find(([value]) => value === windowId)?.[1]}</span>
          </div>
          <Heatmap key={windowId} heat={heat} />
          <p className="muted cog-empty">
            {visible.length} traces · {formatStamp(start)} – {formatStamp(now)}
          </p>
        </div>
        <div className="cog-split">
          <div className="cog-panel">
            <div className="cog-panel-head"><h3>Contributions</h3></div>
            <div className="cog-contrib">
              <Contrib title="By project" rows={byProject} max={Math.max(1, ...byProject.map(([, count]) => count))} />
              <Contrib title="By activity" rows={byActivity} max={Math.max(1, ...byActivity.map(([, count]) => count))} />
            </div>
          </div>
          <div className="cog-panel">
            <div className="cog-panel-head"><h2>Sessions</h2><span className="muted">traces</span></div>
            <ol className="cog-top">
              {top.length === 0 ? <li className="muted cog-empty">No sessions in this window.</li> : null}
              {top.map((item, index) => (
                <li className="cog-top-item" key={item.id}>
                  <span className="cog-top-n">{index + 1}</span>
                  <span>
                    <div className="cog-top-title">{item.name || item.id}</div>
                    <div className="muted cog-top-sub">{item.id}</div>
                  </span>
                  <span className="cog-top-score">{item.count}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>
    </div>
  );
}

function countPairs(values: string[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

type HeatCell = { key: string; count: number; label: string };
type Heat = { mode: "row" | "weeks"; cells: HeatCell[][]; max: number };

function buildHeat(points: ActivityPoint[], windowId: string, start: number, now: number): Heat {
  const counts = new Map<number, number>();
  for (const point of points) {
    const bucket = windowId === "24h" ? Math.floor(point.t / 3_600_000) : Math.floor(point.t / 86_400_000);
    counts.set(bucket, (counts.get(bucket) ?? 0) + 1);
  }
  if (windowId === "24h") {
    const first = Math.floor(start / 3_600_000);
    const cells = Array.from({ length: 24 }, (_, index) => {
      const bucket = first + index;
      const label = new Date(bucket * 3_600_000).toISOString().slice(11, 16);
      return { key: String(bucket), count: counts.get(bucket) ?? 0, label };
    });
    return { mode: "row", cells: [cells], max: Math.max(1, ...cells.map((cell) => cell.count)) };
  }
  if (windowId === "7d" || windowId === "30d") {
    const first = Math.floor(start / 86_400_000);
    const last = Math.floor(now / 86_400_000);
    const cells: HeatCell[] = [];
    for (let bucket = first; bucket <= last; bucket += 1) {
      cells.push({
        key: String(bucket),
        count: counts.get(bucket) ?? 0,
        label: new Date(bucket * 86_400_000).toISOString().slice(0, 10),
      });
    }
    return { mode: "row", cells: [cells], max: Math.max(1, ...cells.map((cell) => cell.count)) };
  }
  const first = Math.floor(start / 86_400_000);
  const last = Math.floor(now / 86_400_000);
  const days: HeatCell[] = [];
  for (let bucket = first; bucket <= last; bucket += 1) {
    days.push({
      key: String(bucket),
      count: counts.get(bucket) ?? 0,
      label: new Date(bucket * 86_400_000).toISOString().slice(0, 10),
    });
  }
  const pad = new Date(first * 86_400_000).getUTCDay();
  const padded: HeatCell[] = [
    ...Array.from({ length: pad }, (_, index) => ({ key: `pad-${index}`, count: 0, label: "" })),
    ...days,
  ];
  const columns: HeatCell[][] = [];
  for (let index = 0; index < padded.length; index += 7) {
    const column = padded.slice(index, index + 7);
    while (column.length < 7) column.push({ key: `end-${index}-${column.length}`, count: 0, label: "" });
    columns.push(column);
  }
  return { mode: "weeks", cells: columns, max: Math.max(1, ...days.map((cell) => cell.count)) };
}

function Heatmap({ heat }: { heat: Heat }) {
  if (heat.mode === "weeks") {
    return (
      <div className="cog-year" role="img" aria-label="Activity heatmap">
        <div className="cog-year-row">
          <div className="cog-year-dows">
            {DOW.map((label, index) => (
              <span key={index}>{label}</span>
            ))}
          </div>
          <div className="cog-year-weeks">
            {heat.cells.map((column, index) => (
              <div className="cog-year-col" key={index}>
                {column.map((cell) => (
                  <span key={cell.key} className={`cog-cell ${heatLevel(cell.count, heat.max)}`} title={cell.label ? `${cell.label}: ${cell.count}` : ""} />
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }
  const row = heat.cells[0] ?? [];
  return (
    <div className={row.length > 14 ? "cog-days" : "cog-hours"} role="img" aria-label="Activity heatmap">
      {row.map((cell) => (
        <span key={cell.key} className={`cog-cell ${heatLevel(cell.count, heat.max)}`} title={`${cell.label}: ${cell.count}`} />
      ))}
    </div>
  );
}

function Landing({ workspace, onRefresh }: { workspace: Workspace | null; onRefresh: () => void }) {
  const [activityPoints, setActivityPoints] = useState<ActivityPoint[]>([]);
  const [activityProjects, setActivityProjects] = useState<string[]>([]);
  const [project, setProject] = useState("");
  const [windowId, setWindowId] = useState("365d");
  useEffect(() => {
    fetch("/api/optagent/v1/activity")
      .then((response) => response.json())
      .then((data: { points?: ActivityPoint[]; projects?: string[] }) => {
        setActivityPoints(data.points ?? []);
        setActivityProjects(data.projects ?? []);
      })
      .catch(() => {
        setActivityPoints([]);
        setActivityProjects([]);
      });
  }, [workspace?.loaded_snapshot_id]);
  if (activityPoints.length) {
    return (
      <ArchiveCognition
        points={activityPoints}
        projects={activityProjects.length ? activityProjects : [...new Set(activityPoints.map((point) => point.project))]}
        onRefresh={() => {
          onRefresh();
          fetch("/api/optagent/v1/activity")
            .then((response) => response.json())
            .then((data: { points?: ActivityPoint[]; projects?: string[] }) => {
              setActivityPoints(data.points ?? []);
              setActivityProjects(data.projects ?? []);
            })
            .catch(() => undefined);
        }}
      />
    );
  }
  const members = workspace?.snapshot?.members ?? [];
  const projects = countBy(members, "project");
  const visible = project ? members.filter((member) => member.project === project) : members;
  const visibleProjects = countBy(visible, "project");
  const kinds = countBy(visible, "kind");
  const kindCount = (name: string) => kinds.find(([kind]) => kind === name)?.[1] ?? 0;
  const sample = Boolean(workspace?.sample_mode && members.length);
  const stats: [string, string, string][] = sample
    ? [
        [String(visibleProjects.length), "Projects", "snapshot pointer"],
        [String(visible.length), "Members", workspace?.sample_mode_source || "session"],
        [String(kinds.length), "Kinds", "iceberg · kudu · files"],
        [String(kindCount("iceberg")), "Iceberg", "metadata only"],
        [String(kindCount("kudu")), "Kudu", "metadata only"],
        [String(kindCount("files")), "Files", "metadata only"],
      ]
    : [
        ["—", "Projects", "warehouse not contacted"],
        ["—", "Members", "no snapshot"],
        ["—", "Kinds", ""],
        ["—", "Iceberg", ""],
        ["—", "Kudu", ""],
        ["—", "Files", ""],
      ];
  const maxProject = Math.max(1, ...visibleProjects.map(([, n]) => n));
  const maxKind = Math.max(1, ...kinds.map(([, n]) => n));

  return (
    <div className="cog-page">
      <aside className="cog-rail" aria-label="Agent stream">
        <div className="cog-rail-head">
          <span className="cog-kicker">{sample ? `${visible.length} MEMBERS` : "— AGENTS"}</span>
          <label className="cog-sr-only" htmlFor="cog-stream">
            Stream
          </label>
          <select
            id="cog-stream"
            className="cog-select"
            aria-label="Stream"
            value={project}
            onChange={(event) => setProject(event.target.value)}
          >
            <option value="">All projects</option>
            {projects.map(([name, count]) => (
              <option key={name} value={name}>
                {name} · {count}
              </option>
            ))}
          </select>
        </div>
        <ul className="cog-rail-list">
          {visible.length === 0 ? <li className="cog-rail-empty muted">No agents in this window.</li> : null}
          {visible.map((member) => (
            <li className="cog-rail-item" key={`${member.project}/${member.kind}/${member.name}`}>
              <div className="cog-rail-title">{member.name}</div>
              <div className="cog-rail-meta">
                <span className="cog-type">{member.kind.toUpperCase()}</span>
                <span className="muted">{member.project}</span>
              </div>
            </li>
          ))}
        </ul>
        <div className="cog-rail-foot mono muted">
          federation.project=optagent
          {sample ? ` · ${members.length} members · ${projects.length} projects` : ""}
        </div>
      </aside>
      <section className="cog-main">
        <div className="cog-toolbar">
          <label className="cog-toolbar-label">
            Window
            <select
              className="cog-select"
              aria-label="Window"
              value={windowId}
              onChange={(event) => setWindowId(event.target.value)}
            >
              {WINDOWS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn" onClick={onRefresh}>
            Refresh
          </button>
          <span className="muted mono">{sample ? "sample pointer" : "UTC"}</span>
          <span className="cog-live-dot" title="live stream" />
          <span className="pill">{sample ? "sample" : "idle"}</span>
        </div>
        <div className="cog-stats" aria-label="Optimization totals">
          {stats.map(([value, label, sub]) => (
            <div className="landing-stat" key={label}>
              <div className="landing-stat-value">{value}</div>
              <div className="landing-stat-label">{label}</div>
              {sub ? <div className="muted cog-stat-sub">{sub}</div> : null}
            </div>
          ))}
        </div>
        <div className="cog-panel">
          <div className="cog-panel-head">
            <h2>Activity</h2>
            <span className="muted">
              {WINDOWS.find(([value]) => value === windowId)?.[1] ?? "Last year"}
            </span>
          </div>
          <div className="cog-year" role="img" aria-label="Activity heatmap">
            <div className="cog-year-row">
              <div className="cog-year-dows">
                {DOW.map((label, index) => (
                  <span key={index}>{label}</span>
                ))}
              </div>
              <div className="cog-year-weeks">
                {Array.from({ length: 53 }, (_, week) => (
                  <div className="cog-year-col" key={week}>
                    {Array.from({ length: 7 }, (_, day) => (
                      <span className="cog-cell cog-h0" key={day} title="no spans" />
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </div>
          <p className="muted cog-empty">No spans in this window. Impala is not contacted.</p>
        </div>
        <div className="cog-split">
          <div className="cog-panel">
            <div className="cog-panel-head">
              <h3>Contributions</h3>
            </div>
            <div className="cog-contrib" aria-label="Contributions by project and kind">
              <Contrib title="By project" rows={visibleProjects} max={maxProject} />
              <Contrib title="By kind" rows={kinds} max={maxKind} />
            </div>
          </div>
          <div className="cog-panel">
            <div className="cog-panel-head">
              <h2>Top members</h2>
              <span className="muted">kind</span>
            </div>
            <ol className="cog-top">
              {visible.length === 0 ? <li className="muted cog-empty">No members in this window.</li> : null}
              {visible.slice(0, 8).map((member, index) => (
                <li className="cog-top-item" key={`${member.project}/${member.name}`}>
                  <span className="cog-top-n">{index + 1}</span>
                  <span>
                    <div className="cog-top-title">{member.name}</div>
                    <div className="muted cog-top-sub">{member.project}</div>
                  </span>
                  <span className="cog-top-score">{member.kind}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>
    </div>
  );
}

function Contrib({ title, rows, max }: { title: string; rows: [string, number][]; max: number }) {
  return (
    <>
      <div className="cog-contrib-h mono muted">{title.toUpperCase()}</div>
      {rows.length === 0 ? <div className="muted cog-empty">No {title.toLowerCase()} in this window.</div> : null}
      {rows.map(([name, count]) => (
        <div className="cog-contrib-row" key={name}>
          <span className="cog-contrib-name mono">{name}</span>
          <span className="cog-contrib-track">
            <span className="cog-contrib-bar" style={{ width: `${(count / max) * 100}%` }} />
          </span>
          <span className="cog-contrib-n mono muted">{count}</span>
        </div>
      ))}
    </>
  );
}

const SESSION_CATEGORIES = [
  ["chats", "Chats"],
  ["automation", "Automation"],
  ["all", "All"],
] as const;

function RichSentence({ parts }: { parts: { text: string; iri?: string; label?: string }[] }) {
  return (
    <div className="rich-body">
      {parts.map((part, index) =>
        part.iri ? (
          <a key={index} href={part.iri} title={part.label || part.iri}>
            {part.text}
          </a>
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </div>
  );
}

function formatStamp(ms: number): string {
  if (!ms) return "";
  return new Date(ms).toISOString().slice(0, 16).replace("T", " ");
}

function SpanSessions({ doc, onRefresh }: { doc: SessionsDoc; onRefresh: () => void }) {
  const projects = doc.phoenix?.projects ?? [];
  const allSessions = doc.phoenix?.sessions ?? [];
  const [project, setProject] = useState("");
  const [activity, setActivity] = useState("");
  const [windowId, setWindowId] = useState("365d");
  const [query, setQuery] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [traces, setTraces] = useState<ExplorerTrace[]>([]);
  const [traceId, setTraceId] = useState("");
  const [detail, setDetail] = useState<TraceDetail | null>(null);
  const [points, setPoints] = useState<ActivityPoint[]>([]);
  const now = Date.now();
  const earliestPoint = points.reduce((min, point) => Math.min(min, point.t || now), now);
  const earliestSession = allSessions.reduce((min, item) => Math.min(min, item.t0 || now), now);
  const earliest = Math.min(earliestPoint, earliestSession);
  const start = windowId === "all" ? earliest : now - (WINDOW_MS[windowId] ?? WINDOW_MS["365d"]);
  const needle = query.trim().toLowerCase();
  const hits = new Map<string, { count: number; latest: number }>();
  for (const point of points) {
    if (project && point.project !== project) continue;
    if (point.t < start || point.t > now) continue;
    const current = hits.get(point.session) ?? { count: 0, latest: 0 };
    current.count += 1;
    current.latest = Math.max(current.latest, point.t);
    hits.set(point.session, current);
  }
  const activities = [
    ...new Set(
      allSessions
        .filter((item) => hits.has(item.id))
        .map((item) => item.activity)
        .filter(Boolean),
    ),
  ].sort();
  const visible = allSessions.filter((item) => {
    if (!hits.has(item.id)) return false;
    if (activity && item.activity !== activity) return false;
    if (!needle) return true;
    return `${item.name} ${item.id}`.toLowerCase().includes(needle);
  });
  useEffect(() => {
    fetch("/api/optagent/v1/activity")
      .then((response) => response.json())
      .then((data: { points?: ActivityPoint[] }) => setPoints(data.points ?? []))
      .catch(() => setPoints([]));
  }, [doc]);
  useEffect(() => {
    if (!sessionId) {
      setTraces([]);
      setTraceId("");
      return;
    }
    const controller = new AbortController();
    fetch(`/api/optagent/v1/session?id=${encodeURIComponent(sessionId)}`, { signal: controller.signal })
      .then((response) => response.json())
      .then((data: { traces?: ExplorerTrace[] }) => {
        const next = data.traces ?? [];
        setTraces(next);
        setTraceId(next[0]?.trace_id ?? "");
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [sessionId]);
  useEffect(() => {
    if (!traceId) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    fetch(`/api/optagent/v1/trace?id=${encodeURIComponent(traceId)}`, { signal: controller.signal })
      .then((response) => response.json())
      .then((data: TraceDetail) => setDetail(data))
      .catch(() => undefined);
    return () => controller.abort();
  }, [traceId]);
  const inWindow = traces.filter((item) => item.t >= start && item.t <= now);
  const shownTraces = inWindow
    .filter((item) => !needle || item.name.toLowerCase().includes(needle))
    .slice(0, 200);
  useEffect(() => {
    if (!sessionId) return;
    if (points.length && !hits.has(sessionId)) {
      setSessionId("");
      return;
    }
    if (activity && allSessions.some((item) => item.id === sessionId && item.activity !== activity)) {
      setSessionId("");
      return;
    }
    if (inWindow.length && !inWindow.some((item) => item.trace_id === traceId)) {
      setTraceId(inWindow[0].trace_id);
    }
  }, [windowId, sessionId, activity, points, traces, traceId]);
  return (
    <div className="cog-page">
      <aside className="cog-rail" aria-label="Sessions">
        <div className="cog-rail-head">
          <span className="cog-kicker">{visible.length} SESSIONS</span>
          <select
            className="cog-select"
            aria-label="Project"
            value={project}
            onChange={(event) => {
              setProject(event.target.value);
              setActivity("");
              setSessionId("");
            }}
          >
            <option value="">All projects</option>
            {projects.map((name) => (
              <option key={name} value={name}>
                {name} · {points.filter((point) => point.project === name && point.t >= start && point.t <= now).length}
              </option>
            ))}
          </select>
        </div>
        <ul className="cog-rail-list">
          <li>
            <button type="button" className={activity === "" ? "cog-rail-item active" : "cog-rail-item"} onClick={() => setActivity("")}>
              <div className="cog-rail-title">All activity</div>
            </button>
          </li>
          {activities.map((name) => (
            <li key={name}>
              <button type="button" className={activity === name ? "cog-rail-item active" : "cog-rail-item"} onClick={() => setActivity(name)}>
                <div className="cog-rail-title">{name}</div>
                <div className="cog-rail-meta">
                  <span className="cog-type">{name.toUpperCase()}</span>
                  <span className="muted">{allSessions.filter((item) => hits.has(item.id) && item.activity === name).length}</span>
                </div>
              </button>
            </li>
          ))}
          {visible.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className={sessionId === item.id ? "cog-rail-item active" : "cog-rail-item"}
                onClick={() => setSessionId(item.id)}
              >
                <div className="cog-rail-title">{item.name || item.id}</div>
                <div className="cog-rail-meta">
                  <span className="muted">{formatStamp(hits.get(item.id)?.latest || item.t1)}</span>
                  <span className="cog-type">{hits.get(item.id)?.count ?? item.trace_count}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
        <div className="cog-rail-foot mono muted">signals-snapshot · {projects.length} projects</div>
      </aside>
      <section className="cog-main">
        <div className="cog-toolbar">
          <label className="cog-toolbar-label">
            Window
            <select className="cog-select" aria-label="Window" value={windowId} onChange={(event) => setWindowId(event.target.value)}>
              {WINDOWS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <input
            className="ses-search"
            type="search"
            placeholder="Search sessions"
            aria-label="Search sessions"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="button" className="btn" onClick={onRefresh}>Refresh</button>
        </div>
        <div className="cog-split ses-explorer">
          <div className="cog-panel ses-trace-list">
            <div className="cog-panel-head">
              <h2>{sessionId ? "Traces" : "Session"}</h2>
              <span className="muted">
                {sessionId ? `${shownTraces.length} of ${inWindow.length} in this window` : "Choose a session"}
              </span>
            </div>
            {shownTraces.length === 0 ? <p className="muted cog-empty">No trace is open.</p> : null}
            <ul className="cog-rail-list">
              {shownTraces.map((item) => (
                <li key={item.trace_id}>
                  <button
                    type="button"
                    className={traceId === item.trace_id ? "cog-rail-item active" : "cog-rail-item"}
                    onClick={() => setTraceId(item.trace_id)}
                  >
                    <div className="cog-rail-title">{item.name || item.trace_id}</div>
                    <div className="cog-rail-meta">
                      <span className="muted">{formatStamp(item.t)}</span>
                      <span className="cog-type">{item.span_kind}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <article className="sum-panel ses-read">
            <header className="sum-panel-head">
              <h2>{detail?.name || "Trace"}</h2>
              <span className="muted sum-panel-meta">
                {[formatStamp(detail?.t || 0), detail?.span_kind, detail?.activity, detail?.attributes?.["semantica.category"], detail?.attributes?.["semantica.relationship"], detail?.attributes?.["llm.model_name"], detail?.attributes?.["llm.token_count.total"]]
                  .filter((part) => part !== undefined && part !== "")
                  .join(" · ")}
              </span>
            </header>
            <div className="sum-panel-body">
              <h3>Input</h3>
              <div className="rich-body">{detail?.input || "—"}</div>
              <h3>Output</h3>
              {detail?.rich && detail.rich.some((part) => part.iri) ? (
                <RichSentence parts={detail.rich} />
              ) : (
                <div className="rich-body">{detail?.output || "—"}</div>
              )}
            </div>
          </article>
        </div>
      </section>
    </div>
  );
}

function Sessions({ doc, onRefresh }: { doc: SessionsDoc; onRefresh: () => void }) {
  const [tenant, setTenant] = useState("");
  const [profile, setProfile] = useState("");
  const [category, setCategory] = useState<(typeof SESSION_CATEGORIES)[number][0]>("all");
  const [source, setSource] = useState("");
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const tenants = doc.tenants ?? [];
  const profiles = (doc.profiles ?? []).filter((item) => !tenant || item.tenant === tenant);
  const selected = profiles.find((item) => item.name === profile && (!tenant || item.tenant === tenant)) ?? null;
  const needle = query.trim().toLowerCase();
  const rows = (doc.sessions ?? []).filter((item) => {
    if (tenant && item.tenant !== tenant) return false;
    if (selected && (item.profile !== selected.name || item.tenant !== selected.tenant)) return false;
    if (category !== "all" && item.category !== category) return false;
    if (source && item.source !== source) return false;
    if (!needle) return true;
    const haystack = `${item.title} ${item.profile} ${item.tenant} ${item.source} ${item.preview}`.toLowerCase();
    return haystack.includes(needle);
  });
  const sources = [...new Set((doc.sessions ?? []).map((item) => item.source))].sort();
  const stats = doc.stats;
  const cards: [string, string, string][] = [
    [String(stats?.total ?? "—"), "Sessions", "lanes"],
    [String(stats?.active ?? "—"), "Active", "in store"],
    [String(stats?.archived ?? "—"), "Archived", ""],
    [String(stats?.messages ?? "—"), "Messages", "not copied"],
    [String(stats?.profiles ?? "—"), "Profiles", "named + default"],
    [String(stats?.tenants ?? "—"), "Tenants", "federated"],
  ];
  const phoenixSessions = doc.phoenix?.sessions ?? [];
  if (phoenixSessions.length || (doc.phoenix?.projects ?? []).length) {
    return <SpanSessions doc={doc} onRefresh={onRefresh} />;
  }

  return (
    <div className="cog-page">
      <aside className="cog-rail" aria-label="Agent profiles">
        <div className="cog-rail-head">
          <span className="cog-kicker">{profiles.length} PROFILES</span>
          <label className="cog-sr-only" htmlFor="ses-tenant">
            Tenant
          </label>
          <select
            id="ses-tenant"
            className="cog-select"
            aria-label="Tenant"
            value={tenant}
            onChange={(event) => {
              setTenant(event.target.value);
              setProfile("");
              setOpenId(null);
            }}
          >
            <option value="">All tenants</option>
            {tenants.map((item) => (
              <option key={item.id} value={item.id}>
                {item.display_name}
              </option>
            ))}
          </select>
        </div>
        <ul className="cog-rail-list">
          <li>
            <button
              type="button"
              className={profile === "" ? "cog-rail-item active" : "cog-rail-item"}
              onClick={() => setProfile("")}
            >
              <div className="cog-rail-title">All profiles</div>
              <div className="cog-rail-meta">
                <span className="cog-type">SCOPE</span>
                <span className="muted">{tenant || "every tenant"}</span>
              </div>
            </button>
          </li>
          {profiles.map((item) => (
            <li key={`${item.tenant}/${item.name}`}>
              <button
                type="button"
                className={
                  selected?.name === item.name && selected.tenant === item.tenant
                    ? "cog-rail-item active"
                    : "cog-rail-item"
                }
                onClick={() => {
                  setProfile(item.name);
                  if (!tenant) setTenant(item.tenant);
                }}
              >
                <div className="cog-rail-title">{item.display_name}</div>
                <div className="cog-rail-meta">
                  <span className="cog-type">{item.is_default ? "DEFAULT" : item.name}</span>
                  <span className="muted">{item.tenant}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
        <div className="cog-rail-foot mono muted">
          federation.project=optagent · {tenants.length} tenants
        </div>
      </aside>
      <section className="cog-main">
        <div className="cog-toolbar">
          <div className="ses-seg" role="group" aria-label="Session category">
            {SESSION_CATEGORIES.map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={category === value ? "active" : undefined}
                aria-pressed={category === value}
                onClick={() => setCategory(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="cog-toolbar-label">
            Source
            <select
              className="cog-select"
              aria-label="Source"
              value={source}
              onChange={(event) => setSource(event.target.value)}
            >
              <option value="">Any source</option>
              {sources.map((item) => (
                <option key={item} value={item}>
                  {item}
                  {doc.stats?.by_source?.[item] != null ? ` · ${doc.stats.by_source[item]}` : ""}
                </option>
              ))}
            </select>
          </label>
          <input
            className="ses-search"
            type="search"
            placeholder="Search sessions"
            aria-label="Search sessions"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="button" className="btn" onClick={onRefresh}>
            Refresh
          </button>
          <span className="pill">{doc.connected ? "phoenix" : "not connected"}</span>
        </div>
        <p className="muted cog-empty">
          {doc.note || "Arize Phoenix agent tracing. Traces stay in Phoenix and are not copied here."}
        </p>
        <div className="cog-stats" aria-label="Session totals">
          {cards.map(([value, label, sub]) => (
            <div className="landing-stat" key={label}>
              <div className="landing-stat-value">{value}</div>
              <div className="landing-stat-label">{label}</div>
              {sub ? <div className="muted cog-stat-sub">{sub}</div> : null}
            </div>
          ))}
        </div>
        <div className="cog-split">
          <div className="cog-panel">
            <div className="cog-panel-head">
              <h2>Sessions</h2>
              <span className="muted">{rows.length}</span>
            </div>
            {rows.length === 0 ? <p className="muted cog-empty">No sessions in this filter.</p> : null}
            <ol className="cog-top">
              {rows.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={openId === item.id ? "ses-row open" : "ses-row"}
                    onClick={() => setOpenId(openId === item.id ? null : item.id)}
                  >
                    <span className="cog-top-title">{item.title}</span>
                    <span className="muted cog-top-sub">
                      {item.tenant} · {item.profile} · {item.source}
                      {item.is_active ? " · active" : ""}
                    </span>
                    <span className="cog-top-score">{item.category}</span>
                  </button>
                  {openId === item.id ? (
                    <div className="ses-detail">
                      <p>{item.preview}</p>
                      <p className="muted mono">
                        {item.message_count} messages · {item.tool_call_count} tool calls · archived{" "}
                        {item.archived ? "yes" : "no"}
                      </p>
                    </div>
                  ) : null}
                </li>
              ))}
            </ol>
          </div>
          <div className="cog-panel">
            <div className="cog-panel-head">
              <h2>Profile</h2>
              <span className="muted">{selected ? selected.name : "all"}</span>
            </div>
            {selected ? (
              <div className="ses-detail">
                <p className="cog-top-title">{selected.display_name}</p>
                <p className="muted mono">
                  {selected.tenant}/{selected.name}
                  {selected.is_default ? " · default" : ""}
                </p>
                <p>{selected.description}</p>
                <p className="muted">Model {selected.model || "—"}</p>
                {selected["metadata-location"] ? (
                  <p className="muted mono">{selected["metadata-location"]}</p>
                ) : null}
              </div>
            ) : (
              <p className="muted">
                Choose a named profile to read its isolated lane. Each profile keeps its own sessions.
              </p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function LineupSummary({ lineup }: { lineup: LineupDoc }) {
  const [root, setRoot] = useState("current");
  const [windowId, setWindowId] = useState(lineup.tracing.window || "365d");
  const [project, setProject] = useState("");
  const [concept, setConcept] = useState("");
  const [table, setTable] = useState("");
  const [view, setView] = useState<LineupDoc>(lineup);
  useEffect(() => {
    const params = new URLSearchParams({ window: windowId });
    if (project) params.set("project", project);
    fetch(`/api/optagent/v1/summary?${params.toString()}`)
      .then((response) => response.json())
      .then((data: SummaryDoc) => {
        if (data.lineup) setView(data.lineup);
      })
      .catch(() => undefined);
  }, [windowId, project]);
  const tracing = view.tracing.projects.find((item) => item.project === project);
  const term = view.lexicon.find((item) => item.iri === concept);
  const schema = view.schema.find((item) => item.name === table);
  return (
    <div className="sum-page">
      <aside className="sum-rail" aria-label="Summary lineup">
        <div className="sum-group">
          <div className="sum-group-title">ROOTS</div>
          {view.roots.map((item) => (
            <button
              key={item.id}
              type="button"
              className={root === item.id ? "sum-tab active" : "sum-tab"}
              onClick={() => setRoot(item.id)}
            >
              {item.title}
            </button>
          ))}
        </div>
        <div className="sum-group">
          <div className="sum-group-title">LEXICON</div>
          {view.lexicon.slice(0, 12).map((item) => (
            <button
              key={item.iri}
              type="button"
              className={concept === item.iri ? "sum-tab active" : "sum-tab"}
              onClick={() => {
                setConcept(item.iri);
                setRoot("current");
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="sum-group">
          <div className="sum-group-title">SCHEMA</div>
          {view.schema.slice(0, 12).map((item) => (
            <button
              key={item.name}
              type="button"
              className={table === item.name ? "sum-tab active" : "sum-tab"}
              onClick={() => {
                setTable(item.name);
                setRoot("current");
              }}
            >
              {item.name}
            </button>
          ))}
        </div>
        <div className="sum-group">
          <div className="sum-group-title">TRACING</div>
          {view.tracing.projects.map((item) => (
            <button
              key={item.project}
              type="button"
              className={project === item.project ? "sum-tab active" : "sum-tab"}
              onClick={() => setProject(item.project)}
            >
              {item.project}
            </button>
          ))}
        </div>
        <div className="sum-rail-foot muted">
          pin {view.pin.slice(0, 12)}
          {view.checkout ? ` · checkout ${view.checkout.slice(0, 12)}` : ""}
          {view.pin_matches === false ? " · pin differs" : ""}
        </div>
      </aside>
      <section className="sum-trail" aria-label="Lineup">
        {root === "scratch" ? (
          <article className="sum-panel">
            <header className="sum-panel-head"><h2>SCRATCH</h2></header>
            <div className="sum-panel-body">
              {view.roots.find((item) => item.id === "scratch")?.live
                ? "Live trace analysis is connected."
                : "This deployment reads snapshots. Live trace analysis is not connected."}
            </div>
          </article>
        ) : null}
        {root === "archive" ? (
          <article className="sum-panel">
            <header className="sum-panel-head"><h2>ARCHIVE</h2></header>
            <div className="sum-panel-body">
              {(view.roots.find((item) => item.id === "archive")?.entries || []).join("\n") || "No frozen snapshots yet."}
            </div>
          </article>
        ) : null}
        {root === "current" && !view.release_installed ? (
          <article className="sum-panel">
            <header className="sum-panel-head"><h2>CURRENT</h2></header>
            <div className="sum-panel-body">The published SDG release is not installed on this host.</div>
          </article>
        ) : null}
        {term ? (
          <article className="sum-panel">
            <header className="sum-panel-head">
              <h2>{term.label}</h2>
              <span className="muted sum-panel-meta">{term.code}</span>
            </header>
            <div className="sum-panel-body">
              <p>{term.definition}</p>
              <p className="mono">{term.iri}</p>
            </div>
          </article>
        ) : null}
        {schema ? (
          <article className="sum-panel">
            <header className="sum-panel-head"><h2>{schema.name}</h2></header>
            <div className="sum-panel-body mono">{schema.location}</div>
          </article>
        ) : null}
        {tracing ? (
          <article className="sum-panel">
            <header className="sum-panel-head">
              <h2>{tracing.project}</h2>
              <select aria-label="Window" value={windowId} onChange={(event) => setWindowId(event.target.value)}>
                {WINDOWS.map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </header>
            <div className="sum-panel-body">
              <p>{tracing.traces} traces · {tracing.sessions} sessions · {tracing.tokens} tokens · {tracing.grounded} grounded</p>
              <p className="muted">{tracing.augmented} augmented</p>
              <p>Genera {tracing.genera.map((item) => `${item.code} ${item.count}`).join(" · ") || "—"}</p>
              <p>Leaves {tracing.top_iris.map((item) => item.iri.split("#")[1]).join(" · ") || "—"}</p>
              {tracing.latency_ms != null ? <p>Latency {tracing.latency_ms} ms</p> : null}
              {tracing.total_cost != null ? <p>Cost {tracing.total_cost}</p> : null}
              {tracing.errors != null ? <p>Errors {tracing.errors}</p> : null}
            </div>
          </article>
        ) : null}
        {view.sessions.map((session) => (
          <article className="sum-panel" key={session.id}>
            <header className="sum-panel-head">
              <h2>{session.id}</h2>
              <span className="muted">{session.traces} traces</span>
            </header>
            <div className="sum-panel-body">
              {session.items.map((item, index) => (
                <div key={`${item.generated_at}-${index}`}>
                  <p className="muted">
                    generated {formatStamp(item.generated_at)}
                    {item.augmented_at ? ` · augmented ${formatStamp(item.augmented_at)}` : ""}
                  </p>
                  {item.rich.some((part) => part.iri) ? <RichSentence parts={item.rich} /> : <p>{item.output}</p>}
                </div>
              ))}
            </div>
          </article>
        ))}
      </section>
    </div>
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
  if (summary.lineup) {
    return <LineupSummary lineup={summary.lineup} />;
  }
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
  onSnapshot,
}: {
  workspace: Workspace | null;
  busy: boolean;
  mode: ColorMode;
  onTheme: (dark: boolean) => void;
  onBrand: (brandId: string) => void;
  onSample: (enabled: boolean) => void;
  onSnapshot: (file: File) => void;
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
      <section className="settings-card">
        <h2>Snapshot upload</h2>
        <p className="muted">
          Load a signals-snapshot archive. Span records stay readable here when Phoenix is not running.
          {workspace?.loaded_snapshot_id ? ` Loaded ${workspace.loaded_snapshot_id}.` : ""}
        </p>
        <input
          className="ses-search"
          type="file"
          accept=".tar.gz,.tgz,application/gzip"
          aria-label="signals-snapshot archive"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onSnapshot(file);
          }}
        />
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
