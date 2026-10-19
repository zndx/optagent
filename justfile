# Local commands. Run them inside the devenv shell (`direnv allow` or
# `devenv shell`). They call the same scripts the AMP runs in CML.

# Run the runbook and application tests.
test:
    uv run --extra dev pytest

# Write the status snapshot. Same script as the CML prepare job.
prepare:
    uv run python 1_job-prepare-project/job.py

# Serve the application on lattice port 9892. CML sets CDSW_APP_PORT instead.
app:
    uv run python 2_app-serve/app.py

# Build impala_fdw against PostgreSQL 16, then register it on :5466.
impala-fdw-install:
    devenv tasks run impala-fdw:install

# Show the devenv Rust toolchain. grok-build requires 1.94.0.
rustc:
    rustc --version

# Check out the pinned sdg-corpora release. Summary lexicon panels read corpora/.
corpora:
    git submodule update --init corpora

# Build grok from git@github.com:zndx/oss-grok-build.git with this shell's cargo.
# The release binary is xai-grok-pager. The terminal invokes it as grok.
# Set GROK_SRC to build a checkout you already have.
grok-build src="":
    #!/usr/bin/env bash
    set -euo pipefail
    root="${GROK_SRC:-{{src}}}"
    if [[ -z "$root" ]]; then
      root="${DEVENV_ROOT:-$PWD}/.devenv/state/src/oss-grok-build"
    fi
    if [[ ! -f "$root/Cargo.toml" ]]; then
      echo "cloning zndx/oss-grok-build into $root"
      git clone --depth 1 git@github.com:zndx/oss-grok-build.git "$root"
    fi
    have="$(rustc --version)"
    echo "$have"
    case "$have" in
      *"1.94."*) ;;
      *)
        echo "this devenv should provide rustc 1.94.0 (grok-build rust-toolchain.toml)" >&2
        exit 1
        ;;
    esac
    cargo build -p xai-grok-pager-bin --release --manifest-path "$root/Cargo.toml"
    bindir="${DEVENV_ROOT:-$PWD}/.devenv/state/bin"
    install -d "$bindir"
    install -m 0755 "$root/target/release/xai-grok-pager" "$bindir/grok"
    echo "installed $bindir/grok"
