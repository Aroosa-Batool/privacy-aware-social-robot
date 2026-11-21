"""Write every setting (key, default, tier, limits, description) to ``website/data/settings.json``.

The Settings reference page is rendered from that file, so it follows ``settings/schema.py``.
Run it from the repository root after changing a setting:

    uv run python website/tools/export_settings.py
"""

from __future__ import annotations

import json
from datetime import time
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from pasr.settings.schema import Settings
from pasr.settings.tiers import field_tier

OUT = Path(__file__).resolve().parents[1] / "data" / "settings.json"
LIMITS = {
    "ge": "≥",
    "gt": ">",
    "le": "≤",
    "lt": "<",
    "min_length": "min length",
    "max_length": "max length",
}


def plain(value: Any) -> Any:
    """A default as it would be written in YAML."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list | tuple):
        return [plain(v) for v in value]
    return value


def limits(field: FieldInfo) -> list[str]:
    found = []
    for item in field.metadata:
        for name, label in LIMITS.items():
            if (bound := getattr(item, name, None)) is not None:
                found.append(f"{label} {bound}")
    return found


def walk(model: type[BaseModel], instance: BaseModel, prefix: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, field in model.model_fields.items():
        key = f"{prefix}.{name}" if prefix else name
        value = getattr(instance, name)
        tier = field_tier(field)
        if tier is None and isinstance(value, BaseModel):
            rows.extend(walk(type(value), value, key))
            continue
        rows.append(
            {
                "key": key,
                "group": key.split(".")[0],
                "default": plain(value),
                "tier": tier or "advanced",
                "limits": limits(field),
                "description": field.description or "",
            }
        )
    return rows


def main() -> None:
    rows = walk(Settings, Settings(), "")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(rows)} settings → {OUT}")


if __name__ == "__main__":
    main()
