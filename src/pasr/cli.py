"""The ``pasr`` command line."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from pasr.apps.reminder.cli import app as reminder_app
from pasr.domain.calibration import Calibration, histogram
from pasr.domain.calibration import calibrate as calibrate_scores
from pasr.domain.enums import Biometric, DetectionModality, DisclosurePolicy
from pasr.hardware import discovery
from pasr.hardware.camera.real import ImageFolderCamera
from pasr.hardware.check import check_devices
from pasr.hardware.microphone.real import WavFileMicrophone
from pasr.hardware.protocols import HardwareNotAvailableError
from pasr.orchestration.calibration import THRESHOLD_FIELDS, VOICE_SAMPLES, VOICE_SECONDS
from pasr.orchestration.enrollment import (
    FACE_GUIDANCE,
    VOICE_GUIDANCE,
    VOICE_PASSAGE,
    EnrollmentError,
    EnrollProgress,
)
from pasr.orchestration.events import Event, EventType
from pasr.orchestration.lock import RuntimeBusyError, RuntimeLock
from pasr.orchestration.offline import open_offline
from pasr.orchestration.runtime import Runtime, setup_warnings
from pasr.paths import PROJECT_ROOT, resolve
from pasr.perception import models as model_weights
from pasr.perception.registry import PluginKind, PluginUnavailableError, recommended_threshold
from pasr.settings.loader import (
    as_dict,
    clear_overrides,
    defaults,
    diff,
    dump_yaml,
    load_settings,
    update_overrides,
)
from pasr.settings.schema import DEVICES, Device, Settings
from pasr.settings.tiers import TIERS, Tier, visible
from pasr.storage.reset import reset as reset_storage

app = typer.Typer(
    help="Privacy-aware social robot: Ohbot + Bangle.js research platform.",
    no_args_is_help=True,
)
app.add_typer(reminder_app, name="reminder")
consent_app = typer.Typer(help="Remembered bystander consent.", no_args_is_help=True)
config_app = typer.Typer(help="Show and change settings.", no_args_is_help=True)
hardware_app = typer.Typer(help="Find and test the real devices.", no_args_is_help=True)
models_app = typer.Typer(
    help="Local model weights. Downloading is the only time the robot uses the network.",
    no_args_is_help=True,
)
app.add_typer(consent_app, name="consent")
app.add_typer(config_app, name="config")
app.add_typer(hardware_app, name="hardware")
app.add_typer(models_app, name="models")

ProfileOption = Annotated[
    Path | None, typer.Option("--profile", help="YAML settings profile to layer under overrides.")
]
LiveViewOption = Annotated[
    bool,
    typer.Option(
        "--live-view",
        help="Show what the robot recognises in a window while it listens, scans, enrols or "
        "calibrates (live_view.enabled, for this run only).",
    ),
]


def _live_view(on: bool) -> dict[str, Any] | None:
    return {"live_view": {"enabled": True}} if on else None


def _robot(settings: Settings, session_id: str | None = None) -> Runtime:
    """A runtime on the robot that shows the live view in a window while live_view.enabled."""
    if settings.live_view.enabled:
        typer.echo("Live view on: a window opens when the robot listens, scans or captures.")
    return Runtime(settings, session_id=session_id, live_window=True)


def _fail(message: str) -> typer.Exit:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return typer.Exit(1)


def _configure_logging(settings: Settings, verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else settings.logging.level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# --- run ---------------------------------------------------------------------------------


def _print_event(event: Event) -> None:
    if event.type is EventType.FLOW_STATE:
        typer.echo(
            f"{event.ts:%H:%M:%S}  reminder #{event.reminder_id}: "
            f"{event.state_from} → {event.state_to}  ({event.data.get('reason', '')})"
        )
    elif event.type in (EventType.CONSENT_REQUESTED, EventType.REMINDER_DELIVERED):
        details = ", ".join(f"{k}={v}" for k, v in event.data.items())
        typer.echo(f"{event.ts:%H:%M:%S}  {event.type.value} {details}")


async def _run_forever(settings: Settings) -> None:
    runtime = _robot(settings)
    runtime.bus.subscribe(_print_event)
    await runtime.start()
    snapshot = runtime.snapshot()
    for warning in snapshot.warnings:
        typer.secho(f"! {warning}", fg=typer.colors.YELLOW)
    typer.echo("Robot running. Press Ctrl+C to stop.")
    try:
        await asyncio.Event().wait()
    finally:
        await runtime.stop()


@app.command()
def run(
    profile: ProfileOption = None,
    live_view: LiveViewOption = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Run the robot (scheduler + reminder flows) until Ctrl+C."""
    settings = load_settings(profile=profile, explicit=_live_view(live_view))
    _configure_logging(settings, verbose)
    try:
        asyncio.run(_run_forever(settings))
    except KeyboardInterrupt:
        typer.echo("Stopped.")
    except (HardwareNotAvailableError, RuntimeBusyError) as exc:
        raise _fail(str(exc)) from exc


