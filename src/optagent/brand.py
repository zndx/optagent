# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Logo packs for OptAgent. The product name stays OptAgent.

Same contract as Signals and Ægir: Weathership, then Cloudera, then an
empty Custom slot. A chosen pack is deployment-wide. HOCON supplies the
default. A settings write stores the id under the session directory.
"""

import json
import os
from pathlib import Path

PACKS = ("weathership", "cloudera", "custom")
_PUBLIC = Path(__file__).resolve().parents[2] / "ui" / "public" / "brand"


def _config_path() -> Path:
    root = Path(os.environ.get("OPTAGENT_SESSION_DIR", ".devenv/state"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "optagent-ui.json"


def _meta(pack_id: str) -> dict:
    path = _PUBLIC / pack_id / "brand.json"
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
    else:
        loaded = {}
    logo = _PUBLIC / pack_id / str(loaded.get("logo_file") or "logo.svg")
    light = _PUBLIC / pack_id / "logo-on-light.svg"
    favicon = _PUBLIC / pack_id / "favicon.svg"
    has_logo = logo.is_file()
    return {
        "id": pack_id,
        "display_name": loaded.get("display_name") or pack_id.title(),
        "logo_href": f"/brand/{pack_id}/{logo.name}" if has_logo else "",
        "logo_href_light": f"/brand/{pack_id}/logo-on-light.svg" if light.is_file() else "",
        "favicon_href": f"/brand/{pack_id}/favicon.svg" if favicon.is_file() else "",
        "logo_alt": loaded.get("logo_alt") or loaded.get("display_name") or pack_id,
        "has_logo": has_logo,
    }


def list_brands() -> list[dict]:
    return [_meta(pack_id) for pack_id in PACKS]


def stored_brand_id() -> str | None:
    path = _config_path()
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    brand_id = loaded.get("brand_id") if isinstance(loaded, dict) else None
    return str(brand_id) if brand_id in PACKS else None


def active_brand_id(configured: str) -> str:
    stored = stored_brand_id()
    if stored:
        return stored
    if configured in PACKS:
        return configured
    return "weathership"


def save_brand_id(brand_id: str) -> str:
    if brand_id not in PACKS:
        raise ValueError(f"unknown brand pack {brand_id}")
    if brand_id != "custom" and not (_PUBLIC / brand_id / "logo.svg").is_file():
        raise ValueError(f"brand pack {brand_id} has no logo")
    path = _config_path()
    path.write_text(json.dumps({"brand_id": brand_id}) + "\n", encoding="utf-8")
    return brand_id


def brand_view(configured: str) -> dict:
    brand_id = active_brand_id(configured)
    brands = list_brands()
    current = next(item for item in brands if item["id"] == brand_id)
    return {"brand_id": brand_id, "brand": current, "brands": brands}
