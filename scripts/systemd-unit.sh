#!/usr/bin/env bash
# Helpers for optagent.service. Only this checkout. Never signals :5455 or RustFS :9010.
: "${ROOT:?systemd-unit.sh: ROOT must be set}"

GRPC_PORT="${OPTAGENT_ENGINE_PORT:-50851}"
UI_PORT="${OPTAGENT_UI_PORT:-9892}"

info() { echo "optagent.service: $*"; }

export_unit_runtime() {
  if [[ -d "/run/user/$(id -u)" ]]; then
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  fi
}

_devenv_lc() {
  export_unit_runtime
  /bin/bash -lc "cd \"$ROOT\" && export PATH=\"/usr/local/bin:\$PATH\" && \
    export NIXPKGS_ALLOW_INSECURE=\"\${NIXPKGS_ALLOW_INSECURE:-1}\" && \
    export XDG_RUNTIME_DIR=\"${XDG_RUNTIME_DIR:-}\" && \
    $*"
}

lattice_up() { _devenv_lc "devenv up -d"; }
lattice_down() { _devenv_lc "devenv processes down || true" || true; }

listener_count() {
  ss -ltn 2>/dev/null | grep -cE ":${GRPC_PORT}\\s" || true
}

status_ok() {
  _devenv_lc "python -m optagent.engine_ready" >/dev/null 2>&1
}

ui_ok() {
  curl -sf --max-time 2 "http://127.0.0.1:${UI_PORT}/health" >/dev/null 2>&1
}
