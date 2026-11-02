from __future__ import annotations

import streamlit as st
import yaml
from pydantic import ValidationError

from pasr.dashboard.components.confirm import confirm
from pasr.dashboard.components.forms import text_form
from pasr.dashboard.components.loading import working
from pasr.dashboard.components.notify import notify, rerun
from pasr.dashboard.components.robot import needs_running
from pasr.dashboard.components.save_bar import renew
from pasr.dashboard.state import (
    attempt,
    get_handle,
    offline,
    report_saved,
    save_settings,
    settings,
)
from pasr.domain.enums import Biometric, DetectionModality, DisclosurePolicy
from pasr.orchestration.enrollment import (
    FACE_GUIDANCE,
    VOICE_GUIDANCE,
    VOICE_PASSAGE,
    face_enrolment_seconds,
    voice_enrolment_seconds,
)
from pasr.orchestration.runtime import Runtime
from pasr.settings.loader import (
    as_dict,
    clear_overrides,
    deep_merge,
    defaults,
    dump_yaml,
    update_overrides,
)
from pasr.settings.schema import Settings

MODALITY_OPTIONS = {
    DetectionModality.AUDIO_ONLY: "Microphone only , the camera is never used for this",
    DetectionModality.CAMERA_ONLY: "Camera only , the microphone is never used for this",
    DetectionModality.AUDIO_AND_CAMERA: "Microphone and camera",
    DetectionModality.NONE: "Neither , do not detect bystanders",
}
# Asking, and remembering the answer, together pick the disclosure policy.
ASK_OPTIONS = {
    False: "Always say them out loud, whoever is present",
    True: "Ask me on the watch when someone else is present",
}
REMEMBER_OPTIONS = {
    False: "Don't remember: ask me every time, and keep nothing about the person",
    True: "Remember: keep my answer with that person's face and voice embeddings, and don't "
    "ask about them again",
}

st.title("Profile")
st.caption(
    "Register the robot's owner, teach it their face and voice, make your privacy choices, and "
    "save or load all settings as a profile. The robot keeps only face and voice embeddings "
    "(numbers), never photos or recordings."
)

handle = get_handle()
data = offline()
current = settings()
owner = data.repos.owner.get()
enrolled = data.repos.owner.enrollment()

# The steps the chosen detection needs (as in setup_warnings); the others are optional.
detection = current.privacy.detection_modality
needed = {
    "owner": True,
    Biometric.FACE: detection.looks,
    Biometric.VOICE: detection.listens,
}
complete = {
    "owner": owner is not None,
    Biometric.FACE: enrolled.get(Biometric.FACE, (0, []))[0] > 0,
    Biometric.VOICE: enrolled.get(Biometric.VOICE, (0, []))[0] > 0,
}
required = [name for name, need in needed.items() if need]
finished = sum(complete[name] for name in required)
st.progress(
    finished / len(required),
    text="Profile complete"
    if finished == len(required)
    else f"{finished} of {len(required)} required steps done",
)


def step(number: int, title: str, done: bool, *, optional: bool = False) -> None:
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown(f"#### {number} · {title}", width="content", anchors=False)
        if done:
            st.badge("Done", icon=":material/check:", color="green")
        elif optional:
            st.badge("Optional", color="gray")
        else:
            st.badge("To do", color="orange")


with st.container(border=True):
    step(1, "Owner", complete["owner"])
    with text_form("owner", border=False):
        name = st.text_input(
            "Owner's name", value=owner.display_name if owner else "", placeholder="Their name"
        )
        if st.form_submit_button("Save name", type="primary") and name.strip():
            data.repos.owner.save(name.strip(), data.clock.now())
            st.rerun()

if owner is not None:  # once, for both captures
    needs_running("capture the owner's face and voice")


async def _enroll(runtime: Runtime, modality: Biometric) -> int:
    if modality is Biometric.FACE:
        return await runtime.enrollment.enroll_face()
    return await runtime.enrollment.enroll_voice()


