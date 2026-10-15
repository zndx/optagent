#!/usr/bin/env bash
# Decrypt the AMP baseline (.env.cai.enc) into .env.cai.
#
# No-ops when the ciphertext is absent. A missing sops binary or age key
# prints a warning and leaves the plaintext absent. The local devenv shell
# does not call this script.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env.cai.enc ]]; then
  exit 0
fi

export PATH="${HOME}/.local/bin:${PATH}"
if ! command -v sops >/dev/null 2>&1; then
  echo "bootstrap-secrets: .env.cai.enc is present and sops is not on PATH." >&2
  exit 0
fi

if sops --decrypt --output-type json .env.cai.enc 2>/dev/null \
  | python3 -c '
import json, shlex, sys
data = json.load(sys.stdin)
for key, value in data.items():
    if key == "sops" or key.startswith("sops_"):
        continue
    print(f"{key}={shlex.quote(str(value))}")
' > .env.cai.tmp; then
  mv .env.cai.tmp .env.cai
  echo "bootstrap-secrets: decrypted .env.cai"
else
  rm -f .env.cai.tmp .env.cai
  echo "bootstrap-secrets: could not decrypt .env.cai.enc. Set SOPS_AGE_KEY or SOPS_AGE_KEY_FILE." >&2
fi
