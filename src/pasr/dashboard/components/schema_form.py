"""Widgets generated from pydantic models.

Every setting and plugin parameter gets a widget from its type, constraints and description, so
new settings appear in the dashboard without UI code.
"""

from __future__ import annotations

import json
import types
from datetime import time
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin

import annotated_types as at
import streamlit as st
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from pasr.dashboard.state import humanize
from pasr.settings.tiers import field_tier


def is_group(field: FieldInfo) -> bool:
    """A nested model without its own tier (e.g. ``hardware.camera``) is a sub-group."""
    annotation = field.annotation
    return (
        isinstance(annotation, type)
        and issubclass(annotation, BaseModel)
        and field_tier(field) is None
    )


def is_setting(field: FieldInfo) -> bool:
    """Settings and plugin parameters are the fields declared with ``setting(...)``."""
    return field_tier(field) is not None


def has_settings(model: type[BaseModel]) -> bool:
    return any(
        has_settings(f.annotation) if is_group(f) else is_setting(f)  # type: ignore[arg-type]
        for f in model.model_fields.values()
    )


def render_model(model: type[BaseModel], values: dict[str, Any], key: str) -> dict[str, Any]:
    """Render every setting of ``model``; returns ``values`` with the edits applied."""
    result = dict(values)
    for name, field in model.model_fields.items():
        if is_group(field):
            sub_model: type[BaseModel] = field.annotation  # type: ignore[assignment]
            if has_settings(sub_model):
                st.markdown(f"**{humanize(name).capitalize()}**")
                result[name] = render_model(sub_model, values[name], f"{key}.{name}")
        elif is_setting(field) and _renderable(field):
            result[name] = render_field(name, field, values[name], f"{key}.{name}")
    return result


def _renderable(field: FieldInfo) -> bool:
    annotation = field.annotation
    return not (isinstance(annotation, type) and issubclass(annotation, BaseModel))


def _bounds(field: FieldInfo) -> tuple[float | None, float | None]:
    low = high = None
    for item in field.metadata:
        if isinstance(item, at.Ge | at.Gt):
            low = float(item.ge if isinstance(item, at.Ge) else item.gt)  # type: ignore[arg-type]
        elif isinstance(item, at.Le | at.Lt):
            high = float(item.le if isinstance(item, at.Le) else item.lt)  # type: ignore[arg-type]
    return low, high


def render_field(
    name: str, field: FieldInfo, value: Any, key: str, *, label: str | None = None
) -> Any:
    """One widget; ``label`` replaces the one made from ``name``."""
    annotation = field.annotation
    origin, args = get_origin(annotation), get_args(annotation)
    label = label or humanize(name).capitalize()
    help_text = field.description

    if annotation is bool:
        return st.toggle(label, value=bool(value), help=help_text, key=key)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        options = [member.value for member in annotation]
        return st.selectbox(
            label,
            options,
            index=options.index(value),
            format_func=humanize,
            help=help_text,
            key=key,
        )
    if origin is Literal:
        options = list(args)
        return st.selectbox(label, options, index=options.index(value), help=help_text, key=key)
    if annotation in (int, float):
        low, high = _bounds(field)
        if annotation is int:
            return int(
                st.number_input(
                    label,
                    value=int(value),
                    min_value=None if low is None else int(low),
                    max_value=None if high is None else int(high),
                    step=1,
                    help=help_text,
                    key=key,
                )
            )
        step = 0.01 if high is not None and high <= 1 else 0.5
        return float(
            st.number_input(
                label,
                value=float(value),
                min_value=low,
                max_value=high,
                step=step,
                format="%.2f",
                help=help_text,
                key=key,
            )
        )
    if annotation is time:
        picked = st.time_input(
            label, value=time.fromisoformat(value), step=60, help=help_text, key=key
        )
        return picked.isoformat() if picked else value
    if annotation in (str, Path):
        return st.text_input(label, value=str(value), help=help_text, key=key)
    if origin is list and args:
        inner = args[0]
        if isinstance(inner, type) and issubclass(inner, Enum):
            options = [member.value for member in inner]
            return st.multiselect(
                label, options, default=value, format_func=humanize, help=help_text, key=key
            )
        if inner is str:
            text = st.text_area(
                label,
                value="\n".join(value),
                help=f"{help_text or ''} One per line.".strip(),
                key=key,
            )
            return [line.strip() for line in text.splitlines() if line.strip()]
    if origin in (Union, types.UnionType) and type(None) in args:
        text = st.text_input(
            label,
            value="" if value is None else str(value),
            help=f"{help_text or ''} Leave empty for none.".strip(),
            key=key,
        )
        return text.strip() or None
    raw = st.text_input(label, value=json.dumps(value), help=f"{help_text} (JSON)", key=key)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        st.caption(f":red[:material/error: {label}: not valid JSON]")  # beside its field
        return value
