"""Streamlit researcher dashboard. Start it with ``pasr dashboard``."""

from pathlib import Path

ICON = Path(__file__).parent / "assets" / "pasr-icon.png"
"""PASR's icon in the browser tab, drawn in ``pasr-icon.svg`` like the robot by the name in the
header. A PNG, so every browser shows it (Safari ignores an SVG or emoji one)."""
