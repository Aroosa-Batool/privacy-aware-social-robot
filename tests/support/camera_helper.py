"""The camera helper (``pasr.hardware.camera.helper``) with a stand-in cv2 and camera names, run
as a process by tests: ``python camera_helper.py PLAN INDEX WIDTH HEIGHT WARMUP STALL [NAME]``.
See ``fakes.FakeCameraHelpers`` for the plan. As it ends, it writes down the captures it made."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/, for fakes

from fakes import FakeCv2  # noqa: E402
from pasr.hardware.camera import helper  # noqa: E402


def main() -> None:
    plan = Path(sys.argv.pop(1))
    counter = plan.with_suffix(".starts")
    number = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(number + 1))
    starts = json.loads(plan.read_text())
    settings = dict(starts[min(number, len(starts) - 1)])
    names = settings.pop("cameras", ["HD Webcam C615"])
    helper.camera_names = lambda: list(names)  # never ask macOS for the real cameras
    if settings.pop("missing", False):
        sys.modules["cv2"] = None  # type: ignore[assignment]
        helper.main()
        return
    exit_at = settings.pop("exit_at_read", None)
    if "stalled_reads" in settings:
        settings["stalls"] = {0: range(*settings.pop("stalled_reads"))}
    for name in ("open_indices", "size"):
        if name in settings:
            settings[name] = tuple(settings[name])
    world = FakeCv2(**settings)
    cv2 = sys.modules["cv2"] = world.module()
    if exit_at is not None:
        read = cv2.VideoCapture.read

        def dying(capture):  # type: ignore[no-untyped-def]
            if capture.reads + 1 >= exit_at:
                os._exit(3)  # a crash: no clean-up, no report
            return read(capture)

        cv2.VideoCapture.read = dying
    try:
        helper.main()
    finally:
        report = [
            {
                "index": c.index,
                "backend": c.backend,
                "props": c.props,
                "reads": c.reads,
                "released": c.released,
            }
            for c in world.captures
        ]
        plan.with_suffix(f".{number}.json").write_text(json.dumps(report))


if __name__ == "__main__":
    main()
