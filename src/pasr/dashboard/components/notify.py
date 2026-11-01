"""Messages as toasts in the top-right corner instead of boxes that stay on the page: green when
something is done, yellow for a warning, red for an error, blue for a note. Each has a close
button and fades by itself (warnings and errors stay longer).

Streamlit's toasts all look alike, so a small script marks each one with its kind (read from its
icon) for the styles to colour. Streamlit also drops a toast sent just before ``st.rerun``,
unless it already reached the browser: ``rerun`` keeps this run's toasts and ``flush``, at the
start of the next run, sends them again, and the script hides a copy of a toast already up.
"""

from __future__ import annotations

from typing import Literal, NoReturn

import streamlit as st

from pasr.dashboard.components.palette import theme

Kind = Literal["success", "warning", "error", "info"]
ICONS: dict[Kind, str] = {
    "success": "check_circle",
    "warning": "warning",
    "error": "error",
    "info": "info",
}
SENT = "pasr-toasts-sent"  # this run's toasts
CARRIED = "pasr-toasts-carried"  # toasts to send again after a rerun
SEEN = "pasr-toasts-seen"  # messages shown once per session

# kind: (background, edge and icon) in each theme
TOASTS: dict[str, dict[Kind, tuple[str, str]]] = {
    "light": {
        "success": ("#f0fdf4", "#16a34a"),
        "warning": ("#fffbeb", "#d97706"),
        "error": ("#fef2f2", "#dc2626"),
        "info": ("#eff6ff", "#2563eb"),
    },
    "dark": {
        "success": ("#0f2419", "#22c55e"),
        "warning": ("#2a2110", "#f59e0b"),
        "error": ("#2c1215", "#ef4444"),
        "info": ("#111f3a", "#3b82f6"),
    },
}

SCRIPT = f"""
<script>
(() => {{
  if (window.pasrToasts) return;  // Streamlit may run this again; one watcher is enough
  window.pasrToasts = true;
  const kinds = {{{", ".join(f'"{icon}": "{kind}"' for kind, icon in ICONS.items())}}};
  let queued = false;
  const mark = () => {{
    queued = false;
    const shown = new Set();
    for (const toast of document.querySelectorAll('[data-testid="stToast"]')) {{
      const icon = toast.querySelector('[data-testid="stToastDynamicIcon"]');
      toast.dataset.kind = kinds[icon ? icon.textContent.trim() : ""] || "info";
      if (toast.dataset.copy) continue;
      // A copy of a toast already up (one sent again after a reload, when the first got
      // through after all) stays hidden for good, also once the first one closes.
      const text = toast.querySelector('[data-testid="stToastText"]');
      const words = text ? text.textContent.trim() : "";
      if (shown.has(words)) toast.dataset.copy = "1"; else shown.add(words);
    }}
  }};
  new MutationObserver(() => {{
    if (!queued) {{ queued = true; requestAnimationFrame(mark); }}
  }}).observe(document.body, {{ childList: true, subtree: true }});
  mark();  // toasts already up when this loads
}})();
</script>
"""


def styles() -> str:
    rules = []
    for kind, (background, edge) in TOASTS[theme()].items():
        toast = f'[data-testid="stToast"][data-kind="{kind}"]'
        rules.append(
            f"{toast} {{ background: {background}; border: 1px solid {edge}55; "
            f"border-left: 4px solid {edge}; }}\n"
            f'{toast} [data-testid="stToastDynamicIcon"] {{ color: {edge}; }}'
        )
    close = '[data-testid="stToast"] button[aria-label="Close"]'
    return f"""
<style>
/* bottom right, clear of the header's robot state and buttons at the top right */
[data-testid="stToastContainer"] {{ top: auto; bottom: 1rem; }}
[data-testid="stToast"][data-copy] {{ display: none; }}
{chr(10).join(rules)}
{close} {{
  opacity: 0.8; color: inherit; width: 1.75rem; height: 1.75rem; border-radius: 0.4rem;
}}
{close}:hover {{ opacity: 1; background: rgba(128, 128, 128, 0.18); }}
{close} svg {{ width: 1.1rem; height: 1.1rem; }}
</style>
"""


def install() -> None:
    """Once per run, at the start of the entry point: the toasts' colours and place (style-only
    HTML takes no space)."""
    st.html(styles())


def watch() -> None:
    """Once per run, at the end of the entry point (a script is an element and would leave a
    gap at the top): the script that marks each toast's kind for the colours."""
    st.html(SCRIPT, unsafe_allow_javascript=True)


def notify(message: str, kind: Kind = "info", *, once: bool = False) -> None:
    """A toast of ``kind``; with ``once``, a given message shows only once per session (for a
    state that lasts, such as an unfinished setup, so it is not repeated on every refresh)."""
    if once:
        seen: set[str] = st.session_state.setdefault(SEEN, set())
        if message in seen:
            return
        seen.add(message)
    _toast(message, kind)
    st.session_state.setdefault(SENT, []).append((message, kind))


def rerun() -> NoReturn:
    """``st.rerun``, keeping the toasts sent in this run for the next one."""
    st.session_state[CARRIED] = st.session_state.pop(SENT, [])
    st.rerun()


def flush() -> None:
    """At the start of a run: send again the toasts of a run that ``rerun`` cut short."""
    st.session_state.pop(SENT, None)
    for message, kind in st.session_state.pop(CARRIED, []):
        notify(message, kind)


def _toast(message: str, kind: Kind) -> None:
    st.toast(
        message,
        icon=f":material/{ICONS[kind]}:",
        duration="short" if kind in ("success", "info") else "long",
    )
