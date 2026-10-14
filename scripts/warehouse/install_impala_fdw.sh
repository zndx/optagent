#!/usr/bin/env bash
# Copy impala_fdw.so into .devenv/pg-ext and register it on optagent Postgres.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SO_SRC="${IMPALA_FDW_SO:-$ROOT/components/impala_fdw/impala_fdw.so}"
EXT_DIR="${IMPALA_FDW_EXT_DIR:-$ROOT/.devenv/pg-ext}"
PGHOST="${OPTAGENT_PGHOST:-127.0.0.1}"
PGPORT="${OPTAGENT_PGPORT:-5466}"
PGDATABASE="${OPTAGENT_PGDATABASE:-optagent}"

if [[ ! -f "$SO_SRC" ]]; then
  echo "impala_fdw.so not found at $SO_SRC" >&2
  echo "Build it with: devenv tasks run impala-fdw:build" >&2
  exit 1
fi
mkdir -p "$EXT_DIR/lib"
tmp="$EXT_DIR/lib/impala_fdw.so.new"
cp -f "$SO_SRC" "$tmp"
mv -f "$tmp" "$EXT_DIR/lib/impala_fdw.so"

ready=0
for _ in $(seq 1 30); do
  if pg_isready -h "$PGHOST" -p "$PGPORT" -d "$PGDATABASE" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then
  echo "Postgres is not accepting connections on $PGHOST:$PGPORT/$PGDATABASE" >&2
  exit 1
fi

export IMPALA_FDW_MODULE="$EXT_DIR/lib/impala_fdw"
PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" python -m optagent.warehouse sql \
  | psql -h "$PGHOST" -p "$PGPORT" -d "$PGDATABASE" -v ON_ERROR_STOP=1
echo "impala_fdw registered on $PGDATABASE ($PGHOST:$PGPORT)"
