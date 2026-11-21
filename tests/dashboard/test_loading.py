"""The working indicator: moving dots while the dashboard waits, gone once the work is done."""

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

from pasr.dashboard.components.loading import markup


def test_the_message_is_shown_as_text_not_html():
    shown = markup("Starting <the> robot & watch")
    assert "Starting &lt;the&gt; robot &amp; watch" in shown
    assert shown.count("<i></i>") == 3  # the three dots


def test_the_indicator_shows_during_the_work_and_is_gone_after():
    def page() -> None:
        import streamlit as st

        from pasr.dashboard.components.loading import install_styles, working

        install_styles()
        with working("Starting the robot"):
            st.session_state["while_working"] = True
        st.write("started")

    app = AppTest.from_function(page).run()
    assert not app.exception
    assert app.session_state["while_working"]
    # only the style block is left (it takes no space): the indicator was cleared
    assert all('role="status"' not in str(element.proto) for element in app.get("html"))
    assert app.markdown[0].value == "started"
