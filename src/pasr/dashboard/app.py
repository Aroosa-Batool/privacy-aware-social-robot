"""Dashboard entry point: the header bar (page menu, robot state and controls) above each page."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from pasr.dashboard import ICON
from pasr.dashboard.components.alerts import alerts
from pasr.dashboard.components.header import header
from pasr.dashboard.components.loading import install_styles
from pasr.dashboard.components.menu import Section
from pasr.dashboard.components.notify import flush, notify
from pasr.dashboard.components.notify import install as install_toasts
from pasr.dashboard.components.notify import watch as watch_toasts
from pasr.dashboard.components.page import frame
from pasr.dashboard.components.robot import perform
from pasr.dashboard.state import explain, logger

# Not "pages": Streamlit would also treat a folder of that name as pages of their own, and run a
# page opened by its link without this script (no header) until someone loads the root page.
PAGES = Path(__file__).parent / "views"

st.set_page_config(page_title="PASR", page_icon=str(ICON), layout="wide")
install_styles()
install_toasts()
flush()  # toasts sent just before the reload that started this run

# What the robot does and will do; making it ready and tuning it; what it has recorded; whose
# robot it is.
sections = {
    "Home": Section(
        ":material/home:",
        [
            st.Page(PAGES / "overview.py", title="Home", icon=":material/home:", default=True),
            st.Page(PAGES / "reminders.py", title="Reminders", icon=":material/alarm:"),
        ],
    ),
    "Settings": Section(
        ":material/settings:",
        [
            st.Page(PAGES / "setup.py", title="Setup", icon=":material/devices:"),
            st.Page(
                PAGES / "hardware.py", title="Hardware", icon=":material/precision_manufacturing:"
            ),
            st.Page(PAGES / "models.py", title="Models", icon=":material/tune:"),
            st.Page(PAGES / "calibration.py", title="Calibration", icon=":material/straighten:"),
            st.Page(PAGES / "reset.py", title="Reset", icon=":material/restart_alt:"),
        ],
    ),
    "Info": Section(
        ":material/info:",
        [
            st.Page(PAGES / "events.py", title="Events", icon=":material/list_alt:"),
            st.Page(PAGES / "people.py", title="People & consent", icon=":material/group:"),
        ],
    ),
    "Profile": Section(
        ":material/account_circle:",
        [st.Page(PAGES / "profile.py", title="Profile", icon=":material/person_add:")],
    ),
}
navigation = st.navigation(  # the header's menu replaces Streamlit's own
    {name: list(section.pages) for name, section in sections.items()}, position="hidden"
)
action = header(sections, navigation)
if action is not None:  # the moving dots and any problem show under the header
    perform(action)

with frame():
    try:
        navigation.run()
    except Exception as exc:  # last line of defence: a problem never takes the dashboard down
        logger.exception("page failed")
        notify(f"This page hit a problem: {explain(exc)}. Details are in the terminal.", "error")
        st.caption("This page could not be shown. Details are in the terminal.")
alerts()  # what goes wrong while the robot runs shows as a toast on any page
watch_toasts()
