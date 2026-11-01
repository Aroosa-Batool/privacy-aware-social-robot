"""Local model weights: what is installed, what is downloaded, and a deliberate one-time
download (the only network access in the system)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pasr.paths import resolve
from pasr.perception import registry
from pasr.perception.bundle import PerceptionBundle
from pasr.perception.registry import PluginKind, PluginSpec
from pasr.settings.schema import PluginChoice, Settings

WEIGHT_DIRS: dict[tuple[PluginKind, str], Path | None] = {
    (PluginKind.FACE, "insightface"): Path("insightface") / "models" / "buffalo_l",
    (PluginKind.SPEAKER, "speechbrain_ecapa"): Path("speechbrain") / "spkrec-ecapa-voxceleb",
    (PluginKind.SPEAKER, "resemblyzer"): None,  # bundled with the package
    (PluginKind.VAD, "silero"): None,
    (PluginKind.STT, "faster_whisper"): Path("faster-whisper"),
    (PluginKind.SENSITIVITY, "zero_shot"): Path("transformers"),
}
DOWNLOADABLE = (
    PluginKind.FACE,
    PluginKind.SPEAKER,
    PluginKind.VAD,
    PluginKind.STT,
    PluginKind.SENSITIVITY,
)


@dataclass(frozen=True, slots=True)
class ModelStatus:
    kind: PluginKind
    plugin: str
    status: str
    """``available`` or ``missing <modules>`` (from the registry)."""
    weights: str
    """``bundled``, ``present`` or ``not downloaded``."""
    configured: bool


def ml_specs() -> list[PluginSpec]:
    return [s for s in registry.specs() if (s.kind, s.name) in WEIGHT_DIRS]


def model_status(settings: Settings) -> list[ModelStatus]:
    models_dir = resolve(settings.storage.models_dir)
    rows = []
    for spec in ml_specs():
        sub = WEIGHT_DIRS[(spec.kind, spec.name)]
        if sub is None:
            weights = "bundled"
        else:
            folder = models_dir / sub
            weights = "present" if folder.is_dir() and any(folder.iterdir()) else "not downloaded"
        configured = settings.perception.choice(spec.kind).plugin == spec.name
        rows.append(ModelStatus(spec.kind, spec.name, spec.status, weights, configured))
    return rows


def download_model(settings: Settings, kind: PluginKind, plugin: str) -> None:
    """Load (and thereby download) one model, in use or not. The one in use keeps its settings
    (e.g. which Whisper size); another one starts from its defaults."""
    chosen = settings.perception.choice(kind)
    choice = chosen if chosen.plugin == plugin else PluginChoice(plugin=plugin)
    perception = settings.perception.model_copy(update={kind.value: choice})
    bundle = PerceptionBundle(perception, models_dir=resolve(settings.storage.models_dir))
    warm_up = getattr(getattr(bundle, kind.value), "warm_up", None)
    if warm_up is not None:
        warm_up()


def download(settings: Settings, kinds: tuple[PluginKind, ...] = DOWNLOADABLE) -> list[str]:
    """Load (and thereby download) the configured plugin of each kind. Returns their names."""
    bundle = PerceptionBundle(settings.perception, models_dir=resolve(settings.storage.models_dir))
    loaded = []
    for kind in kinds:
        plugin = getattr(bundle, kind.value)
        warm_up = getattr(plugin, "warm_up", None)
        if warm_up is not None:
            warm_up()
            loaded.append(f"{kind.value}: {bundle.plugin_name(kind)}")
    return loaded
