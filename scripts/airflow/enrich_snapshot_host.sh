#!/usr/bin/env bash
# Host-side body of the Airflow KubernetesPodOperator.
# The pod enters this mount and network namespace so the SDG aperture can
# use the local Qdrant and GPU. The key stays in ~/local/.env.
#
# Signals at ~/local/src/wxs/signals is the only required sibling.
# Aperture admission is optional: export AEGIR_ROOT to an Aegir checkout
# and, when that tree's interpreter is required, AEGIR_PYTHON. Neither is
# given a default path.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPT="${OPTAGENT_ROOT:-$(cd "$HERE/../.." && pwd)}"
if [[ -n "${SIGNALS_ROOT:-}" ]]; then
  SIGNALS="$SIGNALS_ROOT"
elif [[ -n "${HOME:-}" && -d "${HOME}/local/src/wxs/signals/src" ]]; then
  SIGNALS="${HOME}/local/src/wxs/signals"
else
  SIGNALS=""
  for candidate in /home/*/local/src/wxs/signals; do
    if [[ -d "$candidate/src" ]]; then
      SIGNALS="$candidate"
      break
    fi
  done
  if [[ -z "$SIGNALS" ]]; then
    SIGNALS="${HOME:-}/local/src/wxs/signals"
  fi
fi
if [[ -n "${AEGIR_PYTHON:-}" && -x "${AEGIR_PYTHON}" ]]; then
  PY="$AEGIR_PYTHON"
elif [[ -x "$OPT/.devenv/state/venv/bin/python" ]]; then
  PY="$OPT/.devenv/state/venv/bin/python"
else
  PY="${PYTHON:-python3}"
fi
export OPTAGENT_ROOT="$OPT"
export SIGNALS_ROOT="$SIGNALS"
export OPTAGENT_SESSION_DIR="${OPTAGENT_SESSION_DIR:-$OPT/.devenv/state}"
if [[ "$(id -u)" -eq 0 ]]; then
  export KRB5CCNAME="${KRB5CCNAME_ROOT:-/tmp/optagent-krb5cc}"
fi
export PYTHONPATH="${OPT}/src${PYTHONPATH:+:$PYTHONPATH}"
if [[ -n "${AEGIR_ROOT:-}" && -d "${AEGIR_ROOT}/src" ]]; then
  export PYTHONPATH="${AEGIR_ROOT}/src:${PYTHONPATH}"
fi
export SIGNALS_PYTHON="${SIGNALS_PYTHON:-$PY}"
export KRB5CCNAME="${KRB5CCNAME:-$SIGNALS/.devenv/kdc/krb5cc}"
export KRB5_CONFIG="${KRB5_CONFIG:-$SIGNALS/.devenv/kdc/krb5.conf}"
export IMPALA_HS2_HOST="${IMPALA_HS2_HOST:-tinybox.dev.vista.zndx.org}"
export METAFLOW_S3_ENDPOINT_URL="${METAFLOW_S3_ENDPOINT_URL:-http://127.0.0.1:9010}"

if [[ ! -d "$SIGNALS/src" ]]; then
  echo "Signals is required at $SIGNALS (set SIGNALS_ROOT). Federated peers are not." >&2
  exit 1
fi

if [[ -x "$SIGNALS/scripts/signals_kerberos.sh" ]]; then
  # Refresh the lab ticket when the cache is stale. Do not print it.
  env -u DEVENV_ROOT bash -lc "cd '$SIGNALS' && . scripts/signals_kerberos.sh && signals_krb_kinit" || true
fi

exec "$PY" - << 'PY'
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from optagent.backfill import run
from optagent.classify import classify_snapshot
from optagent.enriched import pack_snapshot, publish
from optagent.snapshot_cache import warm_snapshot_caches
from optagent.snapshot_store import install_archive

opt = Path(os.environ["OPTAGENT_ROOT"])
src = Path(os.environ.get("SNAPSHOT_SRC", str(opt / ".devenv/state/signals-snapshot")))
dest = Path(os.environ["SNAPSHOT_DEST"]) if os.environ.get("SNAPSHOT_DEST") else None
if dest is None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raid = Path("/raid/build/optagent/signals-snapshot")
    dest = (raid if raid.is_dir() else opt / "build" / "signals-snapshot") / stamp
    if dest.exists():
        raise SystemExit(f"refusing to reuse {dest}")
    import shutil
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".*"))
print(f"snapshot {dest}", flush=True)
admitted = run(dest, since="", until="", readable_only=True)
print({"admit": admitted}, flush=True)
classified = classify_snapshot(dest, since="", until="")
print({"classify": classified}, flush=True)
document_path = dest / "signals-snapshot.json"
document = json.loads(document_path.read_text(encoding="utf-8"))
previous = str(document.get("snapshot-id") or "")
document["parent-snapshot-id"] = previous
document["snapshot-id"] = str(uuid.uuid4())
document["sequence-number"] = int(document.get("sequence-number") or 0) + 1
document_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
shipped = publish(dest)
print({"publish": shipped}, flush=True)
installed = install_archive(pack_snapshot(dest))
warm_snapshot_caches()
print({"installed": installed.get("snapshot-id"), "parent": previous}, flush=True)
PY
