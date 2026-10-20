# bin

Put the Linux grok executable at `bin/grok`. The application uses that file when `OPTAGENT_GROK_BIN` is unset. The binary is not committed.

Build it on a workstation with `just grok-build`, then copy `.devenv/state/bin/grok` here for an AMP upload. Ghostty's WASM terminal is already in `ui/dist/ghostty`.
