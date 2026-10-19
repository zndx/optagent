import { Select, Switch } from "@cloudflare/kumo";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

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
type LineupConcept = {
  iri: string;
  code: string;
  label: string;
  definition: string;
  broader?: string[];
  narrower?: string[];
};
type LineupTable = { name: string; location: string; columns?: string[]; refs?: string[] };
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
  overwatch?: number;
};
type LineupSessionItem = {
  name: string;
  output: string;
  rich: { text: string; iri?: string; label?: string }[];
  generated_at: number;
  augmented_at: number | null;
  genus_iri?: string;
  genus_label?: string;
  genus_code?: string;
  overwatch?: string;
};
type TraceStats = {
  traces: number;
  sessions: number;
  tokens: number;
  grounded: number;
  augmented: number;
  latency_ms: number | null;
  total_cost: number | null;
  errors: number | null;
  overwatch?: number;
  top_iris?: { iri: string; count: number }[];
  top_sessions?: { id: string; project: string; traces: number }[];
  undomain?: number;
};
type TimelineDomain = TraceStats & { code: string; iri: string };
type TimelineBin = TraceStats & { start: number; end: number; domains: TimelineDomain[] };
type TimelineDoc = {
  window: string;
  unit: string;
  start: number;
  end: number;
  totals: TraceStats;
  domains: TimelineDomain[];
  bins: TimelineBin[];
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
  timeline?: TimelineDoc;
  ranges?: TimelineBin[];
  sessions: { id: string; traces: number; linked?: number; items: LineupSessionItem[] }[];
  published: string[];
  product?: {
    id: string;
    version: string;
    data_uri: string;
    tx_id?: string;
    rows?: string;
    links?: string;
  };
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
  if (path === "/summary" || path.startsWith("/summary/")) return "/summary";
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

function RichSentence({
  parts,
  onOpen,
  hrefFor,
}: {
  parts: { text: string; iri?: string; label?: string }[];
  onOpen?: (iri: string) => void;
  hrefFor?: (iri: string) => string;
}) {
  return (
    <div className="rich-body">
      {parts.map((part, index) =>
        part.iri ? (
          <a
            key={index}
            href={hrefFor ? hrefFor(part.iri) : `/summary/term/${part.iri.split("#").pop() || ""}`}
            title={part.label || part.iri}
            onClick={(event) => {
              if (!onOpen || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
              event.preventDefault();
              onOpen(part.iri || "");
            }}
          >
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

type TrailStop =
  | { kind: "root"; id: string }
  | { kind: "timeline" }
  | { kind: "trends" }
  | { kind: "bin"; start: number; end: number }
  | { kind: "domain"; code: string; start: number; end: number }
  | { kind: "lexicon"; iri: string }
  | { kind: "schema"; name: string }
  | { kind: "tracing"; project: string }
  | { kind: "session"; id: string; project?: string }
  | { kind: "segment"; project: string; session: string; fragment: string };

const TRAIL_STORAGE = "optagent:summary-trail";
const ROOT_TITLES: Record<string, string> = { archive: "ARCHIVE", current: "CURRENT", scratch: "SCRATCH" };

function trailKey(stop: TrailStop): string {
  if (stop.kind === "root") return `root:${stop.id}`;
  if (stop.kind === "timeline") return "timeline";
  if (stop.kind === "trends") return "trends";
  if (stop.kind === "bin") return `bin:${stop.start}:${stop.end}`;
  if (stop.kind === "domain") return `domain:${stop.code}:${stop.start}:${stop.end}`;
  if (stop.kind === "lexicon") return `lexicon:${stop.iri}`;
  if (stop.kind === "schema") return `schema:${stop.name}`;
  if (stop.kind === "tracing") return `tracing:${stop.project}`;
  if (stop.kind === "segment") return `segment:${stop.project}:${stop.session}:${stop.fragment}`;
  return `session:${stop.project || ""}:${stop.id}`;
}

function isTrailStop(value: unknown): value is TrailStop {
  if (!value || typeof value !== "object") return false;
  const stop = value as TrailStop;
  if (stop.kind === "root") return stop.id === "archive" || stop.id === "current" || stop.id === "scratch";
  if (stop.kind === "timeline" || stop.kind === "trends") return true;
  if (stop.kind === "bin") return Number.isFinite(stop.start) && Number.isFinite(stop.end) && stop.end > stop.start;
  if (stop.kind === "domain") {
    return typeof stop.code === "string" && stop.code.length > 0 && !stop.code.includes("|")
      && Number.isFinite(stop.start) && Number.isFinite(stop.end) && stop.end > stop.start;
  }
  if (stop.kind === "lexicon") return typeof stop.iri === "string" && stop.iri.startsWith("https://signals.zndx.org/sdg#");
  if (stop.kind === "schema") return typeof stop.name === "string" && stop.name.length > 0 && !stop.name.includes("/");
  if (stop.kind === "tracing") return typeof stop.project === "string" && stop.project.length > 0;
  if (stop.kind === "session") {
    return typeof stop.id === "string" && stop.id.length > 0 && (stop.project === undefined || typeof stop.project === "string");
  }
  if (stop.kind === "segment") {
    return stop.project.length > 0 && stop.session.length > 0 && /^[A-Za-z][A-Za-z0-9_]*$/.test(stop.fragment);
  }
  return false;
}

function finitePair(start: string, end: string): { start: number; end: number } | null {
  const left = Number(start);
  const right = Number(end);
  if (!Number.isFinite(left) || !Number.isFinite(right) || right <= left) return null;
  return { start: left, end: right };
}

function stopFromToken(token: string): TrailStop | null {
  if (token === "timeline") return { kind: "timeline" };
  if (token === "trends") return { kind: "trends" };
  if (token.startsWith("bin|")) {
    const pair = finitePair(token.split("|")[1] || "", token.split("|")[2] || "");
    return pair ? { kind: "bin", ...pair } : null;
  }
  if (token.startsWith("domain|")) {
    const parts = token.split("|");
    const pair = finitePair(parts[2] || "", parts[3] || "");
    if (!parts[1] || !pair) return null;
    return { kind: "domain", code: parts[1], ...pair };
  }
  if (token.startsWith("https://signals.zndx.org/sdg#")) return { kind: "lexicon", iri: token };
  if (token.startsWith("schema:")) return { kind: "schema", name: token.slice("schema:".length) };
  if (token.startsWith("segment|")) {
    const parts = token.split("|");
    const project = parts[1] || "";
    const fragment = parts[parts.length - 1] || "";
    const session = parts.slice(2, -1).join("|");
    if (!project || !session || !fragment) return null;
    return { kind: "segment", project, session, fragment };
  }
  if (token.startsWith("session|")) {
    const parts = token.split("|");
    if (!parts[1] || !parts[2]) return null;
    return { kind: "session", project: parts[1], id: parts.slice(2).join("|") };
  }
  if (token.startsWith("session:")) {
    const id = token.slice("session:".length);
    const project = id.split(":")[0] || "";
    return { kind: "session", id, project: LINEUP_PROJECTS.has(project) ? project : undefined };
  }
  if (token.startsWith("tracing:")) return { kind: "tracing", project: token.slice("tracing:".length) };
  return null;
}

function readOpen(): TrailStop | null {
  const token = new URLSearchParams(window.location.search).get("open");
  return token ? stopFromToken(token) : null;
}

function loadStoredTrail(): { root: string; trail: TrailStop[] } | null {
  try {
    const raw = sessionStorage.getItem(TRAIL_STORAGE);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { root?: unknown; trail?: unknown };
    const root = parsed.root === "archive" || parsed.root === "current" || parsed.root === "scratch" ? parsed.root : "current";
    if (!Array.isArray(parsed.trail)) return null;
    const trail = parsed.trail.filter(isTrailStop);
    return trail.length ? { root, trail } : null;
  } catch {
    return null;
  }
}

const LINEUP_PROJECTS = new Set(["gaius", "hermes", "metabase", "semantica"]);

function iriFragment(iri: string): string {
  return iri.split("#").pop() || iri;
}

function sessionLocal(id: string, project: string): string {
  const prefix = `${project}:`;
  return id.startsWith(prefix) ? id.slice(prefix.length) : id;
}

function prettyPart(part: string): string {
  return encodeURIComponent(part).replace(/%3A/gi, ":");
}

function isFragment(part: string): boolean {
  return /^[A-Za-z][A-Za-z0-9_]*$/.test(part);
}

function trailToPath(trail: TrailStop[]): string {
  const parts: string[] = [];
  for (const stop of trail) {
    if (stop.kind === "timeline" || stop.kind === "root") continue;
    if (stop.kind === "trends") {
      parts.push("trends");
    } else if (stop.kind === "tracing") {
      parts.push(stop.project);
    } else if (stop.kind === "session") {
      const project = stop.project || stop.id.split(":")[0] || "";
      if (parts[parts.length - 1] !== project) parts.push(project);
      parts.push(sessionLocal(stop.id, project));
    } else if (stop.kind === "segment") {
      if (parts[parts.length - 1] !== stop.project) parts.push(stop.project);
      parts.push(sessionLocal(stop.session, stop.project));
      parts.push(stop.fragment);
    } else if (stop.kind === "lexicon") {
      parts.push("term", iriFragment(stop.iri));
    } else if (stop.kind === "schema") {
      parts.push("table", stop.name);
    } else if (stop.kind === "bin") {
      parts.push("bin", String(stop.start), String(stop.end));
    } else if (stop.kind === "domain") {
      parts.push("domain", stop.code, String(stop.start), String(stop.end));
    }
  }
  return parts.length ? `/summary/${parts.map(prettyPart).join("/")}` : "/summary";
}

function parseLineupPath(pathname: string): TrailStop[] | null {
  const path = pathname.replace(/\/$/, "") || "/";
  if (path === "/summary") return null;
  if (!path.startsWith("/summary/")) return null;
  const parts = path.slice("/summary/".length).split("/").map((part) => decodeURIComponent(part)).filter(Boolean);
  const trail: TrailStop[] = [{ kind: "timeline" }];
  let index = 0;
  while (index < parts.length) {
    const part = parts[index];
    if (part === "timeline") {
      index += 1;
    } else if (part === "trends") {
      trail.push({ kind: "trends" });
      index += 1;
    } else if (part === "term" && parts[index + 1]) {
      trail.push({ kind: "lexicon", iri: `https://signals.zndx.org/sdg#${parts[index + 1]}` });
      index += 2;
    } else if (part === "table" && parts[index + 1]) {
      trail.push({ kind: "schema", name: parts[index + 1] });
      index += 2;
    } else if (part === "bin") {
      const pair = finitePair(parts[index + 1] || "", parts[index + 2] || "");
      if (!pair) return trail;
      trail.push({ kind: "bin", ...pair });
      index += 3;
    } else if (part === "domain") {
      const code = parts[index + 1] || "";
      const pair = finitePair(parts[index + 2] || "", parts[index + 3] || "");
      if (!code || !pair) return trail;
      trail.push({ kind: "domain", code, ...pair });
      index += 4;
    } else if (LINEUP_PROJECTS.has(part)) {
      const project = part;
      trail.push({ kind: "tracing", project });
      index += 1;
      if (index >= parts.length || parts[index] === "term" || parts[index] === "table") continue;
      const local = parts[index];
      const session = `${project}:${local}`;
      index += 1;
      if (index < parts.length && isFragment(parts[index])) {
        trail.push({ kind: "segment", project, session, fragment: parts[index] });
        index += 1;
      } else {
        trail.push({ kind: "session", project, id: session });
      }
    } else {
      return trail.length > 1 ? trail : null;
    }
  }
  return trail;
}

function projectFromTrail(stops: TrailStop[]): string {
  for (let index = stops.length - 1; index >= 0; index -= 1) {
    const stop = stops[index];
    if (stop.kind === "tracing") return stop.project;
    if (stop.kind === "segment") return stop.project;
    if (stop.kind === "session" && stop.project) return stop.project;
  }
  return "";
}

function initialTrail(): TrailStop[] {
  const parsed = parseLineupPath(window.location.pathname);
  if (parsed) return parsed;
  const opened = readOpen();
  if (opened) return [opened];
  const stored = loadStoredTrail();
  if (
    stored?.trail.length === 1
    && stored.trail[0].kind === "root"
    && stored.trail[0].id === "current"
  ) {
    return [{ kind: "timeline" }];
  }
  if (stored?.trail.length) return stored.trail;
  return [{ kind: "timeline" }];
}

function initialWindow(fallback: string): string {
  const requested = new URLSearchParams(window.location.search).get("w");
  if (requested && WINDOWS.some(([value]) => value === requested)) return requested;
  return fallback;
}

function Follow({ token, label, onOpen }: { token: string; label: string; onOpen: (token: string) => void }) {
  return (
    <a
      href={trailToPath([stopFromToken(token) || { kind: "timeline" }])}
      title={token}
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
        event.preventDefault();
        onOpen(token);
      }}
    >
      {label}
    </a>
  );
}

function conceptLabel(iri: string, byIri: Map<string, LineupConcept>): string {
  return byIri.get(iri)?.label || iri.split("#").pop() || iri;
}

function formatBinLabel(start: number, unit: string): string {
  const iso = new Date(start).toISOString();
  if (unit === "hour" || unit === "6h") return iso.slice(5, 16).replace("T", " ");
  if (unit === "month") return iso.slice(0, 7);
  return iso.slice(0, 10);
}

function formatRange(start: number, end: number): string {
  return `${formatStamp(start)} – ${formatStamp(end)} UTC`;
}

function domainTitle(domain: TimelineDomain, byIri: Map<string, LineupConcept>): string {
  return (domain.iri && byIri.get(domain.iri)?.label) || domain.code;
}

function statRows(row: TraceStats): [string, string][] {
  const rows: [string, string][] = [
    ["traces", String(row.traces)],
    ["sessions", String(row.sessions)],
    ["tokens", String(row.tokens)],
    ["grounded", String(row.grounded)],
    ["augmented", String(row.augmented)],
  ];
  if (row.latency_ms != null) rows.push(["latency", `${row.latency_ms} ms`]);
  if (row.total_cost != null) rows.push(["cost", String(row.total_cost)]);
  if (row.errors != null) rows.push(["errors", String(row.errors)]);
  if (row.undomain) rows.push(["no topic domain", String(row.undomain)]);
  if (row.overwatch) rows.push(["overwatch sessions", String(row.overwatch)]);
  return rows;
}

function PassageFacts({ item, onOpen }: { item: LineupSessionItem; onOpen: (token: string) => void }) {
  const rows: [string, ReactNode][] = [];
  if (item.genus_iri) {
    rows.push([
      "genus",
      <Follow token={item.genus_iri} label={item.genus_label || iriFragment(item.genus_iri)} onOpen={onOpen} />,
    ]);
  } else if (item.genus_label) {
    rows.push(["genus", item.genus_label]);
  }
  if (item.overwatch) rows.push(["overwatch", item.overwatch]);
  if (!rows.length) return null;
  return <PropTable rows={rows} />;
}

function PropTable({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <table className="sum-props">
      <tbody>
        {rows.map(([name, value]) => (
          <tr key={name}>
            <th>{name}</th>
            <td>{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function WindowSelect({ windowId, onWindow }: { windowId: string; onWindow: (windowId: string) => void }) {
  return (
    <select aria-label="Window" value={windowId} onChange={(event) => onWindow(event.target.value)}>
      {WINDOWS.map(([value, label]) => (
        <option key={value} value={value}>{label}</option>
      ))}
    </select>
  );
}

function findRange(view: LineupDoc, start: number, end: number): TimelineBin | undefined {
  const timeline = view.timeline;
  return timeline?.bins.find((bin) => bin.start === start && bin.end === end)
    || view.ranges?.find((bin) => bin.start === start && bin.end === end);
}

function findDomain(view: LineupDoc, code: string, start: number, end: number): TimelineDomain | undefined {
  const timeline = view.timeline;
  if (timeline && start === timeline.start && end === timeline.end) {
    return timeline.domains.find((domain) => domain.code === code);
  }
  return findRange(view, start, end)?.domains.find((domain) => domain.code === code);
}

function trailRanges(trail: TrailStop[]): string {
  const seen = new Set<string>();
  const parts: string[] = [];
  for (const stop of trail) {
    if (stop.kind !== "bin" && stop.kind !== "domain") continue;
    const key = `${stop.start}:${stop.end}`;
    if (seen.has(key)) continue;
    seen.add(key);
    parts.push(key);
  }
  return parts.join(",");
}

function TrailPanels({
  trail,
  view,
  byIri,
  byCode,
  byTable,
  windowId,
  loading,
  onWindow,
  onOpen,
  onClose,
}: {
  trail: TrailStop[];
  view: LineupDoc;
  byIri: Map<string, LineupConcept>;
  byCode: Map<string, LineupConcept>;
  byTable: Map<string, LineupTable>;
  windowId: string;
  loading: boolean;
  onWindow: (windowId: string) => void;
  onOpen: (index: number, token: string) => void;
  onClose: (index: number) => void;
}) {
  return (
    <>
      {trail.map((stop, index) => {
        const closer = trail.length > 1 ? (
          <button type="button" className="sum-panel-close" aria-label="Close panel" onClick={() => onClose(index)}>
            close
          </button>
        ) : null;
        if (stop.kind === "root") {
          const entry = view.roots.find((item) => item.id === stop.id);
          let body = "The published SDG release is installed. An IRI in a trace opens its lexicon panel.";
          if (stop.id === "scratch") {
            body = entry?.live
              ? "Live trace analysis is connected."
              : "This deployment reads snapshots. Live trace analysis is not connected.";
          } else if (stop.id === "archive") {
            body = (entry?.entries || []).join("\n") || "No frozen snapshots yet.";
          } else if (!view.release_installed) {
            body = "The published SDG release is not installed on this host.";
          }
          return (
            <article className="sum-panel" key={`${trailKey(stop)}:${index}`}>
              <header className="sum-panel-head">
                <h2>{ROOT_TITLES[stop.id] || stop.id}</h2>
                {closer}
              </header>
              <div className="sum-panel-body">{body}</div>
            </article>
          );
        }
        if (stop.kind === "timeline" || stop.kind === "trends" || stop.kind === "bin" || stop.kind === "domain") {
          const timeline = view.timeline;
          const windowLabel = WINDOWS.find(([value]) => value === windowId)?.[1] || windowId;
          if (!timeline) {
            return (
              <article className="sum-panel sum-panel-wide" key={`${trailKey(stop)}:${index}`}>
                <header className="sum-panel-head"><h2>Timeline</h2>{closer}</header>
                <div className="sum-panel-body">{loading ? "Loading timeline…" : "This summary has no timeline."}</div>
              </article>
            );
          }
          if (stop.kind === "trends") {
            const maxTraces = Math.max(1, ...timeline.bins.map((bin) => bin.traces));
            const showLatency = timeline.bins.some((bin) => bin.latency_ms != null);
            const showCost = timeline.bins.some((bin) => bin.total_cost != null);
            const showErrors = timeline.bins.some((bin) => bin.errors != null);
            return (
              <article className="sum-panel sum-panel-wide" key={`${trailKey(stop)}:${index}`}>
                <header className="sum-panel-head">
                  <h2>Trends</h2>
                  {closer}
                  <span className="muted sum-panel-meta">{windowLabel} · {timeline.unit} bins</span>
                </header>
                <div className="sum-panel-body">
                  <p><strong>Trends.</strong> {windowLabel}, one row per {timeline.unit} bin.</p>
                  <div className="sum-scroll">
                    <table className="sum-bin-table">
                      <thead>
                        <tr>
                          <th>bin</th>
                          <th>traces</th>
                          <th>tokens</th>
                          <th>grounded</th>
                          {showLatency ? <th>latency</th> : null}
                          {showCost ? <th>cost</th> : null}
                          {showErrors ? <th>errors</th> : null}
                        </tr>
                      </thead>
                      <tbody>
                        {timeline.bins.map((bin) => (
                          <tr key={bin.start}>
                            <td>
                              <Follow token={`bin|${bin.start}|${bin.end}`} label={formatBinLabel(bin.start, timeline.unit)} onOpen={(token) => onOpen(index, token)} />
                            </td>
                            <td>
                              <span className="sum-trend-track" aria-hidden="true">
                                <span className="sum-trend-bar" style={{ width: `${(bin.traces / maxTraces) * 100}%` }} />
                              </span>{" "}
                              {bin.traces}
                            </td>
                            <td>{bin.tokens}</td>
                            <td>{bin.grounded}</td>
                            {showLatency ? <td>{bin.latency_ms ?? "—"}</td> : null}
                            {showCost ? <td>{bin.total_cost ?? "—"}</td> : null}
                            {showErrors ? <td>{bin.errors ?? "—"}</td> : null}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </article>
            );
          }
          if (stop.kind === "bin") {
            const bin = findRange(view, stop.start, stop.end);
            return (
              <article className="sum-panel" key={`${trailKey(stop)}:${index}`}>
                <header className="sum-panel-head">
                  <h2>{formatBinLabel(stop.start, timeline.unit)}</h2>
                  {closer}
                  <span className="muted sum-panel-meta">{formatRange(stop.start, stop.end)}</span>
                </header>
                <div className="sum-panel-body">
                  {bin ? (
                    <>
                      <p><strong>{formatBinLabel(stop.start, timeline.unit)}.</strong> {formatRange(stop.start, stop.end)}.</p>
                      <PropTable rows={statRows(bin)} />
                      <p className="sum-section">Domains.</p>
                      {bin.domains.length ? (
                        <ul className="sum-note-list">
                          {bin.domains.map((domain) => (
                            <li key={domain.code}>
                              <Follow
                                token={`domain|${domain.code}|${bin.start}|${bin.end}`}
                                label={domainTitle(domain, byIri)}
                                onOpen={(token) => onOpen(index, token)}
                              />
                              <span className="muted"> · {domain.traces} traces</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted">No topic domain in this bin.</p>
                      )}
                      {bin.top_iris?.length ? (
                        <>
                          <p className="sum-section">Leaves.</p>
                          <ul className="sum-note-list">
                            {bin.top_iris.map((item) => (
                              <li key={item.iri}>
                                <Follow token={item.iri} label={item.iri.split("#").pop() || item.iri} onOpen={(token) => onOpen(index, token)} />
                                <span className="muted"> · {item.count}</span>
                              </li>
                            ))}
                          </ul>
                        </>
                      ) : null}
                    </>
                  ) : (
                    <p>{loading ? "Loading this bin…" : "No traces in this bin."}</p>
                  )}
                </div>
              </article>
            );
          }
          if (stop.kind === "domain") {
            const domain = findDomain(view, stop.code, stop.start, stop.end);
            const title = domain ? domainTitle(domain, byIri) : stop.code;
            return (
              <article className="sum-panel" key={`${trailKey(stop)}:${index}`}>
                <header className="sum-panel-head">
                  <h2>{title}</h2>
                  {closer}
                  <span className="muted sum-panel-meta">{stop.code} · {formatRange(stop.start, stop.end)}</span>
                </header>
                <div className="sum-panel-body">
                  {domain ? (
                    <>
                      <p><strong>{title}.</strong> Topic domain <span className="mono">{stop.code}</span> in {formatRange(stop.start, stop.end)}.</p>
                      <PropTable
                        rows={[
                          ["code", stop.code],
                          ["iri", domain.iri ? (
                            <Follow token={domain.iri} label={domain.iri.split("#").pop() || domain.iri} onOpen={(token) => onOpen(index, token)} />
                          ) : "—"],
                          ...statRows(domain),
                        ]}
                      />
                      <p className="sum-section">Leaves.</p>
                      {domain.top_iris?.length ? (
                        <ul className="sum-note-list">
                          {domain.top_iris.map((item) => (
                            <li key={item.iri}>
                              <Follow token={item.iri} label={item.iri.split("#").pop() || item.iri} onOpen={(token) => onOpen(index, token)} />
                              <span className="muted"> · {item.count}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted">No leaf IRI in this domain.</p>
                      )}
                      <p className="sum-section">Sessions.</p>
                      {domain.top_sessions?.length ? (
                        <ul className="sum-note-list">
                          {domain.top_sessions.map((session) => (
                            <li key={session.id}>
                              <Follow
                                token={session.project ? `session|${session.project}|${session.id}` : `session:${session.id}`}
                                label={session.id}
                                onOpen={(token) => onOpen(index, token)}
                              />
                              <span className="muted"> · {session.traces} traces</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted">No session in this domain.</p>
                      )}
                    </>
                  ) : (
                    <p>{loading ? "Loading this domain…" : "No traces for this domain in this bin."}</p>
                  )}
                </div>
              </article>
            );
          }
          const maxTraces = Math.max(1, ...timeline.bins.map((bin) => bin.traces));
          return (
            <article className="sum-panel sum-panel-wide" key={`${trailKey(stop)}:${index}`}>
              <header className="sum-panel-head">
                <h2>Timeline</h2>
                {closer}
                <WindowSelect windowId={windowId} onWindow={onWindow} />
                <span className="muted sum-panel-meta">{windowLabel} · {timeline.unit} bins · {formatRange(timeline.start, timeline.end)}</span>
              </header>
              <div className="sum-panel-body">
                <p><strong>Timeline.</strong> {windowLabel}, {timeline.unit} bins, {formatRange(timeline.start, timeline.end)}.</p>
                <PropTable rows={statRows(timeline.totals)} />
                {view.product?.id ? (
                  <>
                    <p className="sum-section">Snapshot.</p>
                    <PropTable
                      rows={[
                        ["product", view.product.id],
                        ["version", view.product.version || ""],
                        ["rows", view.product.rows || ""],
                        ["links", view.product.links || ""],
                        ["data", view.product.data_uri],
                        ...(view.product.tx_id ? [["tx", view.product.tx_id] as [string, string]] : []),
                      ]}
                    />
                  </>
                ) : null}
                <p>
                  <Follow token="trends" label="Trends" onOpen={(token) => onOpen(index, token)} />
                </p>
                <div className="sum-bins" aria-label="Histogram">
                  {timeline.bins.map((bin) => (
                    <button
                      key={bin.start}
                      type="button"
                      className={`sum-bin ${heatLevel(bin.traces, maxTraces)}`}
                      title={`${formatBinLabel(bin.start, timeline.unit)} · ${bin.traces} traces`}
                      onClick={() => onOpen(index, `bin|${bin.start}|${bin.end}`)}
                    />
                  ))}
                </div>
                <p className="sum-section">Bins.</p>
                <div className="sum-scroll">
                  <table className="sum-bin-table">
                    <thead>
                      <tr>
                        <th>bin</th>
                        <th>traces</th>
                        <th>sessions</th>
                        <th>tokens</th>
                        <th>grounded</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...timeline.bins].reverse().map((bin) => (
                        <tr key={bin.start}>
                          <td>
                            <Follow token={`bin|${bin.start}|${bin.end}`} label={formatBinLabel(bin.start, timeline.unit)} onOpen={(token) => onOpen(index, token)} />
                          </td>
                          <td>{bin.traces}</td>
                          <td>{bin.sessions}</td>
                          <td>{bin.tokens}</td>
                          <td>{bin.grounded}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="sum-section">Domains.</p>
                {timeline.domains.length ? (
                  <ul className="sum-note-list">
                    {timeline.domains.map((domain) => (
                      <li key={domain.code}>
                        <Follow
                          token={`domain|${domain.code}|${timeline.start}|${timeline.end}`}
                          label={domainTitle(domain, byIri)}
                          onOpen={(token) => onOpen(index, token)}
                        />
                        <span className="muted"> · {domain.traces} traces</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No topic domain in this window. Open a bin to read that timeframe.</p>
                )}
              </div>
            </article>
          );
        }
        if (stop.kind === "lexicon") {
          const term = byIri.get(stop.iri);
          const local = stop.iri.split("#").pop() || stop.iri;
          return (
            <article className="sum-panel" key={`${trailKey(stop)}:${index}`}>
              <header className="sum-panel-head">
                <h2>{term?.label || local}</h2>
                {closer}
                {term?.code ? <span className="muted sum-panel-meta">{term.code}</span> : null}
              </header>
              <div className="sum-panel-body">
                {term ? (
                  <p><strong>{term.label}.</strong> {term.definition || "No definition in this release."}</p>
                ) : (
                  <p>This term is not in the current release.</p>
                )}
                <PropTable
                  rows={[
                    ...(term?.code ? [["notation", term.code] as [string, ReactNode]] : []),
                    ["iri", <span className="mono" key={stop.iri}>{stop.iri}</span>],
                  ]}
                />
                {term?.broader?.length ? (
                  <>
                    <p className="sum-section">broader.</p>
                    <ul className="sum-note-list">
                      {term.broader.map((iri) => (
                        <li key={iri}>
                          <Follow token={iri} label={conceptLabel(iri, byIri)} onOpen={(token) => onOpen(index, token)} />
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}
                {term?.narrower?.length ? (
                  <>
                    <p className="sum-section">narrower.</p>
                    <ul className="sum-note-list">
                      {term.narrower.map((iri) => (
                        <li key={iri}>
                          <Follow token={iri} label={conceptLabel(iri, byIri)} onOpen={(token) => onOpen(index, token)} />
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}
              </div>
            </article>
          );
        }
        if (stop.kind === "schema") {
          const table = byTable.get(stop.name);
          const inbound = view.schema.filter((item) => (item.refs || []).includes(stop.name)).map((item) => item.name);
          return (
            <article className="sum-panel" key={`${trailKey(stop)}:${index}`}>
              <header className="sum-panel-head">
                <h2>{stop.name}</h2>
                {closer}
              </header>
              <div className="sum-panel-body">
                {table ? (
                  <>
                    <p><strong>{stop.name}.</strong></p>
                    <PropTable rows={[["location", <span className="mono" key={table.location}>{table.location}</span>]]} />
                    {table.columns?.length ? (
                      <>
                        <p className="sum-section">Columns.</p>
                        <ul className="sum-note-list">
                          {table.columns.map((column) => (
                            <li key={column} className="mono">{column}</li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                    <p className="sum-section">References.</p>
                    {table.refs?.length ? (
                      <ul className="sum-note-list">
                        {table.refs.map((name) => (
                          <li key={name}>
                            <Follow token={`schema:${name}`} label={name} onOpen={(token) => onOpen(index, token)} />
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="muted">No foreign key.</p>
                    )}
                    <p className="sum-section">Referenced by.</p>
                    {inbound.length ? (
                      <ul className="sum-note-list">
                        {inbound.map((name) => (
                          <li key={name}>
                            <Follow token={`schema:${name}`} label={name} onOpen={(token) => onOpen(index, token)} />
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="muted">No table references this one.</p>
                    )}
                  </>
                ) : (
                  <p>This table is not in the current release.</p>
                )}
              </div>
            </article>
          );
        }
        if (stop.kind === "tracing") {
          const tracing = view.tracing.projects.find((item) => item.project === stop.project);
          return (
            <article className="sum-panel" key={`${trailKey(stop)}:${index}`}>
              <header className="sum-panel-head">
                <h2>{stop.project}</h2>
                {closer}
                <select aria-label="Window" value={windowId} onChange={(event) => onWindow(event.target.value)}>
                  {WINDOWS.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </header>
              <div className="sum-panel-body">
                {tracing ? (
                  <>
                    <p><strong>{stop.project}.</strong></p>
                    <PropTable
                      rows={[
                        ["traces", String(tracing.traces)],
                        ["sessions", String(tracing.sessions)],
                        ["tokens", String(tracing.tokens)],
                        ["grounded", String(tracing.grounded)],
                        ["augmented", String(tracing.augmented)],
                        ...(tracing.latency_ms != null ? [["latency", `${tracing.latency_ms} ms`] as [string, string]] : []),
                        ...(tracing.total_cost != null ? [["cost", String(tracing.total_cost)] as [string, string]] : []),
                        ...(tracing.errors != null ? [["errors", String(tracing.errors)] as [string, string]] : []),
                        ...(tracing.overwatch ? [["overwatch sessions", String(tracing.overwatch)] as [string, string]] : []),
                      ]}
                    />
                    <p className="sum-section">Domains.</p>
                    {tracing.genera.length ? (
                      <ul className="sum-note-list">
                        {tracing.genera.map((item) => {
                          const term = byCode.get(item.code);
                          return (
                            <li key={item.code}>
                              {term ? (
                                <Follow token={term.iri} label={term.label} onOpen={(token) => onOpen(index, token)} />
                              ) : (
                                <span className="mono">{item.code}</span>
                              )}
                              <span className="muted"> · {item.count} traces</span>
                            </li>
                          );
                        })}
                      </ul>
                    ) : (
                      <p className="muted">No topic domain in this project.</p>
                    )}
                    {tracing.top_iris.length ? (
                      <>
                        <p className="sum-section">Leaves.</p>
                        <ul className="sum-note-list">
                          {tracing.top_iris.map((item) => (
                            <li key={item.iri}>
                              <Follow token={item.iri} label={item.iri.split("#").pop() || item.iri} onOpen={(token) => onOpen(index, token)} />
                              <span className="muted"> · {item.count}</span>
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                  </>
                ) : (
                  <p>{loading ? "Loading traces…" : "No traces in this window."}</p>
                )}
                <p className="sum-section">Sessions.</p>
                {loading && view.sessions.length === 0 ? <p className="muted">Loading sessions…</p> : null}
                {view.sessions.length ? (
                  <ul className="sum-note-list">
                    {view.sessions.map((session) => (
                      <li key={session.id}>
                        <Follow token={`session|${stop.project}|${session.id}`} label={session.id} onOpen={(token) => onOpen(index, token)} />
                        <span className="muted"> · {session.traces} passages · {session.linked || 0} linked</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </article>
          );
        }
        if (stop.kind === "segment") {
          const session = view.sessions.find((item) => item.id === stop.session);
          const term = [...byIri.values()].find((item) => iriFragment(item.iri) === stop.fragment);
          const matches = (session?.items || []).filter((item) =>
            iriFragment(item.genus_iri || "") === stop.fragment ||
            item.rich.some((part) => iriFragment(part.iri || "") === stop.fragment),
          );
          const permalink = trailToPath([
            { kind: "timeline" },
            { kind: "tracing", project: stop.project },
            stop,
          ]);
          return (
            <article className="sum-panel" key={`${trailKey(stop)}:${index}`}>
              <header className="sum-panel-head">
                <h2>{term?.label || stop.fragment}</h2>
                {closer}
                <span className="muted sum-panel-meta">{term?.code || stop.fragment} · {stop.session}</span>
              </header>
              <div className="sum-panel-body">
                <p className="sum-permalink"><a href={permalink}>{permalink}</a></p>
                {matches.length ? matches.map((item, itemIndex) => (
                  <div key={`${item.generated_at}-${itemIndex}`}>
                    <p className="muted">generated {formatStamp(item.generated_at)}</p>
                    <PassageFacts item={item} onOpen={(token) => onOpen(index, token)} />
                    <RichSentence
                      parts={item.rich}
                      hrefFor={(iri) => `/summary/term/${iriFragment(iri)}`}
                      onOpen={(iri) => onOpen(index, iri)}
                    />
                  </div>
                )) : (
                  <p>{loading ? "Loading the segment…" : "This segment has no admitted passage in the snapshot."}</p>
                )}
                {term ? (
                  <p>
                    <Follow token={term.iri} label={term.label} onOpen={(token) => onOpen(index, token)} />
                  </p>
                ) : null}
              </div>
            </article>
          );
        }
        if (stop.kind !== "session") return null;
        const session = view.sessions.find((item) => item.id === stop.id);
        return (
          <article className="sum-panel" key={`${trailKey(stop)}:${index}`}>
            <header className="sum-panel-head">
              <h2>{stop.id}</h2>
              {closer}
              <span className="muted sum-panel-meta">{session ? `${session.traces} passages · ${session.linked || 0} linked` : ""}</span>
            </header>
            <div className="sum-panel-body">
              {session ? session.items.map((item, itemIndex) => (
                <div key={`${item.generated_at}-${itemIndex}`}>
                  <p className="muted">
                    generated {formatStamp(item.generated_at)}
                    {item.augmented_at ? ` · augmented ${formatStamp(item.augmented_at)}` : ""}
                  </p>
                  <PassageFacts item={item} onOpen={(token) => onOpen(index, token)} />
                  {item.rich.some((part) => part.iri) ? (
                    <RichSentence
                      parts={item.rich}
                      hrefFor={(iri) => trailToPath([
                        { kind: "timeline" },
                        { kind: "tracing", project: stop.project || "" },
                        { kind: "segment", project: stop.project || "", session: stop.id, fragment: iriFragment(iri) },
                      ])}
                      onOpen={(iri) => onOpen(index, `segment|${stop.project || ""}|${stop.id}|${iriFragment(iri)}`)}
                    />
                  ) : (
                    <p>{item.output}</p>
                  )}
                </div>
              )) : (
                <p>{loading ? "Loading sessions…" : "This session has no admitted passage in the snapshot."}</p>
              )}
            </div>
          </article>
        );
      })}
    </>
  );
}

function LineupSummary({ lineup }: { lineup: LineupDoc }) {
  const stored = useRef(loadStoredTrail());
  const [root, setRoot] = useState(stored.current?.root || "current");
  const [windowId, setWindowId] = useState(initialWindow(lineup.tracing.window || "365d"));
  const [trail, setTrail] = useState<TrailStop[]>(initialTrail);
  const [project, setProject] = useState(projectFromTrail(initialTrail()));
  const [view, setView] = useState<LineupDoc>(lineup);
  const [loading, setLoading] = useState(false);
  const trailRef = useRef<HTMLElement>(null);
  const prevLen = useRef(trail.length);
  useEffect(() => {
    const params = new URLSearchParams({ window: windowId });
    if (project) params.set("project", project);
    const ranges = trailRanges(trail);
    if (ranges) params.set("ranges", ranges);
    let cancelled = false;
    setLoading(true);
    fetch(`/api/optagent/v1/summary?${params.toString()}`)
      .then((response) => response.json())
      .then((data: SummaryDoc) => {
        if (!cancelled && data.lineup) setView(data.lineup);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [windowId, project, trail]);
  useEffect(() => {
    const wanted = projectFromTrail(trail);
    setProject((current) => (current === wanted ? current : wanted));
  }, [trail]);
  useEffect(() => {
    try {
      sessionStorage.setItem(TRAIL_STORAGE, JSON.stringify({ root, trail }));
    } catch {
      /* sessionStorage unavailable */
    }
    const node = trailRef.current;
    if (node) node.scrollTo({ left: node.scrollWidth });
  }, [trail, root]);
  useEffect(() => {
    const extend = trail.length > prevLen.current;
    prevLen.current = trail.length;
    const path = trailToPath(trail);
    const search = windowId && windowId !== "365d" ? `?w=${encodeURIComponent(windowId)}` : "";
    const next = `${path}${search}`;
    const current = `${window.location.pathname}${window.location.search}`;
    if (next === current) return;
    if (extend) history.pushState(null, "", next);
    else history.replaceState(null, "", next);
  }, [trail, windowId]);
  useEffect(() => {
    const onPop = () => {
      const parsed = parseLineupPath(window.location.pathname);
      const requested = new URLSearchParams(window.location.search).get("w");
      if (requested && WINDOWS.some(([value]) => value === requested)) setWindowId(requested);
      setTrail(parsed ?? [{ kind: "timeline" }]);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const byIri = useMemo(() => new Map(view.lexicon.map((item) => [item.iri, item])), [view.lexicon]);
  const byCode = useMemo(() => {
    const map = new Map<string, LineupConcept>();
    for (const item of view.lexicon) {
      if (item.code && !map.has(item.code)) map.set(item.code, item);
    }
    return map;
  }, [view.lexicon]);
  const byTable = useMemo(() => new Map(view.schema.map((item) => [item.name, item])), [view.schema]);
  const openFrom = (index: number, href: string) => {
    const next = stopFromToken(href) || (byTable.has(href) ? { kind: "schema" as const, name: href } : null);
    if (!next || !isTrailStop(next)) return;
    setTrail((current) => {
      const kept = current.slice(0, index + 1);
      const last = kept[kept.length - 1];
      if (last && trailKey(last) === trailKey(next)) return kept;
      return [...kept, next];
    });
  };
  const seed = trail[0];
  return (
    <div className="sum-page">
      <aside className="sum-rail" aria-label="Summary lineup">
        <div className="sum-group">
          <div className="sum-group-title">SECTION</div>
          <Select
            aria-label="Section"
            size="sm"
            value={root}
            onValueChange={(value) => {
              if (!value) return;
              const id = String(value);
              setRoot(id);
              setTrail(id === "current" ? [{ kind: "timeline" }] : [{ kind: "root", id }]);
            }}
            items={["archive", "current", "scratch"].map((id) => ({
              value: id,
              label: id.charAt(0).toUpperCase() + id.slice(1),
            }))}
          />
        </div>
        <div className="sum-group">
          <div className="sum-group-title">TRACING</div>
          <button
            type="button"
            className={seed?.kind === "timeline" ? "sum-tab active" : "sum-tab"}
            onClick={() => setTrail([{ kind: "timeline" }])}
          >
            Timeline
          </button>
          {view.tracing.projects.map((item) => (
            <button
              key={item.project}
              type="button"
              className={seed?.kind === "tracing" && seed.project === item.project ? "sum-tab active" : "sum-tab"}
              onClick={() => setTrail([{ kind: "tracing", project: item.project }])}
            >
              {item.project}
            </button>
          ))}
        </div>
        <div className="sum-group">
          <div className="sum-group-title">LEXICON</div>
          {view.lexicon.slice(0, 12).map((item) => (
            <button
              key={item.iri}
              type="button"
              className={seed?.kind === "lexicon" && seed.iri === item.iri ? "sum-tab active" : "sum-tab"}
              onClick={() => setTrail([{ kind: "lexicon", iri: item.iri }])}
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
              className={seed?.kind === "schema" && seed.name === item.name ? "sum-tab active" : "sum-tab"}
              onClick={() => setTrail([{ kind: "schema", name: item.name }])}
            >
              {item.name}
            </button>
          ))}
        </div>
        <div className="sum-rail-foot muted">
          pin {view.pin.slice(0, 12)}
          {view.checkout ? ` · checkout ${view.checkout.slice(0, 12)}` : ""}
          {view.pin_matches === false ? " · pin differs" : ""}
        </div>
      </aside>
      <section className="sum-trail" aria-label="Lineup" ref={trailRef}>
        <TrailPanels
          trail={trail}
          view={view}
          byIri={byIri}
          byCode={byCode}
          byTable={byTable}
          windowId={windowId}
          loading={loading}
          onWindow={setWindowId}
          onOpen={openFrom}
          onClose={(index) => setTrail((current) => (current.length > 1 ? current.slice(0, Math.max(1, index)) : current))}
        />
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

type TermSession = { id: string; section: string; status: string; detail: string; created: number };

function terminalStorageKey(section: string): string {
  return `optagent-terminal-session:${section}`;
}

function rememberSession(section: string): string {
  const key = terminalStorageKey(section);
  const stored = localStorage.getItem(key);
  if (stored) return stored;
  const id = crypto.randomUUID();
  localStorage.setItem(key, id);
  return id;
}

function Terminal() {
  const [section, setSection] = useState("current");
  const [sessions, setSessions] = useState<TermSession[]>([]);
  const [active, setActive] = useState("");
  const [status, setStatus] = useState("connecting…");
  const [ask, setAsk] = useState("");
  const [chart, setChart] = useState<number[]>([]);
  const cursor = useRef(0);
  const host = useRef<HTMLDivElement>(null);

  const attach = useCallback((id: string, target: string) => {
    localStorage.setItem(terminalStorageKey(target), id);
    setStatus("connecting…");
    return fetch("/api/optagent/v1/terminal/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section: target, id }),
    })
      .then((response) => response.json())
      .then((row: TermSession & { error?: string }) => {
        if (!row.id) {
          setStatus(row.error || "Could not open a server session");
          return;
        }
        setActive(row.id);
        setStatus(row.detail ? `${row.status} — ${row.detail}` : row.status);
      })
      .catch(() => setStatus("Could not open a server session"));
  }, []);

  const refresh = useCallback(() => {
    fetch(`/api/optagent/v1/terminal/sessions?section=${encodeURIComponent(section)}`)
      .then((response) => response.json())
      .then((data: { sessions?: TermSession[] }) => setSessions(data.sessions || []))
      .catch(() => undefined);
  }, [section]);

  useEffect(() => {
    refresh();
    void attach(rememberSession(section), section);
  }, [refresh, attach, section]);

  useEffect(() => {
    const node = host.current;
    if (!node || !active) return;
    type GhostTerm = { write: (data: string) => void; onData: (cb: (data: string) => void) => void; cols: number; rows: number; loadAddon: (addon: unknown) => void; open: (el: HTMLElement) => void };
    let term: GhostTerm | null = null;
    let timer = 0;
    let stopped = false;
    let observed: ResizeObserver | null = null;
    cursor.current = 0;

    function loadGhostty(): Promise<void> {
      if ((window as Window & { __ghostty?: unknown }).__ghostty) return Promise.resolve();
      return new Promise((resolve) => {
        const script = document.createElement("script");
        script.type = "module";
        script.textContent = [
          "import { Ghostty, Terminal, FitAddon } from '/ghostty/ghostty-web.js';",
          "try {",
          "  const instance = await Ghostty.load('/ghostty/ghostty-vt.wasm');",
          "  window.__ghostty = { Ghostty, Terminal, FitAddon, instance };",
          "} catch (e) { window.__ghosttyError = e; }",
          "window.dispatchEvent(new CustomEvent('ghostty-ready'));",
        ].join("\n");
        window.addEventListener("ghostty-ready", () => resolve(), { once: true });
        document.head.appendChild(script);
      });
    }

    loadGhostty().then(() => {
      const ghost = (window as Window & { __ghostty?: { Terminal: new (opts: object) => GhostTerm; FitAddon: new () => unknown; instance: unknown } }).__ghostty;
      if (!ghost || !node) {
        setStatus("Ghostty assets are not loaded");
        return;
      }
      const created = new ghost.Terminal({
        ghostty: ghost.instance,
        cursorBlink: true,
        fontFamily: 'Menlo, Monaco, "Courier New", ui-monospace, monospace',
        fontSize: 13,
        scrollback: 5000,
        theme: { background: "#0d1117", foreground: "#c9d1d9", cursor: "#58a6ff" },
      });
      const fit = new ghost.FitAddon() as { fit?: () => void };
      created.loadAddon(fit);
      created.open(node);
      term = created;
      const sendSize = () => {
        if (typeof fit.fit === "function") fit.fit();
        fetch(`/api/optagent/v1/terminal/sessions/${active}/resize`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cols: created.cols || 80, rows: created.rows || 24 }),
        }).catch(() => undefined);
      };
      sendSize();
      observed = new ResizeObserver(() => sendSize());
      observed.observe(node);
      created.onData((data) => {
        fetch(`/api/optagent/v1/terminal/sessions/${active}/input`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ data }),
        }).catch(() => undefined);
      });
      const pull = () => {
        if (stopped) return;
        fetch(`/api/optagent/v1/terminal/sessions/${active}/output?cursor=${cursor.current}`)
          .then((response) => response.json())
          .then((frame: { cursor?: number; data?: string; status?: string }) => {
            if (typeof frame.cursor === "number") cursor.current = frame.cursor;
            if (frame.data && term) term.write(frame.data);
            if (frame.status) setStatus(frame.status);
            const points = (frame.data || "").match(/:::optagent-chart\s+(\[[^\]]*\])/);
            if (points) {
              try {
                const parsed = JSON.parse(points[1]) as unknown;
                if (Array.isArray(parsed)) setChart(parsed.filter((item) => typeof item === "number"));
              } catch {
                /* ignore a partial fence */
              }
            }
          })
          .catch(() => undefined)
          .finally(() => {
            timer = window.setTimeout(pull, 250);
          });
      };
      pull();
    });
    return () => {
      stopped = true;
      observed?.disconnect();
      window.clearTimeout(timer);
      node.replaceChildren();
    };
  }, [active]);

  const openSession = () => {
    const id = crypto.randomUUID();
    void attach(id, section).then(() => refresh());
  };

  const askSend = () => {
    if (!active || !ask.trim()) return;
    fetch(`/api/optagent/v1/terminal/sessions/${active}/input`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data: ask.endsWith("\n") ? ask : `${ask}\n` }),
    }).catch(() => undefined);
    setAsk("");
  };

  const max = Math.max(1, ...chart);

  return (
    <div className="term-page">
      <aside className="sum-rail" aria-label="Terminal sessions">
        <div className="sum-group">
          <div className="sum-group-title">SECTION</div>
          <Select
            aria-label="Section"
            size="sm"
            value={section}
            onValueChange={(value) => {
              if (value) setSection(String(value));
            }}
            items={["archive", "current", "scratch"].map((id) => ({
              value: id,
              label: id.charAt(0).toUpperCase() + id.slice(1),
            }))}
          />
        </div>
        <div className="sum-group">
          <div className="sum-group-title">SESSIONS</div>
          <button type="button" className="sum-week-btn" onClick={openSession}>New session</button>
          <ul className="sum-note-list">
            {sessions.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  className="sum-week-btn"
                  onClick={() => {
                    void attach(row.id, section);
                  }}
                >
                  {row.id.slice(0, 8)}
                </button>
                <span className="muted"> {row.status}</span>
              </li>
            ))}
          </ul>
        </div>
      </aside>
      <section className="term-main" aria-label="Terminal execution">
        <p className="muted" style={{ margin: "0.35rem 0.6rem" }}>{status}</p>
        <div id="terminal" ref={host} />
      </section>
      <aside className="term-ask" aria-label="Ask">
        <div className="sum-group">
          <div className="sum-group-title">ASK</div>
          <textarea aria-label="Ask" value={ask} onChange={(event) => setAsk(event.target.value)} />
          <button type="button" className="sum-week-btn" onClick={askSend}>Send</button>
        </div>
        <div className="sum-group">
          <div className="sum-group-title">CHART</div>
          {chart.length ? (
            <div className="term-chart" aria-label="Chart">
              {chart.map((value, index) => (
                <i key={index} style={{ height: `${(value / max) * 100}%` }} />
              ))}
            </div>
          ) : (
            <p className="muted">No chart in this session.</p>
          )}
        </div>
      </aside>
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