@app.command()
def dashboard(
    port: Annotated[int, typer.Option(help="Port for the web dashboard.")] = 8501,
) -> None:
    """Open the researcher dashboard (Streamlit)."""
    if find_spec("streamlit") is None:
        raise _fail("The dashboard needs streamlit: uv sync")
    script = Path(__file__).parent / "dashboard" / "server.py"  # the pages, and the tab's icon
    command = [sys.executable, "-m", "streamlit", "run", str(script), "--server.port", str(port)]
    raise typer.Exit(subprocess.call(command, cwd=PROJECT_ROOT))


# --- setup -------------------------------------------------------------------------------


def _choose[E: (DetectionModality, DisclosurePolicy)](
    question: str, options: dict[E, str], current: E
) -> E:
    typer.echo(question)
    choices = list(options)
    for number, (value, label) in enumerate(options.items(), start=1):
        marker = " (current)" if value is current else ""
        typer.echo(f"  {number}. {label}{marker}")
    picked = int(typer.prompt("Choose", default=choices.index(current) + 1, type=int))
    if not 1 <= picked <= len(choices):
        raise _fail("No such option.")
    return choices[picked - 1]


MODALITY_QUESTION = "How may the robot check whether someone else is in the room?"
MODALITY_OPTIONS = {
    DetectionModality.AUDIO_ONLY: "Microphone only , the camera is never used for this",
    DetectionModality.CAMERA_ONLY: "Camera only , the microphone is never used for this",
    DetectionModality.AUDIO_AND_CAMERA: "Microphone and camera",
    DetectionModality.NONE: "Neither , do not detect bystanders",
}
POLICY_QUESTION = "How should the robot handle sensitive reminders?"
POLICY_OPTIONS = {
    DisclosurePolicy.ALWAYS_DISCLOSE: "Always say them, whoever is present",
    DisclosurePolicy.ALWAYS_ASK: "Always ask me on the watch first when someone else is present",
    DisclosurePolicy.ASK_ONCE_PER_BYSTANDER: "Ask the first time I see a person; "
    "remember my answer for that person",
}


def _progress_line(progress: EnrollProgress) -> None:
    detail = f"{progress.collected}/{progress.wanted} {progress.unit}"
    if progress.pose is not None:
        detail += f" · pose: {progress.pose}"
    if progress.modality is Biometric.FACE:
        detail += (
            f" · {progress.frames} frames (no face in {progress.no_face}, "
            f"several in {progress.many_faces}, not usable {progress.unusable})"
        )
    else:
        detail += f" · {progress.frames} speech segments heard"
    typer.echo(f"\r  {progress.modality.value}: {detail} · {progress.elapsed_s:.0f} s   ", nl=False)


async def _enroll(settings: Settings, *, face: bool, voice: bool) -> list[str]:
    """Enrol on the robot's camera and microphone, with guidance and a progress line."""
    runtime = _robot(settings, session_id="setup")
    done = []
    await runtime.start(run_apps=False)
    try:
        if voice:
            typer.echo(VOICE_GUIDANCE.format(seconds=settings.identity.enroll_voice_seconds))
            typer.echo(f"\n{VOICE_PASSAGE}\n")
            count = await runtime.enrollment.enroll_voice(progress=_progress_line)
            typer.echo("")
            done.append(f"voice: {count} samples")
        if face:
            typer.echo(FACE_GUIDANCE)
            count = await runtime.enrollment.enroll_face(progress=_progress_line)
            typer.echo("")
            identity = settings.identity
            wanted = identity.enroll_face_samples * len(identity.enroll_face_poses)
            missed = "" if count >= wanted else f" of {wanted} (some poses missed: run it again)"
            done.append(f"face: {count} samples{missed}")
    finally:
        await runtime.stop()
    return done


