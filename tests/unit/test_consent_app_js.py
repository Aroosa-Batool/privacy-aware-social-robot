"""The real bangle/consent_app.js, run under Node with stand-ins for the Bangle.js globals,
against the exact bytes the PC sends. Skipped where Node is not installed."""

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pasr.hardware.watch.protocol import (
    WatchReply,
    consent_command,
    notify_command,
    parse_reply,
    ping_command,
)
from pasr.paths import PROJECT_ROOT

NODE = shutil.which("node")
HARNESS = Path(__file__).parents[1] / "support" / "consent_app_harness.js"
APP = PROJECT_ROOT / "bangle" / "consent_app.js"
TITLE = "Reminder: Doctor’s “check”, café \\ 9am"


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_the_watch_app_understands_the_pc(tmp_path: Path):
    steps = [
        ("ping", ping_command(1), {}),
        ("yes", consent_command(2, "Someone is here. Say it out loud?", 20), {"press": 1}),
        ("no", consent_command(3, "Say it out loud?", 45), {"press": 0}),
        ("unanswered", consent_command(4, "Say it out loud?", 30), {"expire": True}),
        ("notify", notify_command(5, TITLE), {}),
    ]
    path = tmp_path / "steps.json"
    path.write_text(
        json.dumps(
            [{"name": n, "bytes": base64.b64encode(b).decode(), **extra} for n, b, extra in steps]
        )
    )
    assert NODE is not None
    output = subprocess.run(
        [NODE, str(HARNESS), str(APP), str(path)], capture_output=True, text=True, check=True
    ).stdout
    report = {step["name"]: step for step in json.loads(output)}
    replies = {name: [parse_reply(line) for line in r["replies"]] for name, r in report.items()}

    assert replies["ping"] == [WatchReply("pong", 1, "function")]
    assert replies["yes"] == [WatchReply("answer", 2, "yes")]
    assert report["yes"]["timeoutMs"] == 20_000  # the PC's timeout reaches the app
    assert replies["no"] == [WatchReply("answer", 3, "no")]
    assert report["no"]["timeoutMs"] == 45_000
    assert replies["unanswered"] == []  # the app sends nothing; the PC counts it as a timeout
    assert replies["notify"] == [WatchReply("ack", 5)]
    assert report["notify"]["prompt"] == {"msg": TITLE, "title": "Private note"}
