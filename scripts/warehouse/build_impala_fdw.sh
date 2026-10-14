#!/usr/bin/env bash
# Build components/impala_fdw against devenv PostgreSQL 16.
# Thrift and Boost are the paths the caller exports (THRIFT_HOME, BOOST_HOME).
# libkudu_client is optional: without it the wrapper still reaches Kudu and
# Iceberg through Impala HS2 (access impala_sql).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/components/impala_fdw"
if [[ ! -f "$SRC/Makefile" ]]; then
  echo "components/impala_fdw is missing. Run: git submodule update --init components/impala_fdw" >&2
  exit 1
fi
: "${THRIFT_HOME:?THRIFT_HOME is required}"
: "${BOOST_HOME:?BOOST_HOME is required}"
: "${PG_DEV:?PG_DEV is required}"
: "${PG_OUT:?PG_OUT is required}"
: "${PG_LIB:?PG_LIB is required}"
: "${CC:?CC is required}"
: "${CXX:?CXX is required}"
MAKE="${MAKE:-make}"

PG_BIN="$ROOT/.devenv/pg-ext/bin"
mkdir -p "$PG_BIN" "$ROOT/.devenv/pg-ext/lib" "$ROOT/.devenv/pg-ext/share"
cat > "$PG_BIN/pg_config" <<EOF
#!/usr/bin/env bash
case "\$1" in
  --version) echo "PostgreSQL 16";;
  --pgxs) echo "$PG_DEV/lib/pgxs/src/makefiles/pgxs.mk";;
  --includedir|--pkgincludedir) echo "$PG_DEV/include";;
  --includedir-server) echo "$PG_DEV/include/server";;
  --libdir) echo "$PG_LIB/lib";;
  --pkglibdir) echo "$ROOT/.devenv/pg-ext/lib";;
  --sharedir) echo "$ROOT/.devenv/pg-ext/share";;
  --bindir) echo "$PG_OUT/bin";;
  --sysconfdir) echo "/etc/postgresql";;
  --mandir|--docdir|--localedir|--htmldir) echo "$ROOT/.devenv/pg-ext/share";;
  --cc) echo "$CC";;
  --cppflags) echo "-I$PG_DEV/include";;
  --cflags) echo "-fPIC -O2";;
  --cflags_sl) echo "-fPIC";;
  --ldflags) echo "-L$PG_LIB/lib";;
  --ldflags_ex|--ldflags_sl) echo "";;
  --libs) echo "";;
  --configure) echo "";;
  *) echo "";;
esac
EOF
chmod +x "$PG_BIN/pg_config"
export PG_CONFIG="$PG_BIN/pg_config"
test -f "$("$PG_CONFIG" --includedir-server)/postgres.h"

KUDU_CLIENT_LIBDIR=""
KUDU_CLIENT_INCDIR=""
IMPALA_FDW_WITH_KUDU=""
if [[ -n "${KUDU_CLIENT_LIBDIR_OVERRIDE:-}" && -n "${KUDU_CLIENT_INCDIR_OVERRIDE:-}" ]]; then
  KUDU_CLIENT_LIBDIR="$KUDU_CLIENT_LIBDIR_OVERRIDE"
  KUDU_CLIENT_INCDIR="$KUDU_CLIENT_INCDIR_OVERRIDE"
  IMPALA_FDW_WITH_KUDU=1
fi

cd "$SRC"
"$MAKE" clean >/dev/null 2>&1 || true
SAFE_CFLAGS="-O2 -fPIC -fno-strict-aliasing -fwrapv -Wall"
EXTRA_INC=""
if [[ -n "${SIG_SASL_INC:-}" ]]; then
  test -f "$SIG_SASL_INC/sasl/sasl.h" || {
    echo "sasl/sasl.h not found under SIG_SASL_INC=$SIG_SASL_INC" >&2
    exit 1
  }
  EXTRA_INC="$EXTRA_INC -I$SIG_SASL_INC"
fi
if [[ -n "${SIG_KRB5_INC:-}" ]]; then
  EXTRA_INC="$EXTRA_INC -I$SIG_KRB5_INC"
fi
if [[ -n "$KUDU_CLIENT_INCDIR" ]]; then
  EXTRA_INC="$EXTRA_INC -I$KUDU_CLIENT_INCDIR"
fi
"$MAKE" with_llvm=no \
  PG_CONFIG="$PG_CONFIG" \
  CC="$CC" \
  CXX="$CXX" \
  CFLAGS="$SAFE_CFLAGS" \
  CXXFLAGS="$SAFE_CFLAGS -std=c++17" \
  THRIFT_HOME="$THRIFT_HOME" \
  BOOST_HOME="$BOOST_HOME" \
  SIG_KRB5_INC="${SIG_KRB5_INC:-}" \
  SIG_KRB5_LIB="${SIG_KRB5_LIB:-}" \
  SIG_SASL_INC="${SIG_SASL_INC:-}" \
  SIG_SASL_LIB="${SIG_SASL_LIB:-}" \
  SIG_SSL_LIB="${SIG_SSL_LIB:-}" \
  KUDU_CLIENT_LIBDIR="$KUDU_CLIENT_LIBDIR" \
  KUDU_CLIENT_INCDIR="$KUDU_CLIENT_INCDIR" \
  IMPALA_FDW_WITH_KUDU="$IMPALA_FDW_WITH_KUDU" \
  PG_CPPFLAGS="-I$BOOST_HOME/include -I$THRIFT_HOME/include -Isrc -Igen-cpp$EXTRA_INC${IMPALA_FDW_WITH_KUDU:+ -DIMPALA_FDW_WITH_KUDU=1}"
test -f "$SRC/impala_fdw.so"
if command -v ldd >/dev/null 2>&1; then
  ldd_out="$(ldd "$SRC/impala_fdw.so")"
  echo "$ldd_out" | grep -q 'libthrift.so.0.2' \
    || { echo "impala_fdw.so is not linked to Nix libthrift" >&2; exit 1; }
  if echo "$ldd_out" | grep -q 'libthrift-0.16'; then
    echo "impala_fdw.so linked Impala-toolchain libthrift 0.16" >&2
    exit 1
  fi
fi
if [[ -n "$IMPALA_FDW_WITH_KUDU" ]]; then
  echo "impala_fdw.so built with libkudu_client"
else
  echo "impala_fdw.so built for HS2 (kudu_scan off; Kudu and Iceberg go through Impala)"
fi
