# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0
"""Ship a portable signals-snapshot as the versioned trace product.

Enriched term links live on the spans inside the archive. The snapshot id
is the version. A later snapshot is a new object. This module does not
write a second warehouse and does not spawn an ACP agent.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tarfile
from pathlib import Path
from typing import Any, Callable

from optagent.backfill import TAU, readable_segment, span_ms, span_text
from optagent.phoenix_spans import read_jsonl

PRODUCT_ID = "optagent.traces.snapshot"
FLOW_NAME = "Snapshot"
DATA_ROOT = "s3://signals-dataproducts/optagent/snapshots"
SDG_IRI = "https://signals.zndx.org/sdg#"
SPEC_ID = "signals.spec.warehouse_product"

CATALOG = {
    "id": PRODUCT_ID,
    "peer": "optagent",
    "title": "Portable trace snapshot",
    "kind": "snapshot",
    "leaf": "root.platform",
    "spec_id": SPEC_ID,
    "agent_focus": (
        "The portable signals-snapshot is the versioned product. "
        "Enriched term links are attributes on the spans inside that archive. "
        "Quality is the count of readable admitted passages and the short links they carry. "
        "Lineage is this snapshot id, its parent snapshot id, the aperture tau, and the TypeSafe model when one was called. "
        "Delta is this snapshot id against its parent. "
        "A later snapshot is a new object under the same product id. A missing factor is not a score. "
        "Nominal means the archive contains those spans."
    ),
}


def data_uri(snapshot_id: str) -> str:
    return f"{DATA_ROOT}/{snapshot_id}.tar.gz"


def _link(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    iri = str(item.get("iri") or "").strip()
    if not iri.startswith(SDG_IRI):
        return None
    try:
        start, end = int(item.get("start") or 0), int(item.get("end") or 0)
    except (TypeError, ValueError):
        return None
    if end <= start:
        return None
    link = {
        "start": start,
        "end": end,
        "text": str(item.get("text") or ""),
        "iri": iri,
        "label": str(item.get("label") or ""),
    }
    if "confidence" in item:
        try:
            link["confidence"] = float(item["confidence"])
        except (TypeError, ValueError):
            pass
    return link


def project_rows(spans: list[dict], snapshot_id: str) -> tuple[list[dict], int]:
    """Readable admitted passages. Returns rows and the unreadable admission count.

    Offsets and confidences are copied. A passage with no term link stays in
    the product so the baseline shows the miss. Unreadable windows are counted
    and left out of the object.
    """

    rows = []
    unreadable = 0
    for span in spans:
        attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
        if not attributes.get("aegir.genus_code"):
            continue
        text = span_text(span)
        if not readable_segment(text):
            unreadable += 1
            continue
        resource = span.get("resource") if isinstance(span.get("resource"), dict) else {}
        links = []
        for item in attributes.get("sdg.spans") or []:
            link = _link(item)
            if link is not None and text[link["start"] : link["end"]] == link["text"]:
                links.append(link)
        row: dict[str, Any] = {
            "product_id": PRODUCT_ID,
            "snapshot_id": snapshot_id,
            "project": str(resource.get("openinference.project.name") or ""),
            "session_id": str(attributes.get("session.id") or ""),
            "trace_id": str(span.get("trace_id") or ""),
            "generated_at_ms": span_ms(span),
            "genus_code": str(attributes.get("aegir.genus_code") or ""),
            "genus_iri": str(attributes.get("aegir.genus_iri") or ""),
            "genus_label": str(attributes.get("aegir.genus_label") or ""),
            "text": text,
            "links": links,
        }
        if attributes.get("aegir.rel_margin_h") not in (None, ""):
            row["rel_margin_h"] = attributes.get("aegir.rel_margin_h")
        if attributes.get("aegir.tau") not in (None, ""):
            row["tau"] = attributes.get("aegir.tau")
        if attributes.get("overwatch.reason"):
            row["overwatch_reason"] = str(attributes["overwatch.reason"])
        if attributes.get("typesafe.model"):
            row["typesafe_model"] = str(attributes["typesafe.model"])
        for source, target in (
            ("typesafe.input_tokens", "typesafe_input_tokens"),
            ("typesafe.output_tokens", "typesafe_output_tokens"),
        ):
            if source in attributes:
                try:
                    row[target] = int(attributes[source])
                except (TypeError, ValueError):
                    continue
        rows.append(row)
    rows.sort(key=lambda item: (int(item["generated_at_ms"]), item["trace_id"]))
    return rows, unreadable


def build_manifest(rows: list[dict], snapshot_id: str, *, unreadable: int, parent_snapshot_id: str = "") -> dict:
    linked_rows = [row for row in rows if row["links"]]
    overwatch = {row["session_id"] for row in rows if row.get("overwatch_reason")}
    models = sorted({row["typesafe_model"] for row in rows if row.get("typesafe_model")})
    return {
        "product_id": PRODUCT_ID,
        "snapshot_id": snapshot_id,
        "parent_snapshot_id": parent_snapshot_id,
        "rows": len(rows),
        "linked_rows": len(linked_rows),
        "links": sum(len(row["links"]) for row in rows),
        "sessions": len({row["session_id"] for row in rows if row["session_id"]}),
        "overwatch_sessions": len(overwatch),
        "admitted_unreadable": unreadable,
        "tau": TAU,
        "models": models,
    }


def pack_snapshot(snapshot: Path) -> bytes:
    """Gzip tar of the snapshot directory. Enriched spans travel inside it."""

    root = Path(snapshot)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                tar.add(path, arcname=str(path.relative_to(root)))
    return buf.getvalue()


def _git_sha() -> str:
    root = Path(__file__).resolve().parents[2]
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def product_facts(manifest: dict, uri: str, *, code_sha: str = "", endpoint: str = "http://127.0.0.1:9010") -> dict[str, str]:
    """Scalar details facts. Local paths are not facts."""

    version = str(manifest["snapshot_id"])
    parent = str(manifest.get("parent_snapshot_id") or "")
    models = ",".join(manifest.get("models") or []) or "none"
    quality = (
        f"snapshot {version} contains {manifest['rows']} readable admitted passages, "
        f"{manifest['linked_rows']} with term links, {manifest['links']} links, "
        f"{manifest['overwatch_sessions']} overwatch sessions, "
        f"{manifest['admitted_unreadable']} unreadable admissions excluded"
    )
    lineage = (
        f"snapshot {version} parent {parent or 'none'} tau {manifest['tau']} model {models}"
        + (f" code {code_sha}" if code_sha else "")
    )
    delta = f"snapshot {version} parent {parent or 'none'}"
    facts = dict(CATALOG)
    facts.update(
        {
            "maturity": "versioned",
            "snapshot_id": version,
            "parent_snapshot_id": parent,
            "data_uri": uri,
            "latest_data_uri": uri,
            "latest_snapshot_id": version,
            "flow_name": FLOW_NAME,
            "rows": str(manifest["rows"]),
            "linked_rows": str(manifest["linked_rows"]),
            "links": str(manifest["links"]),
            "sessions": str(manifest["sessions"]),
            "overwatch_sessions": str(manifest["overwatch_sessions"]),
            "admitted_unreadable": str(manifest["admitted_unreadable"]),
            "tau": str(manifest["tau"]),
            "models": models,
            "object_store": "rustfs",
            "rustfs_endpoint": endpoint,
            "quality": quality,
            "lineage": lineage,
            "delta": delta,
            "assessment": "nominal",
            "assessment_agent": "optagent",
            "upkeep_nominal": "n/a",
        }
    )
    if code_sha:
        facts["code_sha"] = code_sha
    prefix = f"run.{FLOW_NAME}/{version}"
    for name in ("data_uri", "snapshot_id", "rows", "links", "quality"):
        facts[f"{prefix}.{name}"] = facts[name]
    for value in facts.values():
        text = str(value)
        if text.startswith("/") or text.startswith("file:"):
            raise RuntimeError("product facts must not carry a local path")
    return {key: str(value) for key, value in facts.items()}


def _split_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise RuntimeError(f"product object {uri!r} is not an s3 URI")
    rest = uri[len("s3://") :]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise RuntimeError(f"product object {uri!r} needs a bucket and a key")
    return bucket, key


def put_rustfs(body: bytes, *, endpoint: str, uri: str) -> None:
    """PUT one portable snapshot. Lab RustFS credentials are the documented defaults."""

    if "9010" not in endpoint and "rustfs" not in endpoint.lower():
        raise RuntimeError(f"S3 endpoint {endpoint!r} is not RustFS")
    access = os.environ.get("AWS_ACCESS_KEY_ID") or "rustfsadmin"
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY") or "rustfsadmin"
    bucket, key = _split_uri(uri)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "snapshot.tar.gz"
        path.write_bytes(body)
        proc = subprocess.run(
            [
                "rclone",
                "copyto",
                str(path),
                f":s3:{bucket}/{key}",
                "--s3-provider",
                "Other",
                "--s3-endpoint",
                endpoint,
                "--s3-access-key-id",
                access,
                "--s3-secret-access-key",
                secret,
                "--s3-force-path-style",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip().splitlines()
            tail = detail[-1][:300] if detail else f"exit {proc.returncode}"
            raise RuntimeError(f"RustFS write failed: {tail}")


def _signals_python(root: Path) -> list[str]:
    chosen = os.environ.get("SIGNALS_PYTHON", "").strip()
    if chosen:
        return [chosen]
    venv = root / ".devenv" / "state" / "venv" / "bin" / "python"
    if venv.is_file():
        return [str(venv)]
    return ["uv", "run", "--no-sync", "python"]


def _signals_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["DEVENV_ROOT"] = str(root)
    kdc = root / ".devenv" / "kdc"
    if (kdc / "krb5.conf").is_file():
        env.setdefault("KRB5_CONFIG", str(kdc / "krb5.conf"))
    if (kdc / "krb5cc").exists():
        env.setdefault("KRB5CCNAME", str(kdc / "krb5cc"))
    env.setdefault("IMPALA_HS2_HOST", "tinybox.dev.vista.zndx.org")
    src = str(root / "src")
    env["PYTHONPATH"] = src if not env.get("PYTHONPATH") else src + os.pathsep + env["PYTHONPATH"]
    return env


def review_via_signals(facts: dict[str, str], *, summary: str) -> dict:
    """Record tx, details, and hx through Signals. OptAgent does not open the warehouse."""

    root = Path(os.environ.get("SIGNALS_ROOT") or "/home/rch/local/src/wxs/signals")
    script = (
        "import json, sys\n"
        "from signals.ops.history import review\n"
        "payload = json.load(sys.stdin)\n"
        "ev, path = review(\n"
        "    payload['product_id'],\n"
        "    kind='updated',\n"
        "    summary=payload['summary'],\n"
        "    product=payload['product'],\n"
        "    source='optagent',\n"
        ")\n"
        "print(json.dumps({\n"
        "    'tx_id': ev.get('tx_id') or ev.get('event_id'),\n"
        "    'product_id': ev.get('product_id'),\n"
        "    'assessment': ev.get('assessment'),\n"
        "}))\n"
    )
    payload = {"product_id": PRODUCT_ID, "summary": summary, "product": facts}
    try:
        proc = subprocess.run(
            [*_signals_python(root), "-c", script],
            cwd=str(root),
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
            env=_signals_env(root),
        )
    except OSError as exc:
        raise RuntimeError(f"signals review could not start: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1][:400] if detail else f"exit {proc.returncode}"
        raise RuntimeError(f"signals review failed: {tail}")
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        raise RuntimeError("signals review returned no JSON")
    try:
        recorded = json.loads(line[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("signals review stdout is not JSON") from exc
    _confirm_tx(root, str(recorded.get("tx_id") or ""))
    return recorded


def _confirm_tx(root: Path, tx_id: str) -> None:
    """Impala can report an insert complete when the Kudu range is missing."""

    if not tx_id:
        raise RuntimeError("product review did not return a tx_id")
    script = (
        "import json, sys\n"
        "from signals.ops.warehouse import default_warehouse\n"
        "tx_id = json.load(sys.stdin)['tx_id']\n"
        "wh = default_warehouse()\n"
        "sql = \"SELECT tx_id FROM signals_dataproducts.tx_tier0 WHERE tx_id = '\" + tx_id.replace(\"'\", \"\") + \"'\"\n"
        "rows = wh._execute(sql, fetch=True)\n"
        "print(json.dumps({'rows': len(rows or [])}))\n"
    )
    proc = subprocess.run(
        [*_signals_python(root), "-c", script],
        cwd=str(root),
        input=json.dumps({"tx_id": tx_id}),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
        env=_signals_env(root),
    )
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        tail = detail[-1][:300] if detail else f"exit {proc.returncode}"
        raise RuntimeError(f"could not read back the product tx: {tail}")
    try:
        found = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise RuntimeError("product tx read-back was not JSON") from exc
    if int(found.get("rows") or 0) < 1:
        raise RuntimeError(
            "the product tx was not stored. The Kudu hot tier has no range for this hour"
        )


def stamp_snapshot(snapshot: Path, facts: dict[str, str], tx_id: str) -> None:
    path = snapshot / "signals-snapshot.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    summary = document.setdefault("summary", {})
    summary.pop("product.iteration", None)
    summary["product.id"] = PRODUCT_ID
    summary["product.version"] = str(facts["snapshot_id"])
    summary["product.data_uri"] = facts["data_uri"]
    summary["product.tx_id"] = tx_id
    summary["product.rows"] = str(facts["rows"])
    summary["product.links"] = str(facts["links"])
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def load_snapshot(snapshot: Path) -> tuple[str, list[dict]]:
    document = json.loads((snapshot / "signals-snapshot.json").read_text(encoding="utf-8"))
    snapshot_id = str(document.get("snapshot-id") or "")
    if not snapshot_id:
        raise RuntimeError("snapshot-id is required")
    spans: list[dict] = []
    for path in sorted((snapshot / "projects").glob("*/spans.jsonl")):
        spans.extend(read_jsonl(path))
    return snapshot_id, spans


def publish(
    snapshot: Path,
    *,
    put: Callable[..., None] | None = None,
    review: Callable[..., dict] | None = None,
    endpoint: str | None = None,
    stamp: bool = True,
) -> dict:
    """Upload the portable snapshot and record it. Tests inject put and review.

    ``put`` receives ``(uri, body)``. The body is the gzip tar. Term links
    are already on the spans in that tar.
    """

    root = Path(snapshot)
    document = json.loads((root / "signals-snapshot.json").read_text(encoding="utf-8"))
    snapshot_id, spans = load_snapshot(root)
    parent = str(document.get("parent-snapshot-id") or "")
    rows, unreadable = project_rows(spans, snapshot_id)
    manifest = build_manifest(rows, snapshot_id, unreadable=unreadable, parent_snapshot_id=parent)
    uri = data_uri(snapshot_id)
    endpoint = endpoint or os.environ.get("METAFLOW_S3_ENDPOINT_URL") or "http://127.0.0.1:9010"
    writer = put or (lambda target, body: put_rustfs(body, endpoint=endpoint, uri=target))
    code_sha = _git_sha()
    facts = product_facts(manifest, uri, code_sha=code_sha, endpoint=endpoint)
    if stamp:
        stamp_snapshot(root, facts, "")
    writer(uri, pack_snapshot(root))
    summary = facts["quality"]
    recorded = review(facts, summary) if review is not None else review_via_signals(facts, summary=summary)
    tx_id = str(recorded.get("tx_id") or "")
    if not tx_id:
        raise RuntimeError("product review did not return a tx_id")
    if stamp:
        stamp_snapshot(root, facts, tx_id)
        writer(uri, pack_snapshot(root))
    return {
        "product_id": PRODUCT_ID,
        "snapshot_id": snapshot_id,
        "data_uri": uri,
        "tx_id": tx_id,
        "rows": manifest["rows"],
        "links": manifest["links"],
        "overwatch_sessions": manifest["overwatch_sessions"],
        "assessment": recorded.get("assessment") or facts["assessment"],
    }


def main(argv: list[str] | None = None) -> int:
    import sys

    from optagent.snapshot_store import store_root

    args = list(sys.argv[1:] if argv is None else argv)
    snapshot = Path(args[0]) if args else store_root()
    result = publish(snapshot)
    print(
        f"{result['product_id']} snapshot {result['snapshot_id']} "
        f"tx {result['tx_id']} rows {result['rows']} links {result['links']} "
        f"{result['data_uri']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
