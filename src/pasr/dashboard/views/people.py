from __future__ import annotations

import streamlit as st

from pasr.dashboard.components.confirm import confirm, delete_button
from pasr.dashboard.components.notify import notify, rerun
from pasr.dashboard.state import offline
from pasr.domain.enums import Biometric
from pasr.orchestration.events import EventType

st.title("People & consent")
st.caption(
    "Bystanders are remembered only if you chose to remember your answers (Profile), "
    "and only together with your answer , as an anonymous label and an embedding, never a "
    "picture or recording."
)

data = offline()
repos = data.repos


def answer_label(allowed: bool | None) -> str:
    return "," if allowed is None else "yes" if allowed else "no"


st.subheader("Owner")
owner = repos.owner.get()
if owner is None:
    st.caption("No owner registered yet , open Profile.")
else:
    enrolled = repos.owner.enrollment()
    st.write(f"**{owner.display_name}** · registered {owner.created_at:%d %b %Y}")
    st.dataframe(
        [
            {
                "data": modality.value,
                "samples": enrolled.get(modality, (0, []))[0],
                "model": ", ".join(enrolled.get(modality, (0, []))[1]) or ",",
            }
            for modality in Biometric
        ],
        hide_index=True,
    )

st.subheader("Bystanders")
bystanders = repos.bystanders.all()
if not bystanders:
    st.caption("No remembered bystanders.")
else:
    answers = repos.consents.effective([b.id for b in bystanders])
    modalities = repos.bystanders.modalities()
    st.dataframe(
        [
            {
                "label": b.label,
                "recognised by": ", ".join(m.value for m in modalities.get(b.id, [])),
                "first seen": b.first_seen_at.strftime("%d %b %H:%M"),
                "last seen": b.last_seen_at.strftime("%d %b %H:%M"),
                "times seen": b.seen_count,
                "may hear sensitive reminders": answer_label(answers.get(b.id)),
            }
            for b in bystanders
        ],
        hide_index=True,
        width="stretch",
    )
    labels = {b.id: b.label for b in bystanders}
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        forget = st.selectbox("Forget a bystander", list(labels), format_func=labels.__getitem__)
        forgotten = forget is not None and confirm(
            "Forget",
            f"Deletes **{labels[forget]}**'s embeddings and consent answers. The robot will "
            "treat them as someone new.",
            key="forget-bystander",
            icon=":material/person_remove:",
        )
    if forgotten:
        repos.bystanders.delete(forget)
        st.rerun()

st.subheader("Consent history")
consents = repos.consents.all()
if not consents:
    st.caption("No remembered answers.")
else:
    labels = {b.id: b.label for b in bystanders}
    st.dataframe(
        [
            {
                "#": c.id,
                "when": c.decided_at.strftime("%d %b %H:%M"),
                "bystander": labels.get(c.bystander_id, c.bystander_id),
                "answer": "yes" if c.allowed else "no",
                "via": c.source.value,
                "status": f"revoked {c.revoked_at:%d %b %H:%M}" if c.revoked_at else "active",
            }
            for c in consents
        ],
        hide_index=True,
        width="stretch",
    )
with st.popover(
    "Delete last consent",
    icon=":material/delete:",
    disabled=not any(c.revoked_at is None for c in consents),
):
    st.markdown("Withdraws the most recent active answer, so the robot asks again.")
    hard = st.checkbox("Delete it permanently instead of keeping it marked as revoked")
    withdraw = delete_button(
        "Delete permanently" if hard else "Revoke",
        key="revoke-consent",
        icon=":material/delete:",
        width="stretch",
    )
if withdraw:
    revoked = repos.consents.revoke_last(data.clock.now(), hard=hard)
    if revoked is not None:
        data.bus.emit(EventType.CONSENT_REVOKED, bystander_id=revoked.bystander_id)
        notify(f"Consent #{revoked.id} {'deleted' if hard else 'revoked'}.", "success")
    rerun()
