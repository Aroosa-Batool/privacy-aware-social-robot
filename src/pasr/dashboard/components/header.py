"""The bar across the top of every page, filled light blue from edge to edge and from the very
top: the name, the menu, and the robot's state with its buttons, so whether the robot runs is
visible from anywhere."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import quote

import streamlit as st
from streamlit.navigation.page import StreamlitPage

from pasr.dashboard import ICON
from pasr.dashboard.components import robot
from pasr.dashboard.components.menu import HERE, LABEL_HEIGHT, MENU, Section, buttons, top_menu
from pasr.dashboard.components.page import SIDES
from pasr.dashboard.components.palette import colors

HEADER = "pasr-header"
BRAND = "pasr-brand"
DRAWING = ICON.with_suffix(".svg").read_text()
# rem. The bar's top band is Streamlit's own strip, with its ⋮ menu; the name, menu and robot
# buttons sit in a row below it, clear of it.
TOP = 2.5
BOTTOM = 0.75
DROP = 0.3
"""rem: the menu sits this much lower than the middle of the row, level with the name under
the robot rather than above it."""
ONE_ROW = 75
"""rem: the narrowest window whose bar holds the name, the menu, the robot's buttons and
Streamlit's ⋮ in one row; a narrower one wraps them, as on a phone."""


def logo() -> str:
    """The robot of the tab's icon in the text colour, its face the bar's. An image: the HTML
    of ``st.html`` keeps no inline SVG."""
    palette = colors()
    drawing = DRAWING.replace("var(--pasr-icon-face, #fff)", palette["bar"])
    drawing = drawing.replace("currentColor", palette["text"])
    return f'<img src="data:image/svg+xml,{quote(drawing)}" alt="">'


def styles() -> str:
    palette = colors()
    return f"""
<style>
/* Streamlit's own strip lies over the bar's top band, see-through, letting clicks through to
   the bar except on its menu */
header[data-testid="stHeader"] {{ background: transparent; height: {TOP}rem; min-height: 0; }}
/* centred in the band; the ⋮ menu's right edge on the bar's contents' (Streamlit keeps 1rem
   right of it) */
header[data-testid="stHeader"] [data-testid="stToolbar"] {{
  height: 100%; display: flex; align-items: center; padding-right: calc({SIDES} - 1rem);
}}
header[data-testid="stHeader"], header[data-testid="stHeader"] * {{ pointer-events: none; }}
header[data-testid="stHeader"] [data-testid="stMainMenu"],
header[data-testid="stHeader"] [data-testid="stMainMenu"] * {{ pointer-events: auto; }}
/* no running figure and Stop button: Home and the toasts refresh every few seconds, so it would
   flicker on and off; long actions show their own moving dots */
header[data-testid="stHeader"] [data-testid="stStatusWidget"] {{ display: none; }}
/* no space above the bar, which is the first thing in the page's column (``page``) */
[data-testid="stMainBlockContainer"] {{ padding-top: 0; }}
.st-key-{HEADER} {{  /* above the page, so the menu's sections open over it */
  position: relative; z-index: 990; overflow: visible;
  width: 100vw; max-width: none; margin: 0 0 1rem calc(50% - 50vw);
  /* the bar and what is in it span the window, from its top */
  padding: {TOP}rem {SIDES} {BOTTOM}rem;
  background: {palette["bar"]}; border-bottom: 1px solid {palette["bar_line"]};
}}
/* the robot, and the name over what it stands for; no taller than the menu's buttons
   ({LABEL_HEIGHT}rem), so the line under the section shown still sits on the bar's edge */
.pasr-brand {{ display: flex; align-items: center; gap: 0.55rem; white-space: nowrap; }}
.pasr-brand-logo {{ display: flex; }}
.pasr-brand-logo img {{ width: {LABEL_HEIGHT}rem; height: {LABEL_HEIGHT}rem; }}
/* the robot and the name open Home: an invisible page link lies over them, so the session is
   kept, as with the menu's links */
.st-key-{BRAND} {{ position: relative; margin-right: 0.75rem; border-radius: 0.5rem; }}
.st-key-{BRAND} > [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) {{
  position: absolute; inset: 0; z-index: 1; margin: 0;
}}
.st-key-{BRAND} [data-testid="stPageLink"], .st-key-{BRAND} [data-testid="stPageLink-NavLink"] {{
  width: 100%; height: 100%; margin: 0; padding: 0;
}}
.st-key-{BRAND} [data-testid="stPageLink-NavLink"] {{ opacity: 0; }}
.st-key-{BRAND}:has(a:focus-visible) {{
  outline: 2px solid {palette["accent"]}; outline-offset: 4px;
}}
.pasr-brand-name {{
  display: flex; flex-direction: column; font-size: 1.6rem; font-weight: 700; line-height: 1;
}}
.pasr-brand-name small {{
  font-size: 0.75rem; font-weight: 400; line-height: 1.15; color: {palette["bar_text"]};
}}
{buttons(after=' [data-testid="stIconMaterial"]')} {{ font-size: 1.4rem; }}  /* the section icons */
@media (min-width: {ONE_ROW}rem) {{  /* one row: the menu a little lower, and the line under the
                                       section shown, moved up as much, on the bar's edge */
  .st-key-{HEADER} .st-key-{MENU} {{ top: {DROP}rem; }}
  /* Streamlit's ⋮ menu in the row too, level with the robot's buttons and after them */
  header[data-testid="stHeader"] {{ top: {TOP}rem; height: {LABEL_HEIGHT}rem; }}
  .st-key-{HEADER} {{ margin-bottom: 0; padding-right: calc({SIDES} + 2.75rem); }}
  /* the bar stays at the top while the page scrolls under it, as the ⋮ menu does: Streamlit's
     wrapper around it sticks (the bar alone would stay in that wrapper, as tall as itself), and
     the room under the bar is outside it, so nothing clear lies over the page; a phone's bar,
     several rows tall, scrolls away instead */
  [data-testid="stLayoutWrapper"]:has(> .st-key-{HEADER}) {{
    position: sticky; top: 0; z-index: 990; margin-bottom: 1rem;
  }}
  {buttons(f".st-key-{HEADER} {HERE}", "::before")} {{
    bottom: calc(-{BOTTOM - DROP:g}rem - 1px);
  }}
}}
</style>
"""


def header(sections: Mapping[str, Section], current: StreamlitPage) -> robot.Action | None:
    """Draws the bar; returns the robot button pressed, to run under the bar."""
    st.html(styles())
    with st.container(key=HEADER, horizontal=True, vertical_alignment="center", gap="small"):
        with st.container(key=BRAND, width="content", gap=None):
            st.html(
                f'<div class="pasr-brand"><span class="pasr-brand-logo" aria-hidden="true">'
                f'{logo()}</span><span class="pasr-brand-name">PASR'
                "<small>privacy-aware social robot</small></span></div>",
                width="content",
            )
            home = next(iter(sections.values())).pages[0]
            st.page_link(home, label="PASR, home")
        top_menu(sections, current)
        st.space("stretch")
        robot.live_view_switch()  # here, so it can be switched from any page
        return robot.controls()
