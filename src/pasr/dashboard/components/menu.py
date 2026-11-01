"""The menu across the top of the dashboard: a button per section (Home, Settings, Info, Profile)
that opens the section's first page, and shows all its pages while hovered or focused with the
keyboard. On a touch screen, where nothing hovers, a tap on the button shows the pages instead.
A section with a single page (Profile) has no list: its button opens the page.

Streamlit's own top navigation opens its sections on click only, so the menu is built from
``st.page_link`` items in keyed containers (Streamlit gives each a ``st-key-<key>`` CSS class),
revealed with CSS. Page links switch pages without reloading, so the session is kept. A section
closes a moment after the pointer leaves, so a slightly crooked path to a page does not lose it.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from typing import NamedTuple

import streamlit as st
from streamlit.navigation.page import StreamlitPage

from pasr.dashboard.components.palette import colors

MENU = "pasr-menu"
LABEL_HEIGHT = 2.5  # rem; fixed, so a bar holding the menu can move the line to its own edge
SECTION = f'[class*="st-key-{MENU}-section-"]'
PAGES = f'[class*="st-key-{MENU}-pages-"]'


class Section(NamedTuple):
    icon: str
    pages: Sequence[StreamlitPage]


def buttons(scope: str = SECTION, after: str = "") -> str:
    """The selector of the sections' buttons in ``scope`` (a link, or on a touch screen a tap
    target), each followed by ``after`` (a pseudo-element)."""
    link = f'{scope} > [data-testid="stElementContainer"] [data-testid="stPageLink-NavLink"]'
    return f"{link}{after}, {scope} .pasr-menu-tap{after}"


HERE = f'{SECTION}[class*="-here"]'  # the section of the page shown


def styles(last: int) -> str:
    """``last`` is the index of the last section, whose pages open leftwards on a phone."""
    palette = colors()
    return f"""
<style>
.st-key-{MENU} {{ position: relative; z-index: 1000; overflow: visible; }}
.st-key-{MENU} {SECTION} {{ position: relative; overflow: visible; }}
{buttons()} {{
  position: relative; display: flex; align-items: center; gap: 0.4rem;
  height: {LABEL_HEIGHT}rem; box-sizing: border-box; margin: 0; padding: 0 0.8rem;
  border-radius: 0.5rem; background: transparent; color: inherit; font-weight: 600;
  white-space: nowrap; text-decoration: none;
}}
{buttons(after=" p")}, {buttons(after=' [data-testid="stIconMaterial"]')} {{
  color: inherit; font-weight: 600; margin: 0;
}}
{buttons(f"{SECTION}:has({PAGES})", "::after")} {{  /* the section has a list of pages */
  content: "▾"; margin-left: -0.15rem; opacity: 0.6; font-size: 0.8em;
}}
{buttons(HERE)} {{ color: {palette["accent"]}; }}
{buttons(HERE, "::before")} {{  /* the line under the section shown */
  content: ""; position: absolute; left: 0.4rem; right: 0.4rem; bottom: 0; height: 3px;
  border-radius: 3px 3px 0 0; background: {palette["accent"]};
}}
{buttons(after=":focus-visible")} {{ outline: 2px solid {palette["accent"]}; outline-offset: 2px; }}
{buttons(f"{SECTION}:hover")}, {buttons(f"{SECTION}:focus-within")} {{
  background: {palette["bar_line"]};
}}
{SECTION} .pasr-menu-tap {{ display: none; cursor: default; }}  /* only on a touch screen */
@media (hover: none) {{  /* a touch screen: the button shows the pages instead of opening one */
  {SECTION} > [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) {{
    display: none;
  }}
  {SECTION} .pasr-menu-tap {{ display: flex; }}
}}
.st-key-{MENU} {PAGES} {{
  position: absolute; top: calc(100% + 0.35rem); left: 0; min-width: 15rem;
  padding: 0.35rem; gap: 0.1rem; border-radius: 0.6rem; background: {palette["panel"]};
  border: 1px solid {palette["line"]}; box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18);
  visibility: hidden; opacity: 0; transform: translateY(-0.25rem);
  transition: opacity 0.12s ease, transform 0.12s ease, visibility 0s linear 0.18s;
}}
/* covers the gap under the button, so moving down to the pages keeps the section open */
.st-key-{MENU} {PAGES}::before {{
  content: ""; position: absolute; left: 0; right: 0; top: -0.45rem; height: 0.45rem;
}}
.st-key-{MENU} {SECTION}:hover {PAGES},
.st-key-{MENU} {SECTION}:focus-within {PAGES} {{
  visibility: visible; opacity: 1; transform: none;
  transition: opacity 0.12s ease, transform 0.12s ease, visibility 0s;
}}
.st-key-{MENU} {PAGES} [data-testid="stPageLink-NavLink"] {{
  min-height: 2.4rem; padding: 0.4rem 0.65rem; border-radius: 0.45rem;
}}
@media (max-width: 40rem) {{
  .st-key-{MENU} [class*="st-key-{MENU}-section-{last}-"] {PAGES} {{ left: auto; right: 0; }}
}}
@media (prefers-reduced-motion: reduce) {{
  .st-key-{MENU} {PAGES} {{ transform: none; transition: visibility 0s linear 0.18s; }}
}}
</style>
"""


def top_menu(sections: Mapping[str, Section], current: StreamlitPage) -> None:
    """The menu; ``current`` is the page being shown (its section is underlined)."""
    st.html(styles(len(sections) - 1))
    with st.container(
        key=MENU, horizontal=True, width="content", gap="small", vertical_alignment="center"
    ):
        for index, (name, section) in enumerate(sections.items()):
            here = any(page.url_path == current.url_path for page in section.pages)
            key = f"{MENU}-section-{index}-{'here' if here else 'away'}"
            with st.container(key=key, width="content", gap=None):
                st.page_link(section.pages[0], label=name, icon=section.icon)
                st.html(f'<div class="pasr-menu-tap" tabindex="0">{html.escape(name)}</div>')
                if len(section.pages) > 1:
                    with st.container(key=f"{MENU}-pages-{index}", width="content", gap=None):
                        for page in section.pages:
                            st.page_link(page, width="stretch")