@app.command()
def setup(
    name: Annotated[str | None, typer.Option(help="Owner's name.")] = None,
    modality: Annotated[DetectionModality | None, typer.Option(help=MODALITY_QUESTION)] = None,
    policy: Annotated[DisclosurePolicy | None, typer.Option(help=POLICY_QUESTION)] = None,
    enroll: Annotated[bool, typer.Option(help="Enrol the owner's face and voice.")] = True,
    face: Annotated[bool, typer.Option("--face/--no-face", help="Enrol the face.")] = True,
    voice: Annotated[bool, typer.Option("--voice/--no-voice", help="Enrol the voice.")] = True,
    live_view: LiveViewOption = False,
) -> None:
    """First-time setup: register the owner, enrol face and voice, answer two questions."""
    settings = load_settings(explicit=_live_view(live_view))
    offline = open_offline(settings, session_id="setup")
    if offline.runtime_running:
        raise _fail("Stop the running robot (or dashboard runtime) before setup.")
    owner = offline.repos.owner.get()
    name = name or typer.prompt("Owner's name", default=owner.display_name if owner else None)
    offline.repos.owner.save(name, offline.clock.now())

    planned = modality or settings.privacy.detection_modality
    if enroll and face and planned is DetectionModality.AUDIO_ONLY:
        typer.echo("Detection is microphone-only: skipping face enrolment.")
        face = False
    if enroll and voice and planned is DetectionModality.CAMERA_ONLY:
        typer.echo("Detection is camera-only: skipping voice enrolment.")
        voice = False
    if enroll and (face or voice):  # nothing left to enrol: the robot is not started
        what = " and ".join(w for w, on in (("voice", voice), ("face", face)) if on)
        typer.echo(f"Enrolling your {what}…")
        try:
            for line in asyncio.run(_enroll(settings, face=face, voice=voice)):
                typer.echo(f"  {line}")
        except EnrollmentError as exc:
            raise _fail(f"Enrolment failed: {exc}") from exc
        except (HardwareNotAvailableError, RuntimeBusyError) as exc:
            raise _fail(str(exc)) from exc

    modality = modality or _choose(
        MODALITY_QUESTION, MODALITY_OPTIONS, settings.privacy.detection_modality
    )
    policy = policy or _choose(POLICY_QUESTION, POLICY_OPTIONS, settings.privacy.disclosure_policy)
    update_overrides(
        settings.storage.data_dir,
        {"privacy": {"detection_modality": modality.value, "disclosure_policy": policy.value}},
    )
    settings = load_settings()
    enrolled = {m.value: n for m, (n, _) in offline.repos.owner.enrollment().items()}
    typer.echo(f"Done. Owner: {name}; detection: {modality.value}; policy: {policy.value}.")
    for warning in setup_warnings(settings, name, enrolled):
        typer.secho(f"! {warning}", fg=typer.colors.YELLOW)


# --- calibration -------------------------------------------------------------------------


def _print_calibration(
    modality: Biometric, genuine: list[float], impostor: list[float], result: Calibration
) -> None:
    edges, owner_counts = histogram(genuine)
    _, other_counts = histogram(impostor)
    typer.echo(f"\n{modality.value} similarity to the enrolled owner   owner | others")
    for edge, mine, theirs in zip(edges, owner_counts, other_counts, strict=True):
        if mine or theirs:
            typer.echo(f"  {edge:+.2f}  {'#' * mine:<20} | {'#' * theirs}")
    g = result.genuine
    typer.echo(f"owner:  {g.count} samples, min {g.minimum:.2f}, median {g.median:.2f}")
    if result.impostor:
        i = result.impostor
        typer.echo(f"others: {i.count} samples, max {i.maximum:.2f}, median {i.median:.2f}")
    typer.echo(f"suggested identity.{THRESHOLD_FIELDS[modality]}: {result.suggested:.2f}")
    if result.eer is not None:
        typer.echo(
            f"at that threshold: false accept {result.far_at_suggested:.0%}, "
            f"false reject {result.frr_at_suggested:.0%} (EER {result.eer:.0%})"
        )
    colour = {"good": typer.colors.GREEN, "fair": typer.colors.YELLOW}.get(
        result.verdict.value, typer.colors.RED
    )
    typer.secho(f"verdict: {result.verdict.value}", fg=colour)
    for note in result.notes:
        typer.secho(f"  note: {note}", fg=typer.colors.YELLOW)


