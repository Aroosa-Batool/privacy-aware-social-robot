"""Basic → Advanced tiers for settings and plugin parameters.

Every leaf setting declares a tier so ``pasr config show --level`` can show only what a user
asked to see.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, cast

from pydantic import Field
from pydantic.fields import FieldInfo

Tier = Literal["basic", "advanced"]
TIERS: tuple[Tier, ...] = ("basic", "advanced")


def setting(
    default: Any = None,
    *,
    tier: Tier,
    description: str,
    default_factory: Callable[[], Any] | None = None,
    **constraints: Any,
) -> Any:
    """A pydantic ``Field`` tagged with its tier."""
    extra: dict[str, Any] = {"tier": tier}
    if default_factory is not None:
        return Field(
            default_factory=default_factory,
            description=description,
            json_schema_extra=extra,
            **constraints,
        )
    return Field(default, description=description, json_schema_extra=extra, **constraints)


def field_tier(field: FieldInfo) -> Tier | None:
    extra = field.json_schema_extra
    if isinstance(extra, dict) and extra.get("tier") in TIERS:
        return cast(Tier, extra["tier"])
    return None


def visible(field: FieldInfo, level: Tier) -> bool:
    tier = field_tier(field)
    return tier is not None and TIERS.index(tier) <= TIERS.index(level)
