import logging

from pasr.orchestration.notices import Notices, describe, on_loop_error, sentence


def test_an_error_without_a_message_is_unknown():
    assert describe(RuntimeError("camera 0 could not be opened")) == "camera 0 could not be opened"
    assert describe(RuntimeError("  ")) == "an unknown error occurred (RuntimeError)"
    assert sentence("") == "An unknown error occurred."
    assert sentence("is it the head camera?") == "Is it the head camera?"


def test_the_robots_warnings_and_errors_become_notices():
    notices = Notices()
    notices.attach()
    try:
        camera = logging.getLogger("pasr.hardware.camera.real")
        camera.warning("camera %s sent no frame for %.0f s: reconnecting it", 0, 3.0)
        camera.info("camera %s is back", 0, extra={"toast": True})  # good news, asked for
        camera.info("camera 0 opened")  # just information: the terminal only
        flow = logging.getLogger("pasr.apps.reminder.due_flow")
        try:
            raise RuntimeError
        except RuntimeError:
            flow.exception("could not rest the head")
        flow.error("reminder 3 failed", extra={"toast": False})  # shown the pipeline's way
        logging.getLogger("pasr.dashboard.state").error("page failed")  # a toast already
        logging.getLogger("streamlit").error("not the robot")
    finally:
        notices.detach()
    logging.getLogger("pasr.hardware").warning("after the robot stopped")
    found = notices.since(0)
    assert [(notice.kind, notice.message) for notice in found] == [
        ("warning", "Camera 0 sent no frame for 3 s: reconnecting it."),
        ("info", "Camera 0 is back."),
        ("error", "Could not rest the head: an unknown error occurred (RuntimeError)."),
    ]
    assert notices.since(found[0].id) == found[1:]
    assert logging.getLogger("pasr").level == logging.NOTSET  # as it was


def test_an_error_nothing_caught_is_a_notice_too():
    notices = Notices()
    notices.attach()
    try:
        context = {"message": "Exception in callback", "exception": ValueError("bad frame")}
        on_loop_error(None, context)  # type: ignore[arg-type]
        on_loop_error(None, {"message": "Task was destroyed but it is pending!"})  # type: ignore[arg-type]
    finally:
        notices.detach()
    assert [notice.message for notice in notices.since(0)] == [
        "Something in the robot failed: bad frame.",
        "An unknown error occurred (Task was destroyed but it is pending!).",
    ]
