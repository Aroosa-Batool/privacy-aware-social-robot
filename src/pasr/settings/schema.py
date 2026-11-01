"""All runtime settings, grouped, each leaf tagged Basic or Advanced.

Defaults live here (the single source of truth); ``config/default.yaml`` is a generated
reference copy (``pasr config dump``) that a test keeps in sync.
"""

from __future__ import annotations

from datetime import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pasr.domain.enums import DetectionModality, Direction, DisclosurePolicy
from pasr.domain.framing import FullView
from pasr.domain.identity import Aggregate
from pasr.domain.timing import LATE_LISTEN_SHARE
from pasr.perception import registry
from pasr.perception.registry import PluginKind
from pasr.settings.tiers import setting


class _Group(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrivacySettings(_Group):
    detection_modality: DetectionModality = setting(
        DetectionModality.AUDIO_AND_CAMERA,
        tier="basic",
        description="Sensors the robot may use to look for bystanders before a sensitive "
        "reminder. With 'audio_only' the camera is never switched on; with 'camera_only' the "
        "microphone is never used for it (reminders set by voice still use it).",
    )
    disclosure_policy: DisclosurePolicy = setting(
        DisclosurePolicy.ALWAYS_ASK,
        tier="basic",
        description="What to do when someone else may hear a sensitive reminder: always say it, "
        "always ask on the watch, or ask once per bystander and remember the answer.",
    )


class ReminderSettings(_Group):
    wake_lead_minutes: float = setting(
        7.0,
        tier="basic",
        ge=0,
        le=120,
        description="Minutes before a sensitive reminder is due that the robot wakes up "
        "to check for bystanders. With the camera only, it does not listen, so it wakes the "
        "listening window later and scans the room at the same moment. With less time than "
        "this left (a quick test, or any reminder set for a few minutes from now), microphone "
        f"and camera split it: {LATE_LISTEN_SHARE:.0%} listening, then a scan.",
    )
    listen_window_minutes: float = setting(
        5.0,
        tier="basic",
        gt=0,
        le=120,
        description="How long the robot listens for voices after waking up.",
    )
    default_time: time = setting(
        time(0, 0),
        tier="basic",
        description="Time used when a reminder names a date but no time.",
    )
    min_listen_seconds: float = setting(
        15.0,
        tier="advanced",
        ge=0,
        le=600,
        description="Minimum listening time when the robot starts late (for example a "
        "reminder added only a minute before it is due).",
    )
    listen_until_due: bool = setting(
        False,
        tier="advanced",
        description="Keep listening right up to the due time instead of stopping after "
        "the listening window.",
    )
    poll_interval_seconds: float = setting(
        10.0,
        tier="advanced",
        gt=0,
        le=600,
        description="How often the scheduler re-reads reminders from the database.",
    )
    missed_grace_minutes: float = setting(
        10.0,
        tier="advanced",
        ge=0,
        description="A reminder found more than this long after its due time is marked "
        "missed instead of delivered late.",
    )
    scan_if_only_owner_heard: bool = setting(
        True,
        tier="advanced",
        description="With the camera allowed, also scan the room when only the owner's voice "
        "was heard (a silent bystander may be present). Off: scan only after silence.",
    )


class ConsentSettings(_Group):
    timeout_seconds: float = setting(
        60.0,
        tier="basic",
        gt=0,
        le=600,
        description="How long to wait for an answer on the watch. No answer means the "
        "reminder goes to the watch and nothing is remembered.",
    )
    prompt_text: str = setting(
        "I noticed someone is with you. Should I say your reminder out loud?",
        tier="advanced",
        min_length=1,
        max_length=160,
        description="Question shown on the watch.",
    )


class IdentitySettings(_Group):
    voice_threshold: float = setting(
        0.35,
        tier="advanced",
        ge=-1,
        le=1,
        description="Cosine similarity at or above which a voice is treated as the owner (or "
        "a known bystander). Model-specific: the default suits speechbrain_ecapa; calibrate "
        "with `pasr calibrate voice`.",
    )
    face_threshold: float = setting(
        0.40,
        tier="advanced",
        ge=-1,
        le=1,
        description="Cosine similarity at or above which a face is treated as the owner (or "
        "a known bystander). Model-specific: the default suits insightface; calibrate with "
        "`pasr calibrate face`.",
    )
    min_voice_segment_seconds: float = setting(
        1.0,
        tier="advanced",
        ge=0,
        le=30,
        description="Shorter speech segments are ignored; they give unreliable embeddings.",
    )
    min_nonowner_segments: int = setting(
        1,
        tier="advanced",
        ge=1,
        le=20,
        description="Speech segments from someone other than the owner needed to decide "
        "that a bystander is present.",
    )
    enroll_face_samples: int = setting(
        5, tier="advanced", ge=1, le=50, description="Face images used to enrol the owner."
    )
    enroll_voice_samples: int = setting(
        3, tier="advanced", ge=1, le=20, description="Speech segments used to enrol the owner."
    )
    enroll_timeout_seconds: float = setting(
        30.0,
        tier="advanced",
        gt=0,
        le=300,
        description="Give up enrolment if not enough samples arrive within this time.",
    )
    aggregate: Aggregate = setting(
        Aggregate.MAX,
        tier="advanced",
        description="Compare with several enrolled samples by the best single match (max) "
        "or by their averaged embedding (mean).",
    )


class VadSettings(_Group):
    speech_threshold: float = setting(
        0.5,
        tier="advanced",
        ge=0,
        le=1,
        description="Voice-activity probability at or above which audio counts as speech.",
    )
    min_speech_ms: int = setting(
        250, tier="advanced", ge=0, le=5000, description="Shorter speech bursts are ignored."
    )
    min_silence_ms: int = setting(
        300, tier="advanced", ge=0, le=5000, description="Silence that ends a speech segment."
    )
    max_segment_seconds: float = setting(
        10.0, tier="advanced", gt=0, le=60, description="Long speech is split into segments."
    )


class FollowSettings(_Group):
    enabled: bool = setting(
        False,
        tier="basic",
        description="Follow a face that is not in full view (cut off, too small, unclear or "
        "turned away) and matches nobody: the head turns and nods towards it until it is, then "
        "the face is compared with the owner and the remembered bystanders. Off: the robot only "
        "looks in the fixed directions.",
    )
    seconds: float = setting(
        5.0,
        tier="basic",
        gt=0,
        le=30,
        description="Longest time the head follows one face; the camera stays on meanwhile. "
        "If the face is still not in full view, its best view so far is compared.",
    )
    min_face_px: int = setting(
        60,
        tier="advanced",
        ge=10,
        le=2000,
        description="A face narrower than this (in camera pixels) is too small to compare well.",
    )
    min_score: float = setting(
        0.7,
        tier="advanced",
        ge=0,
        le=1,
        description="Detector confidence a face needs to count as in full view.",
    )
    edge_margin: float = setting(
        0.03,
        tier="advanced",
        ge=0,
        le=0.3,
        description="A face closer than this share of the image to an edge may be cut off.",
    )
    max_turned: float = setting(
        0.4,
        tier="advanced",
        ge=0,
        le=1,
        description="How far a face may be turned away: 0 faces the camera, about 0.5 is half "
        "profile. Needs a face algorithm that finds the eyes and nose (insightface does).",
    )
    turn_gain: float = setting(
        2.5,
        tier="advanced",
        ge=0,
        le=10,
        description="HEADTURN units the head turns for a face at the side edge of the image "
        "(less for one nearer the centre). Overshoots: lower it; creeps: raise it.",
    )
    nod_gain: float = setting(
        1.5,
        tier="advanced",
        ge=0,
        le=10,
        description="HEADNOD units the head nods for a face at the top or bottom edge of the "
        "image; 0 never nods.",
    )
    invert_turn: bool = setting(
        False,
        tier="advanced",
        description="Turn the other way: switch on if the head turns away from the face.",
    )
    invert_nod: bool = setting(
        False,
        tier="advanced",
        description="Nod the other way: switch on if the head nods away from the face.",
    )

    def full_view(self) -> FullView:
        return FullView(self.min_face_px, self.min_score, self.edge_margin, self.max_turned)


class ScanSettings(_Group):
    positions: list[Direction] = setting(
        tier="basic",
        default_factory=lambda: [Direction.LEFT, Direction.FRONT, Direction.RIGHT],
        min_length=1,
        description="Head directions the robot looks at when scanning the room with the camera.",
    )
    settle_seconds: float = setting(
        0.6, tier="advanced", ge=0, le=10, description="Wait after moving the head before looking."
    )
    frames_per_position: int = setting(
        3, tier="advanced", ge=1, le=30, description="Camera frames analysed per head direction."
    )
    head_speed: int = setting(5, tier="advanced", ge=1, le=10, description="Ohbot motor speed.")
    follow: FollowSettings = Field(default_factory=FollowSettings)


class PluginChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plugin: str
    params: dict[str, Any] = Field(default_factory=dict)


def _choice(plugin: str, description: str) -> Any:
    return setting(
        tier="advanced",
        default_factory=lambda: PluginChoice(plugin=plugin),
        description=description,
    )


class PerceptionSettings(_Group):
    face: PluginChoice = _choice("insightface", "Face detection and embedding.")
    speaker: PluginChoice = _choice("speechbrain_ecapa", "Speaker (voice) embedding.")
    vad: PluginChoice = _choice("silero", "Voice-activity detection.")
    stt: PluginChoice = _choice("faster_whisper", "Speech-to-text for voice reminders.")
    sensitivity: PluginChoice = _choice("zero_shot", "Decides whether a reminder is sensitive.")
    datetime_parser: PluginChoice = _choice("dateparser", "Finds the date and time in a reminder.")

    @model_validator(mode="after")
    def _known_plugins(self) -> PerceptionSettings:
        for kind in PluginKind:
            try:
                registry.get_spec(kind, getattr(self, kind.value).plugin)
            except registry.UnknownPluginError as exc:
                raise ValueError(str(exc)) from exc
        return self

    def choice(self, kind: PluginKind) -> PluginChoice:
        choice: PluginChoice = getattr(self, kind.value)
        return choice


Device = Literal["ohbot", "speaker", "camera", "microphone", "watch"]
DEVICES: tuple[Device, ...] = ("ohbot", "speaker", "camera", "microphone", "watch")


class OhbotSettings(_Group):
    port: str = setting(
        "auto",
        tier="basic",
        description="Serial port of the Ohbot (e.g. /dev/cu.usbmodem101) or 'auto'.",
    )
    turn_left: float = setting(
        2.0, tier="advanced", ge=0, le=10, description="HEADTURN position for 'left'."
    )
    turn_front: float = setting(
        5.0, tier="advanced", ge=0, le=10, description="HEADTURN position for 'front'."
    )
    turn_right: float = setting(
        8.0, tier="advanced", ge=0, le=10, description="HEADTURN position for 'right'."
    )
    move_seconds: float = setting(
        0.8,
        tier="advanced",
        ge=0,
        le=5,
        description="Time a full left-to-right turn takes at speed 5; the head waits this "
        "long (scaled by distance and speed) before the camera looks.",
    )


class SpeakerSettings(_Group):
    backend: Literal["ohbot", "macos_say"] = setting(
        "ohbot",
        tier="advanced",
        description="Ohbot text-to-speech with lip sync, or plain macOS 'say'.",
    )
    voice: str | None = setting(
        None, tier="advanced", description="macOS voice name for the 'macos_say' backend."
    )
    output_device: str | None = setting(
        None,
        tier="basic",
        description="Speaker the robot's voice plays on, e.g. 'MacBook Air Speakers' (see "
        "`pasr hardware list`). Empty uses the macOS default output, which AirPods or a "
        "display can take over.",
    )


class CameraSettings(_Group):
    name: str | None = setting(
        "C615",
        tier="basic",
        description="Part of the head camera's name, e.g. 'C615' (see `pasr hardware list`). "
        "The camera is found by name each time it opens, so the laptop's own camera or an "
        "iPhone is never used instead; empty uses the index (macOS only finds names).",
    )
    index: int = setting(
        0, tier="basic", ge=0, le=16, description="OpenCV camera index, used when name is empty."
    )
    width: int = setting(640, tier="advanced", ge=160, le=3840, description="Capture width.")
    height: int = setting(480, tier="advanced", ge=120, le=2160, description="Capture height.")
    source: Literal["device", "images"] = setting(
        "device",
        tier="advanced",
        description="'device' is the USB camera; 'images' reads a researcher-supplied folder "
        "of images in name order (research use; nothing is ever written).",
    )
    image_dir: Path | None = setting(
        None, tier="advanced", description="Folder of images for source 'images'."
    )
    warmup_frames: int = setting(
        5, tier="advanced", ge=0, le=30, description="Frames discarded after opening the camera."
    )

    @model_validator(mode="after")
    def _images_need_a_folder(self) -> CameraSettings:
        if self.source == "images" and self.image_dir is None:
            raise ValueError("hardware.camera.image_dir is required with source 'images'")
        return self


class MicrophoneSettings(_Group):
    device: str | None = setting(
        None,
        tier="basic",
        description="Microphone the robot listens with, e.g. 'MacBook Air Microphone' (see the "
        "Setup page). Empty uses the macOS default input, which AirPods or an iPhone can take "
        "over.",
    )
    sample_rate: int = setting(
        16000, tier="advanced", ge=8000, le=48000, description="Audio sample rate in Hz."
    )
    chunk_ms: int = setting(
        32, tier="advanced", ge=10, le=1000, description="Audio chunk length fed to the VAD."
    )
    source: Literal["device", "wav"] = setting(
        "device",
        tier="advanced",
        description="'device' is the microphone; 'wav' plays a researcher-supplied WAV file "
        "(mono or stereo, at sample_rate) as if it were the room.",
    )
    wav_path: Path | None = setting(None, tier="advanced", description="WAV file for source 'wav'.")
    wav_realtime: bool = setting(
        True,
        tier="advanced",
        description="Pace WAV chunks in real time; off delivers them as fast as possible.",
    )

    @model_validator(mode="after")
    def _wav_needs_a_file(self) -> MicrophoneSettings:
        if self.source == "wav" and self.wav_path is None:
            raise ValueError("hardware.microphone.wav_path is required with source 'wav'")
        return self


class WatchSettings(_Group):
    name_prefix: str = setting(
        "Bangle.js", tier="basic", description="Bluetooth name prefix used to find the watch."
    )
    address: str | None = setting(
        None,
        tier="advanced",
        description="Cached Bluetooth address (a CoreBluetooth UUID on macOS).",
    )
    reconnect_attempts: int = setting(
        3, tier="advanced", ge=0, le=20, description="Reconnect attempts before giving up."
    )
    scan_timeout_seconds: float = setting(
        10.0, tier="advanced", gt=0, le=60, description="How long one Bluetooth scan may take."
    )


class HardwareSettings(_Group):
    ohbot: OhbotSettings = Field(default_factory=OhbotSettings)
    speaker: SpeakerSettings = Field(default_factory=SpeakerSettings)
    camera: CameraSettings = Field(default_factory=CameraSettings)
    microphone: MicrophoneSettings = Field(default_factory=MicrophoneSettings)
    watch: WatchSettings = Field(default_factory=WatchSettings)
    executor_workers: int = setting(
        4, tier="advanced", ge=1, le=32, description="Threads for blocking hardware and ML calls."
    )


class StorageSettings(_Group):
    data_dir: Path = setting(
        Path("data"),
        tier="advanced",
        description="Directory for the database and local settings (relative to the project).",
    )
    event_log_retention_days: int = setting(
        0,
        tier="advanced",
        ge=0,
        description="Delete event-log entries older than this at start-up; 0 keeps them.",
    )
    models_dir: Path = setting(
        Path("models"),
        tier="advanced",
        description="Directory for downloaded model weights (relative to the project). Must not "
        "be inside data_dir, which holds nothing but the database.",
    )

    @model_validator(mode="after")
    def _models_outside_data(self) -> StorageSettings:
        data, models = self.data_dir.resolve(), self.models_dir.resolve()
        if models == data or data in models.parents:
            raise ValueError("storage.models_dir must not be inside storage.data_dir")
        return self


class LoggingSettings(_Group):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = setting(
        "INFO", tier="advanced", description="Console log level."
    )


class LiveViewSettings(_Group):
    enabled: bool = setting(
        False,
        tier="advanced",
        description="Open a window on the laptop while the robot listens, scans, enrols or "
        "calibrates (whether it runs from the dashboard or a terminal): the camera frames it "
        "analyses with each face labelled (owner or someone else), the microphone level and "
        "each voice match. Nothing is stored, but faces of people nearby appear on screen: use "
        "it for development, or with participants' consent.",
    )


class Settings(BaseModel):
    """Effective settings. ``pasr.settings.loader.load_settings`` layers them (lowest → highest):
    defaults, profile YAML, ``<data_dir>/settings.json`` overrides, ``.env`` and ``PASR__…``
    environment variables, explicit command-line values."""

    model_config = ConfigDict(extra="forbid")

    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    reminder: ReminderSettings = Field(default_factory=ReminderSettings)
    consent: ConsentSettings = Field(default_factory=ConsentSettings)
    identity: IdentitySettings = Field(default_factory=IdentitySettings)
    vad: VadSettings = Field(default_factory=VadSettings)
    scan: ScanSettings = Field(default_factory=ScanSettings)
    perception: PerceptionSettings = Field(default_factory=PerceptionSettings)
    hardware: HardwareSettings = Field(default_factory=HardwareSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    live_view: LiveViewSettings = Field(default_factory=LiveViewSettings)


STRUCTURAL_GROUPS = frozenset({"perception", "hardware", "storage"})
"""Groups whose changes need a runtime restart; other groups apply live."""
