from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import streamlit as st

from pasr.dashboard.components.loading import working
from pasr.dashboard.components.notify import notify, rerun
from pasr.dashboard.components.robot import needs_stopped
from pasr.dashboard.state import attempt, settings
from pasr.hardware import discovery
from pasr.hardware.check import check_devices
from pasr.orchestration.lock import RuntimeLock
from pasr.paths import resolve
from pasr.perception import models as model_weights
from pasr.settings.schema import DEVICES

DEVICE_LABELS = {
    "ohbot": "Head",
    "speaker": "Voice",
    "camera": "Camera",
    "microphone": "Microphone",
    "watch": "Watch",
}

st.title("Setup")
st.caption(
    "Find and test the robot's devices, and download the models. "
    "Scanning and testing need the robot stopped: while it runs, it owns the devices."
)

current = settings()
hardware = current.hardware
busy = not needs_stopped("scan or test the devices", key="stop-setup")


def with_devices(what: str, work: Callable[[], Any]) -> Any:
    """Run ``work`` while holding the runtime lock, so no robot uses the devices meanwhile.
    Errors become a toast and a note, never a crashed page."""

    def locked() -> Any:
        with RuntimeLock(resolve(current.storage.data_dir)):
            return work()

    return attempt(what, locked)


# --- what is connected ---------------------------------------------------------------------

with st.container(border=True):
    st.markdown("#### What is connected")
    configured = {
        "serial ports": f"hardware.ohbot.port = {hardware.ohbot.port}",
        "microphones": f"hardware.microphone.device = {hardware.microphone.device or 'default'}",
        "audio outputs": "hardware.speaker.output_device = "
        f"{hardware.speaker.output_device or 'macOS default'}",
        "cameras": f"hardware.camera.name = {hardware.camera.name}"
        if hardware.camera.name
        else f"hardware.camera.index = {hardware.camera.index}",
        "watches": f"hardware.watch.address = {hardware.watch.address or 'not found yet'}",
    }
    if st.button("Scan", disabled=busy, key="scan", icon=":material/search:"):

        def scan() -> list[discovery.Discovery]:
            with working("Scanning for devices"):
                return [
                    discovery.serial_ports(),
                    discovery.microphones(),
                    discovery.audio_outputs(),
                    asyncio.run(discovery.cameras()),
                    asyncio.run(discovery.watches(hardware.watch.name_prefix, 5.0)),
                ]

        st.session_state["devices-scan"] = with_devices("Scanning", scan)
    for found in st.session_state.get("devices-scan") or []:
        st.markdown(f"**{found.kind.capitalize()}** · {configured.get(found.kind, '')}")
        for item in found.items:
            st.write(f"- {item}")
        if found.hint:
            st.caption(found.hint)


# --- test -------------------------------------------------------------------------------------

with st.container(border=True):
    st.markdown("#### Test the devices")
    st.caption(
        "The head blinks and looks left, front and right; the robot says “Robot check.”; the "
        "camera takes one frame; the microphone listens for a moment; the watch is pinged and "
        "must have the consent app loaded (a newly found watch address is saved)."
    )
    chosen = st.multiselect(
        "Devices", list(DEVICES), default=list(DEVICES), format_func=DEVICE_LABELS.__getitem__
    )
    if st.button("Run test", type="primary", disabled=busy or not chosen, key="test"):

        def test() -> list[Any]:
            with working("Testing the devices"):
                return asyncio.run(check_devices(current, only=chosen))

        st.session_state["devices-test"] = with_devices("Testing", test)
    reports = st.session_state.get("devices-test") or []
    if reports:
        st.dataframe(
            [
                {
                    "device": DEVICE_LABELS[r.device],
                    "result": "✅ ok" if r.ok else "⚠️ failed",
                    "detail": r.detail,
                }
                for r in reports
            ],
            hide_index=True,
            width="stretch",
        )


# --- models -------------------------------------------------------------------------------------

with st.container(border=True):
    st.markdown("#### Models")
    st.caption(
        "Tick the models to install, once before enrolling; afterwards the robot works offline. "
        "This is the only time it uses the network (a few hundred MB each). Which model each "
        "stage uses is chosen on the Models page."
    )
    statuses = model_weights.model_status(current)
    rows = [
        {
            # the models in use that are not downloaded yet are ticked to start with
            "install": row.configured and row.weights == "not downloaded",
            "stage": row.kind.value,
            "model": row.plugin,
            "in use": "✓" if row.configured else "",
            "installed": row.weights,
            "status": row.status,
        }
        for row in statuses
    ]
    marks = st.data_editor(
        rows,
        column_config={"install": st.column_config.CheckboxColumn("install")},
        disabled=["stage", "model", "in use", "installed", "status"],
        hide_index=True,
        width="stretch",
        key=f"models-marked-{st.session_state.get('models-installs', 0)}",  # fresh once installed
    )
    marked = [row for row, mark in zip(statuses, marks, strict=True) if mark["install"]]
    if st.button(
        "Install the marked models",
        key="models-install",
        icon=":material/download:",
        disabled=not marked,
    ):
        progress = st.progress(0.0, text="Starting…")
        installed = []
        for number, row in enumerate(marked):
            what = f"the {row.kind.value} model {row.plugin}"
            progress.progress(number / len(marked), text=f"{row.kind.value}: {row.plugin}…")

            def fetch(row: Any = row) -> bool:
                model_weights.download_model(current, row.kind, row.plugin)
                return True

            with working(f"Installing {what}"):
                done = attempt(f"Installing {what}", fetch)
            if done is None:  # network, disk or library problem: shown, stop here
                break
            installed.append(row.plugin)
        else:
            progress.progress(1.0, text="Done")
        if installed:
            st.session_state["models-installs"] = st.session_state.get("models-installs", 0) + 1
            notify(f"Installed {', '.join(installed)}: they work offline from now on.", "success")
            rerun()
