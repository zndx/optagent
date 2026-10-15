#!/usr/bin/env bash
# optagent.service stop. This checkout only. Does not stop signals.target siblings.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="/usr/local/bin:/usr/bin:/bin:${HOME}/.nix-profile/bin:${PATH:-}"
# shellcheck source=systemd-unit.sh
source "$ROOT/scripts/systemd-unit.sh"

export_unit_runtime
info "stopping devenv graph"
lattice_down

for _ in $(seq 1 30); do
  if [[ "$(listener_count)" -eq 0 ]]; then
    info "engine port :${GRPC_PORT} free"
    exit 0
  fi
  sleep 1
done

info "engine port :${GRPC_PORT} still held" >&2
exit 1
