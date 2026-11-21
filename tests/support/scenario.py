"""Scripted reminder scenarios for the tests: stand-in devices and perception on a virtual clock,
with expectations on the flow and on what was stored. Every file in ``tests/scenarios/data`` is
a test."""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pasr.apps.reminder.due_flow import DueState, FlowOutcome
from pasr.domain.enums import (
    Biometric,
    DeliveryChannel,
    Direction,
    ReminderOrigin,
    ReminderStatus,
    WatchAnswer,
)
from pasr.orchestration.runtime import Runtime
from pasr.settings.loader import as_dict, deep_merge, defaults
from pasr.settings.schema import Settings
from support.clock import VirtualClock
from support.devices import stand_in_hardware
from support.perception import STAND_IN_PERCEPTION
from support.room import OWNER_TAG, Room

SCENARIO_DIR = Path(__file__).parents[1] / "scenarios" / "data"
SCENARIO_START = datetime(2026, 1, 5, 9, 0).astimezone()
SCENARIO_DEFAULTS: dict[str, Any] = {
    "hardware": {"microphone": {"chunk_ms": 250}},
    "perception": STAND_IN_PERCEPTION,
}
"""Stand-in perception, and coarser audio chunks to keep virtual time fast; a scenario may
override them."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VoiceCue(_Strict):
    at_s: float = Field(description="Seconds after the reminder flow starts (wake-up).")
    speaker: str
    seconds: float = 3.0
    text: str | None = None


class WatchCue(_Strict):
    answer: WatchAnswer
    delay_s: float = 3.0


class AwayCue(_Strict):
    """The owner, wearing the watch, is out of Bluetooth range."""

    from_s: float = Field(0.0, description="Seconds after the reminder flow starts (wake-up).")
    back_s: float | None = Field(None, description="Back in range; ``None``: not this episode.")


class ReminderCue(_Strict):
    title: str
    due_in_minutes: float = 10.0
    sensitive: bool | None = None
    """``None`` lets the sensitivity plugin decide."""


class Expectation(_Strict):
    states: list[DueState] | None = None
    channel: DeliveryChannel | None = None
    spoken: int | None = None
    watch_prompts: int | None = None
    camera_used: bool | None = None
    microphone_used: bool | None = None
    remembered_consents: int | None = None
    bystanders_stored: int | None = None
    status: ReminderStatus | None = None


class Episode(_Strict):
    reminder: ReminderCue
    voices: list[VoiceCue] = Field(default_factory=list)
    faces: dict[Direction, list[str]] | None = None
    """Who is visible in each direction; ``None`` keeps the previous episode's room."""
    watch: WatchCue | None = None
    owner_away: AwayCue | None = None
    expect: Expectation = Field(default_factory=Expectation)


class Scenario(_Strict):
    name: str
    description: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)
    enroll: list[Biometric] = Field(default_factory=lambda: [Biometric.FACE, Biometric.VOICE])
    episodes: list[Episode] = Field(min_length=1)


@dataclass(slots=True)
class EpisodeResult:
    outcome: FlowOutcome
    spoken: int
    watch_prompts: int
    camera_used: bool
    microphone_used: bool
    remembered_consents: int
    bystanders_stored: int
    status: ReminderStatus
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclass(slots=True)
class ScenarioResult:
    scenario: Scenario
    episodes: list[EpisodeResult]

    @property
    def passed(self) -> bool:
        return all(e.passed for e in self.episodes)


def scenario_paths(directory: Path = SCENARIO_DIR) -> list[Path]:
    return sorted(directory.glob("*.yaml"))


def load_scenario(path: Path) -> Scenario:
    import yaml

    return Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _check(expect: Expectation, result: EpisodeResult) -> list[str]:
    failures = []
    actual: dict[str, object] = {
        "states": list(result.outcome.states),
        "channel": result.outcome.channel,
        "spoken": result.spoken,
        "watch_prompts": result.watch_prompts,
        "camera_used": result.camera_used,
        "microphone_used": result.microphone_used,
        "remembered_consents": result.remembered_consents,
        "bystanders_stored": result.bystanders_stored,
        "status": result.status,
    }
    for key, wanted in expect.model_dump(exclude_unset=True).items():
        got = actual[key]
        if key == "states":
            got = [str(s) for s in result.outcome.states]
            wanted = [str(s) for s in wanted]
        if got != wanted:
            failures.append(f"{key}: expected {wanted}, got {got}")
    return failures