async def _calibrate(
    settings: Settings,
    modality: Biometric,
    *,
    others: int,
    samples: int,
    files: list[Path],
    fast: bool,
) -> tuple[list[float], list[float], Calibration, Runtime]:
    runtime = _robot(settings, session_id="calibrate")
    identity = settings.identity
    mic = settings.hardware.microphone

    def source(path: Path) -> Any:
        if modality is Biometric.VOICE:
            return WavFileMicrophone(
                path, mic.sample_rate, mic.chunk_ms, clock=runtime.clock, realtime=not fast
            )
        return ImageFolderCamera(path, clock=runtime.clock)

    async def capture(person: str, path: Path | None) -> list[float]:
        if path is None:
            action = (
                "do what the robot says (look straight, then turn and tilt your head)"
                if modality is Biometric.FACE
                else "speak for a few seconds"
            )
            typer.prompt(f"{person}: press Enter, then {action}", default="")
        try:
            if modality is Biometric.VOICE:
                return await runtime.calibration.score_voice(
                    samples=samples,
                    timeout_s=VOICE_SECONDS,
                    microphone=source(path) if path else None,
                    progress=_progress_line,
                )
            return await runtime.calibration.score_face(
                samples=samples,
                timeout_s=identity.enroll_face_pose_seconds,
                guided=path is None,
                camera=source(path) if path else None,
                progress=_progress_line,
            )
        finally:
            typer.echo("")

    async def run() -> tuple[list[float], list[float], Calibration, Runtime]:
        await runtime.start(run_apps=False)
        try:
            if files:
                genuine = await capture("owner", files[0])
                impostor = [s for path in files[1:] for s in await capture("other", path)]
            else:
                genuine = await capture("Owner", None)
                impostor = []
                for k in range(1, others + 1):
                    impostor += await capture(f"Other person {k}/{others}", None)
            kind = PluginKind.FACE if modality is Biometric.FACE else PluginKind.SPEAKER
            ceiling = recommended_threshold(kind, settings.perception.choice(kind).plugin)
            result = calibrate_scores(genuine, impostor or None, ceiling=ceiling)
            return genuine, impostor, result, runtime
        finally:
            await runtime.stop()

    return await run()


@app.command()
def calibrate(
    modality: Annotated[Biometric, typer.Argument(help="face or voice")],
    others: Annotated[
        int, typer.Option(help="How many other people to capture live (0 = owner only).")
    ] = 1,
    samples: Annotated[
        int | None,
        typer.Option(
            help=f"Samples per person; live faces: per pose (default: faces as enrolment, "
            f"{VOICE_SAMPLES} speech segments)."
        ),
    ] = None,
    apply: Annotated[bool, typer.Option("--apply", help="Save the suggested threshold.")] = False,
    wav: Annotated[
        list[Path] | None,
        typer.Option("--wav", help="Voice from WAV files: first the owner, then others."),
    ] = None,
    images: Annotated[
        list[Path] | None,
        typer.Option("--images", help="Faces from image folders: first the owner, then others."),
    ] = None,
    fast: Annotated[
        bool, typer.Option("--fast", help="Do not pace WAV files in real time.")
    ] = False,
    live_view: LiveViewOption = False,
) -> None:
    """Measure owner-vs-others similarity with the current plugins and suggest a threshold.
    Nothing but the chosen threshold is stored."""
    settings = load_settings(explicit=_live_view(live_view))
    files = list(wav or []) if modality is Biometric.VOICE else list(images or [])
    if (wav and modality is Biometric.FACE) or (images and modality is Biometric.VOICE):
        raise _fail("--wav goes with 'voice' and --images with 'face'.")
    identity = settings.identity
    count = samples or (
        VOICE_SAMPLES
        if modality is Biometric.VOICE
        else identity.enroll_face_samples * len(identity.enroll_face_poses)
        if files
        else identity.enroll_face_samples
    )
    try:
        genuine, impostor, result, runtime = asyncio.run(
            _calibrate(settings, modality, others=others, samples=count, files=files, fast=fast)
        )
    except (EnrollmentError, HardwareNotAvailableError, RuntimeBusyError, ValueError) as exc:
        raise _fail(f"Calibration failed: {exc}") from exc
    _print_calibration(modality, genuine, impostor, result)
    if apply or typer.confirm("Apply the suggested threshold?", default=False):
        runtime.calibration.apply(modality, result.suggested, result)
        typer.echo(
            f"Saved identity.{THRESHOLD_FIELDS[modality]} = {result.suggested:.2f}"
            " (a running robot applies it on restart)."
        )


# --- hardware ----------------------------------------------------------------------------