def enrolment_step(number: int, modality: Biometric, title: str, what: str) -> None:
    count, models = enrolled.get(modality, (0, []))
    with st.container(border=True):
        step(number, title, count > 0, optional=not needed[modality])
        if count:
            st.write(f"Enrolled: {count} samples · model `{', '.join(models)}`")
        if owner is None:
            st.caption("Register the owner first.")
            return
        if not handle.running:
            return
        if modality is Biometric.FACE:
            st.caption(FACE_GUIDANCE)
        else:
            st.caption(VOICE_GUIDANCE.format(seconds=current.identity.enroll_voice_seconds))
            with st.container(border=True):  # in view while the robot listens
                st.markdown(VOICE_PASSAGE)
        timeout = (
            face_enrolment_seconds(current.identity)
            if modality is Biometric.FACE
            else voice_enrolment_seconds(current.identity)
        ) + 30
        with st.container(horizontal=True, gap="small"):
            capture = st.button(
                f"Capture {what}",
                key=f"capture-{modality}",
                type="secondary" if count else "primary",
                icon=":material/photo_camera:" if modality is Biometric.FACE else ":material/mic:",
            )
            delete = count and confirm(
                f"Delete {what} data",
                f"Deletes the owner's {count} {what} embeddings. The robot cannot recognise "
                f"their {what} until you capture it again.",
                key=f"delete-{modality}",
            )
        if capture:
            with working(f"Capturing your {what}"):
                samples = attempt(
                    f"{what.capitalize()} capture",
                    lambda: handle.call(lambda rt: _enroll(rt, modality), timeout=timeout),
                )
            if samples is not None:
                identity = current.identity
                wanted = identity.enroll_face_samples * len(identity.enroll_face_poses)
                if modality is Biometric.FACE and samples < wanted:
                    notify(
                        f"Stored {samples} of {wanted} face embeddings: the robot could not "
                        "see every pose (it said which). Capture again to add it.",
                        "warning",
                    )
                else:
                    notify(f"Stored {samples} {what} embeddings.", "success")
                rerun()
        if delete:
            data.repos.owner.delete_embeddings(modality)
            notify(f"Deleted the owner's {what} data.", "success")
            rerun()


enrolment_step(2, Biometric.FACE, "Face", "face")
enrolment_step(3, Biometric.VOICE, "Voice", "voice")

with st.container(border=True):
    st.markdown("#### 4 · Your privacy choices", anchors=False)
    saved = current.privacy.disclosure_policy
    modality = st.radio(
        "How may the robot check whether someone else is in the room?",
        list(MODALITY_OPTIONS),
        index=list(MODALITY_OPTIONS).index(detection),
        format_func=MODALITY_OPTIONS.__getitem__,
    )
    ask = st.radio(
        "How should the robot handle sensitive reminders when someone else may hear them?",
        list(ASK_OPTIONS),
        index=int(saved is not DisclosurePolicy.ALWAYS_DISCLOSE),
        format_func=ASK_OPTIONS.__getitem__,
    )
    remember = saved is DisclosurePolicy.ASK_ONCE_PER_BYSTANDER
    if ask and modality is not DetectionModality.NONE:  # telling people apart needs a sensor
        remember = st.radio(
            "When you answer on the watch, should the robot remember it for that person?",
            list(REMEMBER_OPTIONS),
            index=int(remember),
            format_func=REMEMBER_OPTIONS.__getitem__,
        )
        known = len(data.repos.bystanders.all())
        if remember:
            st.caption(
                "Remembered people and your answers are listed under Info › People & consent, "
                "where you can forget them."
            )
        elif known:
            stays = (
                "1 person remembered earlier stays"
                if known == 1
                else (f"{known} people remembered earlier stay")
            )
            st.caption(f"{stays} stored until you forget them under Info › People & consent.")
    policy = (
        DisclosurePolicy.ALWAYS_DISCLOSE
        if not ask
        else DisclosurePolicy.ASK_ONCE_PER_BYSTANDER
        if remember
        else DisclosurePolicy.ALWAYS_ASK
    )
    unchanged = (modality, policy) == (detection, saved)
    if st.button("Save preferences", type="primary", disabled=unchanged):
        restart = save_settings(
            {"privacy": {"detection_modality": modality.value, "disclosure_policy": policy.value}}
        )
        report_saved("Preferences saved.", restart)
        rerun()  # the steps the new choice needs

with st.expander("Profiles: save or load all settings"):
    st.caption("A profile is a YAML file with every setting , useful to repeat an experiment.")
    st.download_button(
        "Download current settings", dump_yaml(current), file_name="pasr-profile.yaml"
    )
    upload = st.file_uploader("Load a profile", type=["yaml", "yml"])
    if upload is not None and st.button("Apply profile"):
        try:
            profile = yaml.safe_load(upload.getvalue()) or {}
            Settings.model_validate(deep_merge(as_dict(defaults()), profile))
            clear_overrides(current.storage.data_dir)
            update_overrides(current.storage.data_dir, profile)
        except (ValidationError, ValueError, yaml.YAMLError) as exc:
            notify(f"Profile not loaded: {exc}", "error")
        else:
            renew()
            notify(
                "Profile loaded. Stop and start the robot to apply hardware or algorithm changes.",
                "success",
            )
            rerun()
    if confirm(
        "Restore all defaults",
        "Every setting on every page returns to its default, hardware included. Download the "
        "current settings first to keep them.",
        key="restore-defaults",
        action="Restore defaults",
        icon=":material/settings_backup_restore:",
    ):
        clear_overrides(current.storage.data_dir)
        renew()
        notify("All settings are back to their defaults.", "success")
        rerun()
