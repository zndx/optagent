# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Deployment posture from config/base.conf.

local keeps the FDW and Postgres. amp speaks Impala HS2 and does not open
the FDW. Cloudera Data Engineering is a flag on the amp posture. This
module does not import an Impala or Spark client.
"""

from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CONF = _REPO / "config" / "base.conf"


@dataclass(frozen=True)
class Runtime:
    posture: str
    engine: str
    database_url: str
    impala_host: str
    impala_port: int
    impala_database: str
    auth: str
    principal: str
    keytab: str
    cde_enabled: bool
    traces_s3_uri: str

    @property
    def direct_impala(self) -> bool:
        return self.engine == "impala"

    @property
    def uses_fdw(self) -> bool:
        return self.engine == "fdw"


def _flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def _text(tree, key: str, default: str = "") -> str:
    value = tree.get(key, default) if tree is not None else default
    if value is None:
        return default
    return str(value)


def load_runtime(path: Path | None = None, *, absorb: bool = True) -> Runtime:
    """Parse HOCON. Optional ${?VAR} lines disappear when the variable is unset."""

    from pyhocon import ConfigFactory

    from optagent.secrets import absorb_secrets

    conf_path = path or _DEFAULT_CONF
    if absorb and path is None:
        absorb_secrets(conf_path.parents[1])
    conf = ConfigFactory.parse_file(str(conf_path))
    posture = _text(conf, "posture", "local")
    if posture not in {"local", "amp"}:
        raise ValueError(f"posture must be local or amp, got {posture!r}")

    fdw = conf.get("fdw", None)
    impala = conf.get("impala", None)
    cde = conf.get("cde", None)
    traces = conf.get("traces", None)
    auth = _text(impala, "auth", "kerberos")
    if posture == "amp" and auth != "kerberos":
        raise ValueError("the amp posture accepts only kerberos")

    if posture == "amp":
        engine = "impala"
        cde_enabled = _flag(cde.get("enabled", False) if cde is not None else False)
    else:
        engine = "fdw"
        cde_enabled = False

    port_raw = impala.get("port", 21050) if impala is not None else 21050
    return Runtime(
        posture=posture,
        engine=engine,
        database_url=_text(fdw, "database_url", "postgres://127.0.0.1:5466/optagent"),
        impala_host=_text(impala, "host", ""),
        impala_port=int(port_raw),
        impala_database=_text(impala, "database", "optagent"),
        auth=auth,
        principal=_text(impala, "principal", ""),
        keytab=_text(impala, "keytab", ""),
        cde_enabled=cde_enabled,
        traces_s3_uri=_text(traces, "s3_uri", ""),
    )
