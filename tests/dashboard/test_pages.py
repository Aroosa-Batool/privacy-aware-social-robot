"""Headless dashboard tests (Streamlit AppTest): every page renders, key interactions work."""

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

from pasr.dashboard import state
from pasr.domain.enums import Biometric, DisclosurePolicy
from pasr.orchestration.enrollment import FACE_GUIDANCE
from pasr.settings.loader import load_settings, read_overrides
from support.live import Windows

DASHBOARD = Path(state.__file__).parent
PAGES = sorted(p for p in (DASHBOARD / "views").glob("*.py") if not p.name.startswith("_"))


@pytest.fixture
def data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stand_in_robot) -> Iterator[Path]:
    path = tmp_path / "data"
    monkeypatch.setenv("PASR__STORAGE__DATA_DIR", str(path))
    monkeypatch.setenv("PASR__HARDWARE__MICROPHONE__CHUNK_MS", "100")
    state.get_handle.clear()
    yield path
    state.get_handle().stop()
    state.get_handle.clear()


def run(page: Path) -> AppTest:
    app = AppTest.from_file(str(page), default_timeout=60).run()
    assert not app.exception, app.exception
    return app


@pytest.mark.parametrize("page", [DASHBOARD / "app.py", *PAGES], ids=lambda p: p.stem)
def test_page_renders_while_stopped(page: Path, data_dir: Path):
    run(page)


def test_pages_render_while_running(data_dir: Path):
    state.get_handle().start()
    for page in PAGES:
        run(page)


def test_onboarding_and_enrolment(data_dir: Path):
    app = run(DASHBOARD / "views" / "profile.py")
    app.text_input[0].input("Aroosa")
    app.button[0].click().run()
    assert state.offline().repos.owner.get().display_name == "Aroosa"

    state.get_handle().start()
    app = run(DASHBOARD / "views" / "profile.py")
    assert any(c.value == FACE_GUIDANCE for c in app.caption)
    next(b for b in app.button if b.label == "Capture face").click().run()
    assert not app.exception
    assert state.offline().repos.owner.enrollment()[Biometric.FACE][0] == 5


def test_typed_reminder_asks_for_a_date(data_dir: Path):
    app = run(DASHBOARD / "views" / "reminders.py")
    app.text_input[0].input("Doctor appointment at 2pm")
    next(b for b in app.button if b.label == "Add reminder").click().run()
    assert any("On what date" in d.label for d in app.date_input)
    next(b for b in app.button if b.label == "Save").click().run()
    assert not app.exception
    (reminder,) = state.offline().service.upcoming()
    assert reminder.sensitive
    assert (reminder.due_at.hour, reminder.due_at.minute) == (14, 0)


