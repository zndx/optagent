#!/usr/bin/env bash
# optagent.service start. signals.target membership hook.
# Brings up this checkout's devenv graph and waits for Engine/Status.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="/usr/local/bin:/usr/bin:/bin:${HOME}/.nix-profile/bin:${PATH:-}"
# shellcheck source=systemd-unit.sh
source "$ROOT/scripts/systemd-unit.sh"

POLL_ITERS="${OPTAGENT_SYSTEMD_POLL_ITERS:-120}"
POLL_SLEEP="${OPTAGENT_SYSTEMD_POLL_SLEEP:-5}"

export_unit_runtime
info "starting devenv graph (engine :${GRPC_PORT}, ui :${UI_PORT})"
if ! lattice_up; then
  info "up reported failure — will still poll"
fi

for i in $(seq 1 "$POLL_ITERS"); do
  if status_ok && ui_ok; then
    info "Engine/Status and UI ready (iter=$i)"
    exit 0
  fi
  if (( i % 6 == 0 )); then
    info "waiting… iter=$i listeners=$(listener_count)"
  fi
  sleep "$POLL_SLEEP"
done

info "timed out waiting for Engine/Status :${GRPC_PORT} and UI :${UI_PORT}" >&2
exit 1
