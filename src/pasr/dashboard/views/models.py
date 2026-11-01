from __future__ import annotations

from functools import partial
from typing import Any

import streamlit as st

from pasr.dashboard.components.save_bar import save_bar, settings_version
from pasr.dashboard.components.schema_form import render_field
from pasr.dashboard.state import settings
from pasr.perception import registry
from pasr.perception.registry import PluginKind
from pasr.settings.loader import as_dict, diff

TABS: dict[str, tuple[PluginKind, ...]] = {
    "Voice": (PluginKind.VAD, PluginKind.SPEAKER, PluginKind.STT),
    "Face": (PluginKind.FACE,),
    "Sensitivity": (PluginKind.SENSITIVITY,),
}
KIND_LABELS = {
    PluginKind.VAD: "Voice-activity detection",
    PluginKind.SPEAKER: "Voice recognition",
    PluginKind.STT: "Speech-to-text",
    PluginKind.FACE: "Face recognition",
    PluginKind.SENSITIVITY: "Sensitivity classifier",
}
# The only model settings on this page: the words and topics that make a reminder sensitive.
# Thresholds and the like keep their values (``pasr config set``, ``pasr calibrate``).
# (Comments, not docstrings: Streamlit would print a bare string on the page.)
WORDS = ("sensitive_keywords", "non_sensitive_keywords", "sensitive_topics")

st.title("Models")
st.caption(
    "Choose the model for each stage of an experiment: what the robot hears, what it sees, and "
    "how it judges whether a reminder is sensitive. Install models on the Setup page."
)

version = settings_version()
values = as_dict(settings())
edited = {"perception": dict(values["perception"])}


def model_label(kind: PluginKind, name: str) -> str:
    return f"{name} , {registry.get_spec(kind, name).description}"


def stage_editor(kind: PluginKind) -> None:
    """One stage: its model, and for the sensitivity classifier its words and topics."""
    names: list[str] = [s.name for s in registry.specs(kind) if s.available]
    chosen = values["perception"][kind.value]
    with st.container(border=True):
        st.markdown(f"**{KIND_LABELS[kind]}**")
        name = st.selectbox(
            "Model",
            names,
            index=names.index(chosen["plugin"]) if chosen["plugin"] in names else 0,
            format_func=partial(model_label, kind),
            key=f"{version}.perception.{kind.value}.plugin",
        )
        if name is None:
            return
        params: dict[str, Any] = chosen["params"] if name == chosen["plugin"] else {}
        model = registry.params_model(kind, name)
        words = [field for field in WORDS if model is not None and field in model.model_fields]
        if model is not None and words:
            full = model.model_validate(params).model_dump(mode="json")
            for field in words:
                full[field] = render_field(
                    field,
                    model.model_fields[field],
                    full[field],
                    f"{version}.perception.{kind.value}.{field}",
                )
            params = diff(full, model().model_dump(mode="json"))
        edited["perception"][kind.value] = {"plugin": name, "params": params}


for tab, kinds in zip(st.tabs(list(TABS)), TABS.values(), strict=True):
    with tab:
        for kind in kinds:
            stage_editor(kind)
        with st.expander("All models, including planned ones"):
            st.dataframe(
                [
                    {
                        "stage": KIND_LABELS[s.kind],
                        "model": s.name,
                        "status": s.status,
                        "description": s.description,
                    }
                    for s in registry.specs()
                    if s.kind in kinds
                ],
                hide_index=True,
                width="stretch",
            )

save_bar(edited, values)