async def _run_episode(runtime: Runtime, room: Room, episode: Episode) -> EpisodeResult:
    clock = runtime.clock
    room.clear_logs()
    room.utterances.clear()
    room.scripted_answers.clear()
    room.owner_away.clear()
    if episode.faces is not None:
        for direction in Direction:
            room.set_faces(direction, episode.faces.get(direction, []))

    cue = episode.reminder
    reminder = runtime.service.create(
        cue.title,
        clock.now() + timedelta(minutes=cue.due_in_minutes),
        origin=ReminderOrigin.CLI,
        sensitive=cue.sensitive,
    )
    start = max(runtime.reminders.start_time(reminder), clock.now())
    for voice in episode.voices:
        room.speak(
            voice.speaker,
            voice.seconds,
            text=voice.text,
            start=start + timedelta(seconds=voice.at_s),
        )
    if episode.watch is not None:
        room.script_answer(episode.watch.answer, episode.watch.delay_s)
    if (away := episode.owner_away) is not None:
        back = None if away.back_s is None else start + timedelta(seconds=away.back_s)
        room.leave(start + timedelta(seconds=away.from_s), back)

    outcome = await runtime.reminders.wait_for(reminder.id)
    result = EpisodeResult(
        outcome=outcome,
        spoken=sum(1 for line in room.spoken if line.text.startswith("Here is your reminder")),
        watch_prompts=len(room.watch_prompts),
        camera_used=room.camera_opened > 0,
        microphone_used=room.microphone_opened > 0,
        remembered_consents=len(runtime.repos.consents.all(include_revoked=False)),
        bystanders_stored=len(runtime.repos.bystanders.all()),
        status=runtime.repos.reminders.get(reminder.id).status,
    )
    result.failures = _check(episode.expect, result)
    return result


async def _run(scenario: Scenario, settings: Settings, clock: VirtualClock) -> ScenarioResult:
    room = Room(clock)
    mic = settings.hardware.microphone
    runtime = Runtime(
        settings,
        clock=clock,
        hardware=stand_in_hardware(room, clock, sample_rate=mic.sample_rate, chunk_ms=mic.chunk_ms),
        inline_compute=True,
        session_id=f"scenario:{scenario.name}",
    )
    await runtime.start()
    try:
        runtime.enrollment.register("Owner")
        room.stage_owner(voice_seconds=settings.identity.enroll_voice_seconds)
        if Biometric.VOICE in scenario.enroll:
            await runtime.enrollment.enroll_voice()
        if Biometric.FACE in scenario.enroll:
            await runtime.enrollment.enroll_face()
        room.set_faces(Direction.FRONT, [OWNER_TAG])
        results = [await _run_episode(runtime, room, episode) for episode in scenario.episodes]
    finally:
        await runtime.stop()
    return ScenarioResult(scenario, results)


async def run_scenario_async(
    scenario: Scenario, *, base: Settings | None = None, data_dir: Path | None = None
) -> ScenarioResult:
    clock = VirtualClock(SCENARIO_START)
    with tempfile.TemporaryDirectory(prefix="pasr-scenario-") as tmp:
        layers = deep_merge(
            as_dict(base or defaults()),
            SCENARIO_DEFAULTS,
            scenario.settings,
            {"storage": {"data_dir": str(data_dir or tmp)}},
        )
        settings = Settings.model_validate(layers)
        return await clock.drive(_run(scenario, settings, clock))


def run_scenario(
    scenario: Scenario, *, base: Settings | None = None, data_dir: Path | None = None
) -> ScenarioResult:
    return asyncio.run(run_scenario_async(scenario, base=base, data_dir=data_dir))
