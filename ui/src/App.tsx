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

type Workspace = {
  sample_mode: boolean;
  sample_mode_source: string;
  session_id: string;
  snapshot_s3_uri: string;
  snapshot_endpoint: string;
  traces_s3_uri: string;
  color_mode: ColorMode;
  brand_id: string;
  brand: Brand;
  brands: Brand[];
  snapshot: {
    "snapshot-id": string;
    "sequence-number": number;
    members: Member[];
  } | null;
};

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
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  function applyWorkspace(data: Workspace) {
    setWorkspace(data);
    setSelected((current) => current ?? data.snapshot?.members[0]?.project ?? null);
    if (data.color_mode === "light" || data.color_mode === "dark") applyColorMode(data.color_mode);
    const logo = data.brand?.favicon_href || data.brand?.logo_href || "";
    applyFavicon(logo);
  }

  function load() {
    setBusy(true);
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
  }

  useEffect(() => {
    load();
  }, []);

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

  const members = workspace?.snapshot?.members ?? [];
  const projects = [...new Set(members.map((member) => member.project))];
  const open = members.filter((member) => member.project === selected);
  const mode = workspace?.color_mode === "light" ? "light" : "dark";
  const logoHref =
    mode === "light" && workspace?.brand.logo_href_light
      ? workspace.brand.logo_href_light
      : workspace?.brand.logo_href;

  return (
    <div className="flex min-h-screen flex-col">
      <header
        className="flex items-center gap-4 border-b px-4 py-3"
        style={{ background: "var(--color-kumo-base)", borderColor: "var(--color-kumo-line)" }}
      >
        {logoHref ? (
          <img src={logoHref} alt={workspace?.brand.logo_alt || "OptAgent"} height={28} />
        ) : null}
        <strong style={{ color: "var(--text-color-kumo-strong)" }}>OptAgent</strong>
      </header>
      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <aside
          className="w-full border-b p-4 md:w-64 md:border-b-0 md:border-r"
          style={{ background: "var(--color-kumo-base)", borderColor: "var(--color-kumo-line)" }}
        >
          <p className="mb-2 text-xs font-semibold" style={{ color: "var(--text-color-kumo-subtle)" }}>
            Sessions
          </p>
          {workspace?.sample_mode ? (
            <button
              type="button"
              className="w-full rounded px-2 py-1 text-left text-sm"
              style={{ background: "var(--color-kumo-fill)", color: "var(--text-color-kumo-strong)" }}
            >
              Sample workspace
            </button>
          ) : (
            <p className="text-sm" style={{ color: "var(--text-color-kumo-subtle)" }}>
              No sessions
            </p>
          )}
        </aside>
        <main className="flex-1 p-6">
          <h1 className="mb-4 text-2xl font-semibold" style={{ color: "var(--text-color-kumo-strong)" }}>
            Settings
          </h1>
          <section
            className="mb-6 rounded-lg border p-4"
            style={{ background: "var(--color-kumo-elevated)", borderColor: "var(--color-kumo-line)" }}
          >
            <h2 className="mb-2 text-lg font-semibold">Theme</h2>
            <p className="mb-3 text-sm" style={{ color: "var(--text-color-kumo-subtle)" }}>
              Keiretsu stays the theme. This switch chooses dark or light for this session.
            </p>
            <Switch
              label="Dark theme"
              checked={mode === "dark"}
              disabled={busy || workspace === null}
              onCheckedChange={(checked) => void post("/api/optagent/v1/theme", { mode: checked ? "dark" : "light" })}
            />
          </section>
          <section
            className="mb-6 rounded-lg border p-4"
            style={{ background: "var(--color-kumo-elevated)", borderColor: "var(--color-kumo-line)" }}
            id="branding"
          >
            <h2 className="mb-2 text-lg font-semibold">Branding</h2>
            <p className="mb-3 text-sm" style={{ color: "var(--text-color-kumo-subtle)" }}>
              Logo pack only. The product name stays OptAgent. Weathership, then Cloudera.
            </p>
            <div className="flex flex-wrap gap-3" role="radiogroup" aria-label="Logo brand pack">
              {(workspace?.brands ?? []).map((brand) => (
                <button
                  key={brand.id}
                  type="button"
                  role="radio"
                  aria-checked={workspace?.brand_id === brand.id}
                  disabled={busy || !brand.has_logo}
                  className="rounded border px-3 py-2 text-left text-sm"
                  style={{
                    borderColor: "var(--color-kumo-line)",
                    background: workspace?.brand_id === brand.id ? "var(--color-kumo-fill)" : "transparent",
                    color: "var(--text-color-kumo-default)",
                  }}
                  onClick={() => void post("/api/optagent/v1/brand", { brand_id: brand.id })}
                >
                  {brand.has_logo ? (
                    <img src={mode === "light" && brand.logo_href_light ? brand.logo_href_light : brand.logo_href} alt={brand.logo_alt} height={24} />
                  ) : (
                    <span>{brand.display_name}</span>
                  )}
                  <span className="mt-1 block" style={{ color: "var(--text-color-kumo-subtle)" }}>{brand.id}</span>
                </button>
              ))}
            </div>
          </section>
          <section
            className="mb-6 rounded-lg border p-4"
            style={{ background: "var(--color-kumo-elevated)", borderColor: "var(--color-kumo-line)" }}
          >
            <Switch
              label="Sample mode"
              labelTooltip="Use the signals-snapshot pointer. Impala is not contacted."
              checked={workspace?.sample_mode ?? false}
              disabled={busy || workspace === null}
              onCheckedChange={(checked) => void post("/api/optagent/v1/sample-mode", { enabled: checked })}
            />
            <p className="mt-2 text-sm" style={{ color: "var(--text-color-kumo-subtle)" }}>
              Source {workspace?.sample_mode_source || "hocon"}. Snapshot {workspace?.snapshot_s3_uri}.
            </p>
          </section>
          {workspace?.sample_mode && workspace.snapshot ? (
            <>
              <h2 className="mb-1 text-xl font-semibold" style={{ color: "var(--text-color-kumo-strong)" }}>
                Lineup
              </h2>
              <p className="mb-4 text-sm" style={{ color: "var(--text-color-kumo-subtle)" }}>
                signals-snapshot {workspace.snapshot["snapshot-id"]}. Sequence {workspace.snapshot["sequence-number"]}. Pointers only.
              </p>
              <div className="mb-4 flex flex-wrap gap-2">
                {projects.map((project) => (
                  <button
                    key={project}
                    type="button"
                    className="rounded border px-2 py-1 text-sm"
                    style={{
                      borderColor: "var(--color-kumo-line)",
                      background: project === selected ? "var(--color-kumo-fill)" : "transparent",
                      color: "var(--text-color-kumo-default)",
                    }}
                    onClick={() => setSelected(project)}
                  >
                    {project}
                  </button>
                ))}
              </div>
              <ul className="space-y-2">
                {open.map((member) => (
                  <li
                    key={`${member.project}:${member.name}`}
                    className="rounded border px-3 py-2 text-sm"
                    style={{ borderColor: "var(--color-kumo-line)" }}
                  >
                    <span className="font-medium">{member.name}</span>
                    <span style={{ color: "var(--text-color-kumo-subtle)" }}> · {member.kind}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p style={{ color: "var(--text-color-kumo-subtle)" }}>No data for this period</p>
          )}
          {error ? (
            <p className="mt-4 text-sm" style={{ color: "var(--color-kumo-danger, #f28881)" }}>
              {error}
            </p>
          ) : null}
        </main>
      </div>
    </div>
  );
}

