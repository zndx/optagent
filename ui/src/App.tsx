import { Switch } from "@cloudflare/kumo";
import { useEffect, useState } from "react";

type Member = {
  project: string;
  kind: string;
  name: string;
  "metadata-location": string;
};

type Workspace = {
  sample_mode: boolean;
  sample_mode_source: string;
  session_id: string;
  snapshot_s3_uri: string;
  snapshot_endpoint: string;
  traces_s3_uri: string;
  snapshot: {
    "snapshot-id": string;
    "sequence-number": number;
    members: Member[];
  } | null;
};

export default function App() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  function load() {
    setBusy(true);
    fetch("/api/optagent/v1/workspace")
      .then((response) => {
        if (!response.ok) throw new Error(`workspace ${response.status}`);
        return response.json() as Promise<Workspace>;
      })
      .then((data) => {
        setWorkspace(data);
        const first = data.snapshot?.members[0]?.project ?? null;
        setSelected(first);
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

  async function onSampleMode(enabled: boolean) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/optagent/v1/sample-mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      if (!response.ok) throw new Error(`sample-mode ${response.status}`);
      await response.json();
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "sample mode failed");
      setBusy(false);
    }
  }

  const members = workspace?.snapshot?.members ?? [];
  const projects = [...new Set(members.map((member) => member.project))];
  const open = members.filter((member) => member.project === selected);
  const endpoint = workspace?.snapshot_endpoint || "AWS S3";

  return (
    <div className="flex min-h-screen flex-col">
      <header
        className="flex items-center gap-4 border-b px-4 py-3"
        style={{ background: "var(--color-kumo-base)", borderColor: "var(--color-kumo-line)" }}
      >
        <strong style={{ color: "var(--text-color-kumo-strong)" }}>agentsview</strong>
        <span className="text-sm" style={{ color: "var(--text-color-kumo-subtle)" }}>
          Optagent
        </span>
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
          <section
            className="mb-6 rounded-lg border p-4"
            style={{ background: "var(--color-kumo-elevated)", borderColor: "var(--color-kumo-line)" }}
          >
            <Switch
              label="Sample mode"
              labelTooltip="Use the signals-snapshot pointer. Impala is not contacted."
              checked={workspace?.sample_mode ?? false}
              disabled={busy || workspace === null}
              onCheckedChange={(checked) => void onSampleMode(checked)}
            />
            <p className="mt-2 text-sm" style={{ color: "var(--text-color-kumo-subtle)" }}>
              Source {workspace?.sample_mode_source || "hocon"}. Snapshot {workspace?.snapshot_s3_uri}. Endpoint {endpoint}.
            </p>
          </section>
          {workspace?.sample_mode && workspace.snapshot ? (
            <>
              <h1 className="mb-1 text-xl font-semibold" style={{ color: "var(--text-color-kumo-strong)" }}>
                Lineup
              </h1>
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
                    <div className="truncate" style={{ color: "var(--text-color-kumo-subtle)" }}>
                      {member["metadata-location"]}
                    </div>
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
