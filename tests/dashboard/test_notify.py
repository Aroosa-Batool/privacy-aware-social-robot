"""Toasts instead of boxes on the page: one icon per kind (the script colours them by it), a
lasting state said once, and a toast sent just before a reload shown after it."""

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

from pasr.dashboard.components.notify import ICONS, SCRIPT, styles


def test_each_kind_has_its_own_icon_colour_and_close_button():
    assert len(set(ICONS.values())) == len(ICONS)
    for kind, icon in ICONS.items():
        assert f'"{icon}": "{kind}"' in SCRIPT  # the script reads the kind from the icon
    css = styles()
    assert all(f'[data-kind="{kind}"]' in css for kind in ICONS)
    assert 'button[aria-label="Close"]' in css
    assert "dataset.copy" in SCRIPT and "[data-copy]" in css  # a copy of a toast stays hidden


def test_the_kinds_and_how_long_they_stay():
    def page() -> None:
        from pasr.dashboard.components.notify import notify

        notify("Saved.", "success")
        notify("Restart to apply.", "warning")
        notify("Capture failed.", "error")

    app = AppTest.from_function(page).run()
    assert [(t.value, t.icon) for t in app.toast] == [
        ("Saved.", ":material/check_circle:"),
        ("Restart to apply.", ":material/warning:"),
        ("Capture failed.", ":material/error:"),
    ]
    assert [t.proto.duration for t in app.toast] == [4, 10, 10]  # problems stay longer


def test_a_lasting_state_is_said_once_per_session():
    def page() -> None:
        from pasr.dashboard.components.notify import notify

        notify("Owner voice not enrolled.", "warning", once=True)

    app = AppTest.from_function(page).run()
    assert len(app.toast) == 1
    app.run()
    assert not app.toast


def test_a_toast_sent_just_before_a_reload_is_shown_after_it():
    def page() -> None:
        import streamlit as st

        from pasr.dashboard.components.notify import flush, notify, rerun

        flush()
        if st.button("Save"):
            notify("Saved #3.", "success")
            rerun()

    app = AppTest.from_function(page).run()
    app.button[0].click().run()
    assert [t.value for t in app.toast] == ["Saved #3."]
    app.run()
    assert not app.toast  # and only once