@hardware_app.command("check")
def hardware_check(
    device: Annotated[
        list[str] | None,
        typer.Option("--device", "-d", help=f"Only these devices ({', '.join(DEVICES)})."),
    ] = None,
    profile: ProfileOption = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Connect to each device once: move the head, speak, grab a frame, listen, ping the
    watch."""
    settings = load_settings(profile=profile)
    _configure_logging(settings, verbose)
    unknown = [d for d in device or [] if d not in DEVICES]
    if unknown:
        raise _fail(f"Unknown device(s): {', '.join(unknown)}. Known: {', '.join(DEVICES)}.")
    only: list[Device] = [d for d in DEVICES if device is None or d in device]
    try:
        with RuntimeLock(resolve(settings.storage.data_dir)):
            reports = asyncio.run(check_devices(settings, only=only))
    except RuntimeBusyError as exc:
        raise _fail(str(exc)) from exc
    for report in reports:
        colour = typer.colors.GREEN if report.ok else typer.colors.RED
        status = "ok  " if report.ok else "FAIL"
        typer.secho(f"{status} {report.device:<11}{report.detail}", fg=colour)
    if any(not r.ok for r in reports):
        raise typer.Exit(1)


@hardware_app.command("list")
def hardware_list(
    scan_seconds: Annotated[
        float, typer.Option(help="How long to scan for the watch over Bluetooth.")
    ] = 5.0,
) -> None:
    """List serial ports, microphones, cameras and nearby watches to fill in the settings."""
    settings = load_settings()

    async def gather() -> list[discovery.Discovery]:
        return [
            discovery.serial_ports(),
            discovery.microphones(),
            discovery.audio_outputs(),
            await discovery.cameras(),
            await discovery.watches(settings.hardware.watch.name_prefix, scan_seconds),
        ]

    try:
        with RuntimeLock(resolve(settings.storage.data_dir)):
            found_all = asyncio.run(gather())
    except RuntimeBusyError as exc:
        raise _fail(str(exc)) from exc
    for found in found_all:
        typer.secho(found.kind, bold=True)
        for item in found.items:
            typer.echo(f"  {item}")
        if found.hint:
            typer.secho(f"  ({found.hint})", fg=typer.colors.YELLOW)


# --- models ------------------------------------------------------------------------------


@models_app.command("status")
def models_status() -> None:
    """Which ML plugins are installed, and whose weights are already downloaded."""
    settings = load_settings()
    typer.echo(f"models directory: {resolve(settings.storage.models_dir)}")
    for row in model_weights.model_status(settings):
        marker = "*" if row.configured else " "
        typer.echo(f"{marker} {row.kind.value:<8} {row.plugin:<18} {row.status:<28} {row.weights}")
    typer.echo("(* = selected in perception settings)")


@models_app.command("download")
def models_download(
    kind: Annotated[
        list[PluginKind] | None,
        typer.Option("--kind", "-k", help="Only these stages (face, speaker, vad)."),
    ] = None,
) -> None:
    """Download and load the configured face, speaker and VAD models once, so later runs
    work offline."""
    settings = load_settings()
    kinds = tuple(kind) if kind else model_weights.DOWNLOADABLE
    try:
        loaded = model_weights.download(settings, kinds)
    except PluginUnavailableError as exc:
        raise _fail(str(exc)) from exc
    for line in loaded:
        typer.echo(f"ready: {line}")


# --- consent -----------------------------------------------------------------------------


@consent_app.command("list")
def consent_list() -> None:
    """Show remembered consent decisions (newest first)."""
    offline = open_offline(load_settings(), session_id="cli")
    labels = {b.id: b.label for b in offline.repos.bystanders.all()}
    consents = offline.repos.consents.all()
    if not consents:
        typer.echo("No consent decisions.")
    for c in consents:
        state = f"revoked {c.revoked_at:%Y-%m-%d %H:%M}" if c.revoked_at else "active"
        answer = "yes" if c.allowed else "no"
        who = labels.get(c.bystander_id, c.bystander_id)
        typer.echo(f"#{c.id:<4} {c.decided_at:%Y-%m-%d %H:%M}  {who:<8} {answer:<4} {state}")


@consent_app.command("delete-last")
def consent_delete_last(
    hard: Annotated[bool, typer.Option(help="Delete the record instead of revoking it.")] = False,
) -> None:
    """Forget the most recent remembered consent decision."""
    offline = open_offline(load_settings(), session_id="cli")
    revoked = offline.repos.consents.revoke_last(offline.clock.now(), hard=hard)
    if revoked is None:
        typer.echo("No remembered consent to delete.")
        return
    verb = "Deleted" if hard else "Revoked"
    typer.echo(f"{verb} consent #{revoked.id} ({'yes' if revoked.allowed else 'no'}).")
    offline.bus.emit(EventType.CONSENT_REVOKED, bystander_id=revoked.bystander_id)


# --- reset -------------------------------------------------------------------------------


@app.command()
def reset(
    delete_owner: Annotated[
        bool | None,
        typer.Option(
            "--delete-owner/--keep-owner",
            help="Also delete the owner's face and voice data, name and reminders.",
        ),
    ] = None,
    purge_log: Annotated[bool, typer.Option(help="Also delete the research event log.")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")] = False,
) -> None:
    """Reset the app: always removes bystanders, consents and preferences."""
    settings = load_settings()
    offline = open_offline(settings, session_id="cli")
    if offline.runtime_running:
        raise _fail("Stop the running robot (or dashboard runtime) before resetting.")
    if delete_owner is None:
        delete_owner = typer.confirm("Also delete the owner's face and voice data?", default=False)
    what = "everything, including the owner" if delete_owner else "settings, bystanders, consents"
    if not yes:
        typer.confirm(f"This deletes {what}. Continue?", abort=True)
    summary = reset_storage(
        offline.db,
        resolve(settings.storage.data_dir),
        delete_owner=delete_owner,
        purge_log=purge_log,
    )
    removed = ", ".join(f"{table}: {n}" for table, n in summary.deleted_rows.items())
    typer.echo(f"Reset done. Deleted rows , {removed}.")
    if summary.settings_cleared:
        typer.echo("Preferences restored to defaults.")


# --- config ------------------------------------------------------------------------------


@config_app.command("show")
def config_show(
    level: Annotated[str, typer.Option(help="basic or advanced")] = "basic",
) -> None:
    """Show effective settings up to a detail level."""
    if level not in TIERS:
        raise _fail(f"Level must be one of {', '.join(TIERS)}.")
    settings = load_settings()
    for group_name in Settings.model_fields:
        rows = _visible_rows(getattr(settings, group_name), level)
        if rows:
            typer.secho(group_name, bold=True)
            for key, value in rows:
                typer.echo(f"  {key} = {value}")


def _visible_rows(model: Any, tier: Tier, prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    plain = model.model_dump(mode="json")
    for name, field in type(model).model_fields.items():
        value = getattr(model, name)
        if hasattr(value, "model_fields") and field.json_schema_extra is None:
            rows += _visible_rows(value, tier, f"{prefix}{name}.")
        elif visible(field, tier):
            rows.append((prefix + name, plain[name]))
    return rows


@config_app.command("dump")
def config_dump(
    defaults_only: Annotated[
        bool, typer.Option("--defaults", help="Built-in defaults instead of effective settings.")
    ] = False,
) -> None:
    """Print settings as YAML (usable as a --profile)."""
    typer.echo(dump_yaml(defaults() if defaults_only else load_settings()), nl=False)


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Dotted key, e.g. privacy.disclosure_policy")],
    value: Annotated[str, typer.Argument(help="Value (YAML syntax: 5, true, [left, right])")],
) -> None:
    """Change one setting (saved in the data directory)."""
    parts = key.split(".")
    change: dict[str, Any] = {parts[-1]: yaml.safe_load(value)}
    for part in reversed(parts[:-1]):
        change = {part: change}
    settings = load_settings()
    try:
        update_overrides(settings.storage.data_dir, change)
    except ValueError as exc:
        raise _fail(f"Invalid setting: {exc}") from exc
    typer.echo(f"{key} = {value}")


@config_app.command("reset")
def config_reset() -> None:
    """Restore default settings (keeps the owner, reminders and bystanders)."""
    settings = load_settings()
    removed = clear_overrides(settings.storage.data_dir)
    typer.echo("Settings restored to defaults." if removed else "Settings were already default.")


@config_app.command("diff")
def config_diff() -> None:
    """Show settings that differ from the defaults."""
    changed = diff(as_dict(load_settings()), as_dict(defaults()))
    changed.get("storage", {}).pop("data_dir", None)
    typer.echo(yaml.safe_dump(changed, sort_keys=False) if any(changed.values()) else "(none)")


if __name__ == "__main__":
    app()
