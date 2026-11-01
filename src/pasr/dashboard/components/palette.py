"""Colours for the dashboard's own HTML, matching ``.streamlit/config.toml`` in light and dark."""

from __future__ import annotations

from typing import Literal

import streamlit as st

LIGHT = {
    "accent": "#2563eb",
    "danger": "#dc2626",
    "danger_hover": "#b91c1c",
    "ok": "#15803d",
    "warn": "#b45309",
    "text": "#31333f",
    "page": "#ffffff",
    "panel": "#ffffff",
    "line": "rgba(49, 51, 63, 0.16)",
    "muted": "rgba(49, 51, 63, 0.62)",
    "disabled": "rgba(49, 51, 63, 0.4)",
    "bar": "#eff6ff",
    "bar_line": "#dbeafe",
    "bar_text": "rgba(49, 51, 63, 0.78)",
}
DARK = {
    "accent": "#3b82f6",
    "danger": "#dc2626",
    "danger_hover": "#ef4444",
    "ok": "#16a34a",
    "warn": "#d97706",
    "text": "#fafafa",
    "page": "#0e1117",
    "panel": "#1a1c24",
    "line": "rgba(250, 250, 250, 0.16)",
    "muted": "rgba(250, 250, 250, 0.62)",
    "disabled": "rgba(250, 250, 250, 0.4)",
    "bar": "#121d33",
    "bar_line": "#1e3a6e",
    "bar_text": "rgba(250, 250, 250, 0.78)",
}


def theme() -> Literal["light", "dark"]:
    """The theme the viewer has on."""
    return "dark" if st.context.theme.type == "dark" else "light"


def colors() -> dict[str, str]:
    """The palette for the theme the viewer has on."""
    return DARK if theme() == "dark" else LIGHT