def test_models_page_chooses_a_model_per_stage_and_keeps_the_sensitive_words(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("PASR__PERCEPTION__VAD__PLUGIN")  # the default, Silero, not the tests'
    app = run(DASHBOARD / "views" / "models.py")
    assert [t.label for t in app.tabs] == ["Voice", "Face", "Sensitivity"]
    assert [s.label for s in app.selectbox] == ["Model"] * 5
    assert not app.number_input  # no thresholds, sizes or other tuning
    assert not any("Room scan" in m.value for m in app.markdown)  # on the Hardware page
    keywords = [t.label for t in app.text_area]  # the keyword classifier's lists, kept as they were
    assert keywords == ["Sensitive keywords", "Non sensitive keywords"]

    vad = next(s for s in app.selectbox if s.key and s.key.endswith("perception.vad.plugin"))
    assert vad.value == "silero"
    vad.set_value("energy").run()
    next(b for b in app.button if b.label == "Save").click().run()
    assert not app.exception
    assert read_overrides(data_dir) == {"perception": {"vad": {"plugin": "energy"}}}
    assert load_settings().perception.vad.plugin == "energy"


def test_room_scan_and_face_following_settings(data_dir: Path):
    app = run(DASHBOARD / "views" / "hardware.py")
    assert any(m.value == "#### Room scan" for m in app.markdown)
    assert not app.expander  # following is a toggle, nothing more
    assert [t.label for t in app.toggle] == ["Follow faces that are not in full view"]
    app.toggle[0].set_value(True).run()
    assert any(c.value == "1 unsaved change(s)" for c in app.caption)
    next(b for b in app.button if b.label == "Save").click().run()
    assert not app.exception
    assert read_overrides(data_dir) == {"scan": {"follow": {"enabled": True}}}
    assert load_settings().scan.follow.enabled


def test_setup_page_tests_the_devices_and_installs_models(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from pasr.perception import models

    monkeypatch.setenv("PASR__STORAGE__MODELS_DIR", str(tmp_path / "models"))  # none downloaded
    in_use = {
        "face": "insightface",
        "speaker": "speechbrain_ecapa",
        "vad": "silero",
        "stt": "faster_whisper",
        "sensitivity": "zero_shot",
    }
    for kind, plugin in in_use.items():  # the real models, as on the robot (none is loaded here)
        monkeypatch.setenv(f"PASR__PERCEPTION__{kind.upper()}__PLUGIN", plugin)
    app = run(DASHBOARD / "views" / "setup.py")
    app.multiselect[0].set_value(["camera", "microphone"]).run()
    next(b for b in app.button if b.label == "Run test").click().run()
    assert not app.exception
    results = app.dataframe[0].value
    assert list(results["device"]) == ["Camera", "Microphone"]
    assert list(results["result"]) == ["✅ ok", "✅ ok"]
    assert not any("head camera" in m.value for m in app.markdown)

    installed = []
    monkeypatch.setattr(
        models, "download_model", lambda settings, kind, plugin: installed.append(plugin)
    )
    next(b for b in app.button if b.label == "Install the marked models").click().run()
    assert not app.exception
    # ticked to start with: the models in use that are not downloaded (Silero comes bundled)
    assert sorted(installed) == ["faster_whisper", "insightface", "speechbrain_ecapa", "zero_shot"]
    assert [t.icon for t in app.toast if "Installed" in t.value] == [":material/check_circle:"]


def test_setup_page_waits_while_the_robot_runs(data_dir: Path):
    state.get_handle().start()
    app = run(DASHBOARD / "views" / "setup.py")
    assert any("Stop it to scan or test the devices" in t.value for t in app.toast)
    assert not app.info  # a toast, not a box that stays
    assert next(b for b in app.button if b.label == "Run test").disabled

    next(b for b in app.button if b.label == "Stop the robot").click().run()  # right there
    assert not app.exception
    assert not state.get_handle().running
    assert not next(b for b in app.button if b.label == "Run test").disabled


def test_profiles_are_saved_loaded_and_reset_on_the_profile_page(data_dir: Path):
    profiles = "Profiles: save or load all settings"
    for elsewhere in ("models.py", "setup.py"):
        assert not any(e.label == profiles for e in run(DASHBOARD / "views" / elsewhere).expander)
    state.save_settings({"identity": {"face_threshold": 0.55}})
    app = run(DASHBOARD / "views" / "profile.py")
    assert any(e.label == profiles for e in app.expander)
    app.button(key="confirm-restore-defaults").click().run()
    assert not app.exception
    assert read_overrides(data_dir) == {}  # every setting back to its default


def test_device_errors_become_a_toast_not_a_crashed_page(data_dir: Path, monkeypatch):
    from pasr.hardware.protocols import HardwareNotAvailableError
    from pasr.orchestration.enrollment import EnrollmentService

    async def broken_microphone(self, progress=None):
        raise HardwareNotAvailableError("microphone 'AirPods Pro' could not be opened")

    monkeypatch.setattr(EnrollmentService, "enroll_voice", broken_microphone)
    app = run(DASHBOARD / "views" / "profile.py")
    app.text_input[0].input("Aroosa")
    app.button[0].click().run()
    state.get_handle().start()
    app = run(DASHBOARD / "views" / "profile.py")
    next(b for b in app.button if b.label == "Capture voice").click().run()
    assert not app.exception
    failed = [t for t in app.toast if "Voice capture failed: microphone 'AirPods Pro'" in t.value]
    assert [t.icon for t in failed] == [":material/error:"]  # a red toast
    assert not app.warning  # and no box left on the page
    assert any(b.label == "Capture face" for b in app.button)  # the rest of the page still works


def test_the_live_view_window_toggle_is_in_the_header_and_saved(data_dir: Path):
    app = run(DASHBOARD / "app.py")
    assert any(t.label == "Live view window" for t in app.toggle)  # on every page, not one

    def switch() -> None:  # AppTest keeps the entry script's header on its first run only
        from pasr.dashboard.components.robot import live_view_switch

        live_view_switch()

    app = AppTest.from_function(switch, default_timeout=60).run()
    assert app.toggle[0].value is False
    app.toggle[0].set_value(True).run()
    assert not app.exception
    assert read_overrides(data_dir)["live_view"] == {"enabled": True}


def test_the_robots_state_moves_while_it_runs():
    from pasr.dashboard.components.robot import state, state_styles

    assert 'is-running" role="status"' in state(True) and ">Running</span>" in state(True)
    assert 'is-stopped" role="status"' in state(False) and ">Stopped</span>" in state(False)
    css = state_styles()
    assert ".is-running .pasr-state-dot::before" in css and "animation: pasr-ripple" in css
    assert "prefers-reduced-motion" in css  # a slow glow instead, for those who ask for less


def test_the_dashboards_robot_shows_enrolment_in_the_live_view_window(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, live_windows: Windows
):
    monkeypatch.setenv("PASR__LIVE_VIEW__ENABLED", "true")
    app = run(DASHBOARD / "views" / "profile.py")
    app.text_input[0].input("Aroosa")
    app.button[0].click().run()
    state.get_handle().start()
    app = run(DASHBOARD / "views" / "profile.py")
    next(b for b in app.button if b.label == "Capture face").click().run()
    assert not app.exception

    deadline = time.monotonic() + 10
    while not any(view.title == "Enrolling the owner's face" for view in shown(live_windows)):
        assert time.monotonic() < deadline, "the live view window never showed the enrolment"
        time.sleep(0.05)
    state.get_handle().stop()
    assert live_windows.last.closed  # with the robot


def shown(windows: Windows) -> list:
    return [view for window in windows.opened for view in window.views]


def test_the_menu_has_a_button_per_section_listing_every_page(data_dir: Path):
    app = run(DASHBOARD / "app.py")
    links = [(link.proto.label, link.proto.page) for link in app.get("page_link")]
    buttons = {"Home": "", "Settings": "setup", "Info": "events", "Profile": "profile"}
    assert all(button in links for button in buttons.items())  # each opens its first page
    # every page is in its section's list once, except Profile: its button is its only link
    assert len(links) == 1 + len(buttons) + len(PAGES) - 1
    assert links.count(("Profile", "profile")) == 1
    assert ("PASR, home", "") in links  # the logo and name open Home
    taps = [str(element.proto) for element in app.get("html")]  # what a touch screen shows
    assert all(
        any("pasr-menu-tap" in t and f">{name}</div>" in t for t in taps) for name in buttons
    )


def test_no_pages_folder_lets_a_link_skip_the_entry_point():
    # Streamlit runs a file in a "pages" folder beside app.py by itself when opened by its link
    # on a freshly started server: no header, and its own list of files in the sidebar.
    assert not (DASHBOARD / "pages").exists()


def test_the_header_shows_the_robots_state_and_only_the_buttons_that_apply(data_dir: Path):
    app = run(DASHBOARD / "app.py")
    assert [b.label for b in app.button if b.key and b.key.startswith("robot-")] == ["Start robot"]
    assert not app.sidebar.children  # the header replaced the sidebar

    def header_controls() -> None:  # AppTest keeps the entry script's header on its first run only
        from pasr.dashboard.components.robot import controls, perform

        action = controls()
        if action is not None:
            perform(action)

    app = AppTest.from_function(header_controls, default_timeout=60).run()
    app.button(key="robot-start").click().run()
    assert not app.exception
    assert state.get_handle().running
    assert [b.label for b in app.button] == ["Stop"]

    app.button(key="robot-stop").click().run()
    assert not state.get_handle().running
    assert [b.label for b in app.button] == ["Start robot"]


def test_a_page_that_needs_the_robot_points_to_the_headers_start(data_dir: Path):
    app = run(DASHBOARD / "views" / "profile.py")
    app.text_input[0].input("Aroosa")
    app.button[0].click().run()
    said = "Start it at the top right to capture"
    assert [t.icon for t in app.toast if said in t.value] == [":material/warning:"]
    assert not any(b.label == "Start the robot" for b in app.button)  # the header's is enough
    app.run()
    assert not any(said in t.value for t in app.toast)  # said once, not again

    state.get_handle().start()  # Start robot in the header
    app.run()
    assert not app.exception
    assert any(b.label == "Capture face" for b in app.button)


def test_remembering_watch_answers_is_its_own_choice(data_dir: Path):
    app = run(DASHBOARD / "views" / "profile.py")

    def save():
        return next(b for b in app.button if b.label == "Save preferences")

    def remember():
        return [r for r in app.radio if r.label.startswith("When you answer on the watch")]

    assert save().disabled  # nothing changed yet
    (choice,) = remember()
    assert choice.value is False  # the default: ask every time, keep nothing
    choice.set_value(True).run()
    save().click().run()
    assert not app.exception
    policy = load_settings().privacy.disclosure_policy
    assert policy is DisclosurePolicy.ASK_ONCE_PER_BYSTANDER
    assert any("Info › People & consent" in c.value for c in app.caption)

    asking = next(r for r in app.radio if r.label.startswith("How should the robot handle"))
    asking.set_value(False).run()  # always say them: there is no answer to remember
    assert not remember()
    save().click().run()
    assert load_settings().privacy.disclosure_policy is DisclosurePolicy.ALWAYS_DISCLOSE


def test_home_counts_down_to_a_quick_test_and_tags_it(data_dir: Path):
    state.get_handle().start()
    app = run(DASHBOARD / "views" / "reminders.py")
    next(b for b in app.button if b.label == "Add test reminder").click().run()
    app = run(DASHBOARD / "views" / "overview.py")
    (card,) = [m for m in app.metric if m.label.startswith("Next reminder")]
    assert card.label == "Next reminder (test)"
    assert card.value.startswith("in ") and card.value.endswith(" s")  # due in 45 s


def test_home_leaves_starting_the_robot_to_the_header(data_dir: Path):
    app = run(DASHBOARD / "views" / "overview.py")
    assert not any(b.label == "Start the robot" for b in app.button)


def test_the_closed_voice_tab_does_not_ask_for_the_robot(data_dir: Path):
    app = run(DASHBOARD / "views" / "reminders.py")
    assert not any("set reminders by voice" in t.value for t in app.toast)
    assert not any(b.label == "Start the robot" for b in app.button)


def test_deleting_enrolled_data_needs_the_confirm_button(data_dir: Path):
    app = run(DASHBOARD / "views" / "profile.py")
    app.text_input[0].input("Aroosa")
    app.button[0].click().run()
    state.get_handle().start()
    app = run(DASHBOARD / "views" / "profile.py")
    next(b for b in app.button if b.label == "Capture face").click().run()
    assert state.offline().repos.owner.enrollment()[Biometric.FACE][0] == 5

    delete = next(b for b in app.button if b.label == "Delete face data")
    assert delete.key == "confirm-delete-face"  # the button inside the confirm panel
    delete.click().run()
    assert not app.exception
    assert Biometric.FACE not in state.offline().repos.owner.enrollment()


def test_profile_progress_counts_only_the_steps_the_chosen_detection_needs(data_dir: Path):
    app = run(DASHBOARD / "views" / "profile.py")
    assert app.get("progress")[0].proto.text == "0 of 3 required steps done"

    state.save_settings({"privacy": {"detection_modality": "audio_only"}})
    app = run(DASHBOARD / "views" / "profile.py")
    assert app.get("progress")[0].proto.text == "0 of 2 required steps done"
    assert sum("Optional" in m.value for m in app.markdown) == 1  # the face step

    state.save_settings({"privacy": {"detection_modality": "camera_only"}})
    app = run(DASHBOARD / "views" / "profile.py")
    assert app.get("progress")[0].proto.text == "0 of 2 required steps done"
    texts = [m.value for m in app.markdown]
    (badge,) = [i for i, text in enumerate(texts) if "Optional" in text]
    assert "Voice" in texts[badge - 1]  # the badge follows its step's title
    detection = next(r for r in app.radio if r.label.startswith("How may the robot check"))
    assert "Camera only , the microphone is never used for this" in detection.options


def test_the_pipeline_says_each_stages_state_in_words():
    from pasr.apps.reminder.due_flow import DueState as S
    from pasr.dashboard.components.pipeline import progress

    listen = {S.LISTENING, S.AUDIO_BYSTANDER}
    assert progress(listen, {S.IDLE, S.WAKING}, S.LISTENING) == "now"
    assert progress(listen, {S.LISTENING}, S.SCANNING) == "done"
    assert progress(listen, set(), S.WAKING) == "pending"
    deliver = {S.WAIT_FOR_DUE, S.DISCLOSE_SPEAK, S.DISCLOSE_WATCH, S.DONE}
    assert progress(deliver, set(), S.DONE) == "done"  # a finished reminder is not "now"


FAILED_AT_SCAN = ("IDLE", "WAKING", "CHECKING_PRESENCE", "LISTENING", "SCANNING", "FAILED")


def failed_flow(*, finished: bool, delivered: str | None = None):
    from datetime import UTC, datetime

    from pasr.orchestration.runtime import FlowView

    at = datetime(2026, 11, 1, 13, 39, tzinfo=UTC)
    steps = tuple((name, at, "") for name in FAILED_AT_SCAN)
    return FlowView(68, "FAILED", steps, finished, delivered, "camera 0 returned no frame")


def test_a_failure_is_red_where_it_happened_and_deliver_says_where_the_reminder_went():
    import re

    from pasr.dashboard.components.pipeline import strip, summary

    def stages(flow) -> list[str]:
        return re.findall(r'<li class="pasr-step is-(\w+)', strip(flow))

    reached = ["done"] * 4 + ["failed", "pending", "pending"]  # Scan failed, not green
    sent = failed_flow(finished=True, delivered="watch")
    assert stages(sent) == [*reached, "done"]  # the watch got it after all
    assert stages(failed_flow(finished=False)) == [*reached, "now"]  # on its way there
    assert stages(failed_flow(finished=True)) == [*reached, "failed"]  # the watch failed too
    assert summary(sent) == (
        "last run: the Scan step failed. Camera 0 returned no frame. It was sent to the watch."
    )


def test_a_failed_reminder_is_a_red_toast_once(data_dir: Path, monkeypatch: pytest.MonkeyPatch):
    from pasr.orchestration.runtime import Runtime

    monkeypatch.setattr(Runtime, "latest_flow", lambda self: failed_flow(finished=False))
    state.get_handle().start()

    app = AppTest.from_function(alerts, default_timeout=60).run()
    failed = [t for t in app.toast if "the Scan step failed. Camera 0 returned no frame" in t.value]
    assert [t.icon for t in failed] == [":material/error:"]
    app.run()
    assert not app.toast  # once, not on every refresh

    monkeypatch.setattr(Runtime, "latest_flow", lambda self: failed_flow(finished=True))
    app.run()
    assert [t.value for t in app.toast] == ["Reminder #68 could not be sent to the watch: missed."]

    app = AppTest.from_function(alerts, default_timeout=60).run()  # opened after it ended
    assert not app.toast  # old news


def alerts() -> None:  # the entry point runs it on every page
    from pasr.dashboard.components.alerts import alerts

    alerts()


def test_what_goes_wrong_while_the_robot_runs_is_a_toast_once(data_dir: Path):
    import logging

    state.get_handle().start()
    app = AppTest.from_function(alerts, default_timeout=60).run()  # the dashboard is open
    camera = logging.getLogger("pasr.hardware.camera.real")
    camera.warning("camera %s sent no frame for %.0f s: reconnecting it", 0, 3.0)
    camera.info("camera %s is back", 0, extra={"toast": True})
    try:
        raise RuntimeError  # an error without a message
    except RuntimeError:
        logging.getLogger("pasr.apps.reminder.due_flow").exception("could not rest the head")
    app.run()
    assert [(t.icon, t.value) for t in app.toast] == [
        (":material/warning:", "Camera 0 sent no frame for 3 s: reconnecting it."),
        (":material/info:", "Camera 0 is back."),
        (":material/error:", "Could not rest the head: an unknown error occurred (RuntimeError)."),
    ]
    app.run()
    assert not app.toast  # each once

    app = AppTest.from_function(alerts, default_timeout=60).run()  # opened afterwards
    assert not app.toast  # old news


def flow_through(*states: str, finished: bool = True, **fields: Any):
    """A flow that went through ``states``, the last one the state it is in."""
    from datetime import UTC, datetime

    from pasr.orchestration.runtime import FlowView

    at = datetime(2026, 11, 1, 13, 39, tzinfo=UTC)
    return FlowView(77, states[-1], tuple((s, at, "") for s in states), finished, **fields)


def route(flow) -> list[tuple[str, str]]:
    """Each stage's classes, and how many columns its arch spans if it has one."""
    import re

    from pasr.dashboard.components.pipeline import strip

    html = strip(flow)
    assert "pasr-step-detail" not in html  # each stage is its name and state, nothing more
    items = re.findall(r'<li class="([^"]+)"[^>]*>(<span class="pasr-step-bypass"[^>]*>)?', html)
    return [(classes, re.sub(r"\D", "", bypass)) for classes, bypass in items]


START = ("IDLE", "WAKING", "CHECKING_PRESENCE")


def test_the_pipeline_route_arches_over_skipped_stages():
    # no consent needed: from Decide over Consent to Deliver
    stages = route(
        flow_through(
            *START,
            "LISTENING",
            "SCANNING",
            "NO_BYSTANDER",
            "WAIT_FOR_DUE",
            "DISCLOSE_SPEAK",
            "DONE",
            delivered="spoken",
            planned="spoken",
        )
    )
    assert [("is-taken" in c, over) for c, over in stages] == [
        (False, ""),
        (True, ""),
        (True, ""),
        (True, ""),
        (True, ""),
        (True, ""),
        (False, ""),  # Consent: the line into it was not taken...
        (False, "2"),  # ...nor the one out of it: an arch over 2 columns, Decide to Deliver
    ]
    # owner away: from Presence straight to the watch, over four stages, dashed amber
    away = flow_through(
        *START, "OWNER_AWAY", "WAIT_FOR_DUE", "DISCLOSE_WATCH", "DONE", delivered="watch"
    )
    stages = route(away)
    assert stages[2][0].startswith("pasr-step is-turned")  # Presence: no green tick
    assert stages[-1] == ("pasr-step is-done via-turned", "5")
    assert not any(over for _, over in stages[:-1])
    # still running: nothing reached after the gap yet, so no arch
    assert not any(over for _, over in route(flow_through(*START, finished=False)))


def test_each_breaker_is_amber_where_it_turned_the_reminder():
    from pasr.dashboard.components.pipeline import stages, summary

    def marks(flow) -> list[str]:
        return [
            f"{s.progress}" if s.word in ("done", "skipped") else f"{s.progress}: {s.word}"
            for s in stages(flow)
        ]

    # the owner's watch did not answer, and then did not take the reminder either (#77)
    missed = flow_through(
        *START,
        "OWNER_AWAY",
        "WAIT_FOR_DUE",
        "DISCLOSE_WATCH",
        "FAILED",
        planned="watch",
        problem="the watch did not show the reminder",
    )
    assert marks(missed) == [*["done"] * 2, "turned: away", *["pending"] * 4, "failed: missed"]
    assert route(missed)[-1] == ("pasr-step is-failed via-turned", "5")
    assert summary(missed) == (
        "last run: the owner's watch did not answer, so the owner counted as away. The Deliver "
        "step failed. The watch did not show the reminder. Trying the watch again failed too, "
        "so it was missed."
    )
    # someone heard, so no scan; the owner said no on the watch
    said_no = flow_through(
        *START,
        "LISTENING",
        "AUDIO_BYSTANDER",
        "CHECK_MEMORY",
        "AWAITING_CONSENT",
        "WAIT_FOR_DUE",
        "DISCLOSE_WATCH",
        "DONE",
        planned="watch",
        answer="no",
        delivered="watch",
    )
    assert marks(said_no) == [
        *["done"] * 3,
        "done: heard someone",  # detection working: green, saying what it found
        "pending",
        "done",
        "turned: said no",
        "done: to watch",
    ]
    assert "via-" not in route(said_no)[5][0]  # into Decide: a plain green arch
    assert summary(said_no) == (
        "last run: someone other than the owner was heard. The owner said no on the watch. "
        "It was sent to the watch."
    )
    # someone seen, and the owner said yes: spoken, green all the way (#83)
    said_yes = flow_through(
        *START,
        "LISTENING",
        "SCANNING",
        "VISUAL_BYSTANDER",
        "CHECK_MEMORY",
        "AWAITING_CONSENT",
        "WAIT_FOR_DUE",
        "DISCLOSE_SPEAK",
        "DONE",
        planned="spoken",
        answer="yes",
        delivered="spoken",
    )
    assert marks(said_yes) == [
        *["done"] * 4,
        "done: saw someone",
        "done",
        "done: said yes",
        "done: spoken",
    ]
    assert not any("via-" in classes for classes, _ in route(said_yes))  # no dashed lines
    assert summary(said_yes) == (
        "last run: someone other than the owner was seen. The owner said yes on the watch. "
        "It was spoken."
    )
    # someone seen whom the owner had declined for before: no need to ask
    declined = flow_through(
        *START,
        "LISTENING",
        "SCANNING",
        "VISUAL_BYSTANDER",
        "CHECK_MEMORY",
        "WAIT_FOR_DUE",
        "DISCLOSE_WATCH",
        "DONE",
        planned="watch",
        delivered="watch",
    )
    assert marks(declined)[4:] == [
        "done: saw someone",
        "turned: declined before",
        "pending",
        "done: to watch",
    ]
    # no answer on the watch
    no_answer = flow_through(
        *START, "AWAITING_CONSENT", "WAIT_FOR_DUE", "DISCLOSE_WATCH", "DONE", answer="timeout"
    )
    assert marks(no_answer)[6] == "turned: no answer"
    # all clear, but the owner had gone by the due time
    left = flow_through(
        *START,
        "LISTENING",
        "NO_BYSTANDER",
        "WAIT_FOR_DUE",
        "DISCLOSE_WATCH",
        "DONE",
        planned="spoken",
        delivered="watch",
    )
    assert marks(left)[-1] == "turned: owner left"
    # all clear and spoken: green all the way, and Deliver says how
    spoken = flow_through(
        *START,
        "LISTENING",
        "NO_BYSTANDER",
        "WAIT_FOR_DUE",
        "DISCLOSE_SPEAK",
        "DONE",
        planned="spoken",
        delivered="spoken",
    )
    assert marks(spoken) == [*["done"] * 4, "pending", "done", "pending", "done: spoken"]
    assert summary(spoken) == "last run: it was spoken."
    # speaking failed, but the watch took it: amber, not a green tick
    retried = flow_through(
        *START,
        "WAIT_FOR_DUE",
        "DISCLOSE_SPEAK",
        "FAILED",
        planned="spoken",
        delivered="watch",
    )
    assert marks(retried)[-1] == "turned: to watch"


def test_an_empty_form_adds_nothing(data_dir: Path):
    app = run(DASHBOARD / "views" / "reminders.py")
    next(b for b in app.button if b.label == "Add reminder").click().run()  # nothing typed
    next(t for t in app.text_input if t.label == "Title").set_value("   ")
    next(b for b in app.button if b.label == "Add test reminder").click().run()
    assert not app.exception
    assert not app.date_input  # no draft to check
    assert state.offline().service.upcoming() == []


def test_yes_no_columns_read_as_blue_words_not_pale_checkboxes():
    from pasr.dashboard.components.palette import LIGHT
    from pasr.dashboard.components.tables import with_flags

    table = with_flags(
        [{"due": "Mon", "sensitive": True}, {"due": "Tue", "sensitive": False}], "sensitive"
    )
    assert list(table.data["sensitive"]) == ["✓ Yes", "No"]
    assert f"color: {LIGHT['accent']}" in table.to_html()
