from enum import StrEnum


class DetectionModality(StrEnum):
    """Sensors the robot may use to look for bystanders."""

    NONE = "none"
    AUDIO_ONLY = "audio_only"
    CAMERA_ONLY = "camera_only"
    AUDIO_AND_CAMERA = "audio_and_camera"

    @property
    def listens(self) -> bool:
        """The microphone is used to find bystanders (so the owner's voice must be known)."""
        return self in (DetectionModality.AUDIO_ONLY, DetectionModality.AUDIO_AND_CAMERA)

    @property
    def looks(self) -> bool:
        """The camera is used to find bystanders (so the owner's face must be known)."""
        return self in (DetectionModality.CAMERA_ONLY, DetectionModality.AUDIO_AND_CAMERA)


class DisclosurePolicy(StrEnum):
    """How the robot decides whether to say a sensitive reminder out loud."""

    ALWAYS_DISCLOSE = "always_disclose"
    ALWAYS_ASK = "always_ask"
    ASK_ONCE_PER_BYSTANDER = "ask_once_per_bystander"


class Biometric(StrEnum):
    FACE = "face"
    VOICE = "voice"


class DeliveryChannel(StrEnum):
    SPOKEN = "spoken"
    WATCH = "watch"


class ReminderStatus(StrEnum):
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    SPOKEN = "spoken"
    SENT_TO_WATCH = "sent_to_watch"
    MISSED = "missed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self not in (ReminderStatus.SCHEDULED, ReminderStatus.ACTIVE)


class ReminderOrigin(StrEnum):
    VOICE = "voice"
    DASHBOARD = "dashboard"
    CLI = "cli"
    TEST = "test"
    """The dashboard's Quick test: due in seconds, to watch the pipeline."""


class ConsentSource(StrEnum):
    WATCH = "watch"


class Direction(StrEnum):
    """Where the robot's head (and therefore the head-mounted camera) points."""

    LEFT = "left"
    FRONT = "front"
    RIGHT = "right"


class Pose(StrEnum):
    ATTENTION = "attention"
    REST = "rest"


class FacePose(StrEnum):
    """Which way the robot asks the owner to look while it learns their face."""

    FRONT = "front"
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


class WatchAnswer(StrEnum):
    YES = "yes"
    NO = "no"
    TIMEOUT = "timeout"
