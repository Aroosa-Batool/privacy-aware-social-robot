"""A visible sign of work while the dashboard waits , starting the robot, captures, scans,
downloads: moving dots and a message, instead of a page that only fades and looks stuck."""

from __future__ import annotations

import contextlib
import html
from collections.abc import Iterator
from typing import Any

import streamlit as st

STYLES = """
<style>
/* Streamlit fades the whole page to a third while a script runs, which looks frozen during the
   longer waits; keep it readable and let the indicator below show the work. */
[data-testid="stElementContainer"][data-stale="true"] { opacity: 1 !important; }

.pasr-working {
  display: flex; align-items: center; gap: 0.9rem; margin: 0.25rem 0;
  padding: 0.8rem 1rem; border-radius: 0.75rem;
  background: rgba(42, 120, 214, 0.08); border: 1px solid rgba(42, 120, 214, 0.3);
}
.pasr-working-dots { display: inline-flex; gap: 0.35rem; flex: none; }
.pasr-working-dots i {
  width: 0.55rem; height: 0.55rem; border-radius: 50%; background: #3987e5;
  animation: pasr-bounce 1.2s ease-in-out infinite;
}
.pasr-working-dots i:nth-child(2) { animation-delay: 0.15s; }
.pasr-working-dots i:nth-child(3) { animation-delay: 0.3s; }
.pasr-working-text { line-height: 1.35; font-weight: 600; }
@keyframes pasr-bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.45; }
  40% { transform: translateY(-0.4rem); opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .pasr-working-dots i { animation: pasr-pulse 1.6s ease-in-out infinite; }
  @keyframes pasr-pulse { 0%, 100% { opacity: 0.45; } 50% { opacity: 1; } }
}
</style>
"""


def install_styles() -> None:
    """Once per run, from the app's entry point (style-only HTML takes no space)."""
    st.html(STYLES)


def markup(message: str) -> str:
    return (
        '<div class="pasr-working" role="status" aria-live="polite">'
        '<span class="pasr-working-dots" aria-hidden="true"><i></i><i></i><i></i></span>'
        f'<span class="pasr-working-text">{html.escape(message)}</span>'
        "</div>"
    )


@contextlib.contextmanager
def working(message: str, *, where: Any = None) -> Iterator[None]:
    """Moving dots and ``message`` while the block runs, in ``where`` (default: the page)."""
    slot = (where or st).empty()
    slot.html(markup(message))
    try:
        yield
    finally:
        slot.empty()
