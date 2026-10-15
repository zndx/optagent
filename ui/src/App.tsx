import { Switch } from "@cloudflare/kumo";
import { useEffect, useState } from "react";

type Settings = {
  sample_mode: boolean;
  snapshot_s3_uri: string;
  snapshot_endpoint: string;
  traces_s3_uri: string;
};

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/optagent/v1/settings")
      .then((response) => {
        if (!response.ok) throw new Error(`settings ${response.status}`);
        return response.json() as Promise<Settings>;
      })
      .then((data) => {
        setSettings(data);
        setBusy(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "settings unavailable");
        setBusy(false);
      });
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
      setSettings((await response.json()) as Settings);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "sample mode failed");
    } finally {
      setBusy(false);
    }
  }

  const endpoint = settings?.snapshot_endpoint || "AWS S3";

  return (
    <main className="mx-auto flex max-w-xl flex-col gap-6 p-8">
      <header>
        <p className="text-sm" style={{ color: "var(--text-color-kumo-subtle)" }}>
          Optagent
        </p>
        <h1 className="text-2xl font-semibold" style={{ color: "var(--text-color-kumo-strong)" }}>
          Settings
        </h1>
      </header>
      <section
        className="rounded-lg border p-4"
        style={{
          background: "var(--color-kumo-elevated)",
          borderColor: "var(--color-kumo-line)",
        }}
      >
        <Switch
          label="Sample mode"
          labelTooltip="Read the signals-snapshot pointer. The live Impala warehouse is not contacted."
          checked={settings?.sample_mode ?? false}
          disabled={busy || settings === null}
          onCheckedChange={(checked) => void onSampleMode(checked)}
        />
        <p className="mt-3 text-sm" style={{ color: "var(--text-color-kumo-subtle)" }}>
          Workspace snapshot {settings?.snapshot_s3_uri || "not set"}. Endpoint {endpoint}.
        </p>
      </section>
      <p className="text-sm" style={{ color: "var(--text-color-kumo-subtle)" }}>
        Trace archive {settings?.traces_s3_uri || "not set"}. Sample mode does not publish that archive.
      </p>
      {error ? (
        <p className="text-sm" style={{ color: "var(--color-kumo-danger, #f28881)" }}>
          {error}
        </p>
      ) : null}
      <p className="text-sm">
        <a href="/" style={{ color: "var(--text-color-kumo-link)" }}>
          Back to sessions
        </a>
      </p>
    </main>
  );
}
