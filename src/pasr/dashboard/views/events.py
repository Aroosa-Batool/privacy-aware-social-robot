from __future__ import annotations

import csv
import io
import json
from collections import Counter

import pandas as pd
import streamlit as st

from pasr.dashboard.components.feedback import outcome, rate, verdict
from pasr.dashboard.components.feedback import rows as feedback_rows
from pasr.dashboard.components.tables import with_flags
from pasr.dashboard.state import offline
from pasr.orchestration.events import EventType

st.title("Events")
st.caption(
    "The research log: every state change, detection score and consent answer, with labels and "
    "numbers only , no reminder titles, transcripts, embeddings or images."
)

repos = offline().repos
sessions = repos.events.sessions()
session_column, type_column, limit_column = st.columns([2, 3, 1])
session = session_column.selectbox("Session", ["All sessions", *sessions])
types = type_column.multiselect("Event types", [t.value for t in EventType])
limit = limit_column.number_input("Rows", min_value=10, max_value=10000, value=500, step=50)

events = repos.events.query(
    limit=int(limit),
    types=types or None,
    session_id=None if session == "All sessions" else session,
)
rows = [
    {
        "id": e.id,
        "time": e.ts.strftime("%Y-%m-%d %H:%M:%S"),
        "session": e.session_id,
        "type": e.type,
        "reminder": e.reminder_id,
        "bystander": e.bystander_id,
        "from": e.state_from,
        "to": e.state_to,
        "data": json.dumps(dict(e.payload)),
    }
    for e in events
]

if not rows:
    st.caption("No events yet.")
else:
    counts = Counter(row["type"] for row in rows)
    st.bar_chart(dict(sorted(counts.items())), horizontal=True, x_label="events", y_label="")
    st.dataframe(rows, hide_index=True, width="stretch")

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    with st.container(horizontal=True, gap="small"):
        st.download_button(
            "Download CSV",
            buffer.getvalue(),
            "pasr-events.csv",
            "text/csv",
            icon=":material/download:",
        )
        st.download_button(
            "Download JSON Lines",
            "\n".join(json.dumps(row) for row in rows) + "\n",
            "pasr-events.jsonl",
            "application/jsonl",
            icon=":material/download:",
        )

st.subheader("Pipeline feedback")
st.caption(
    "Whether each reminder's run worked as it should, with the models it used, for comparing "
    "them. Rate a run on Home as it ends, or any run here. Comments are kept with the feedback, "
    "never in the event log."
)
runs = {(run.session_id, run.reminder_id): run for run in repos.events.runs(limit=200)}
rated = {(f.run.session_id, f.run.reminder_id): f for f in repos.feedback.all()}
if not runs:
    st.caption("No reminder has run yet.")
else:

    def label(key: tuple[str, int]) -> str:
        run = runs[key]
        said = f"rated: {verdict(rated[key].worked)}" if key in rated else "not rated"
        return f"#{run.reminder_id} · {run.started_at:%a %d %b %H:%M} · {outcome(run)} · {said}"

    keys = list(runs)
    first_unrated = next((i for i, key in enumerate(keys) if key not in rated), 0)
    chosen = st.selectbox("Run", keys, index=first_unrated, format_func=label)
    with st.container(border=True):
        rate(*chosen)

if rated:
    table = feedback_rows(list(rated.values()))
    flags = ["worked", *(["sensitive"] if any("sensitive" in row for row in table) else [])]
    st.dataframe(with_flags(table, *flags), hide_index=True, width="stretch")
    st.download_button(
        "Download feedback CSV",
        pd.DataFrame(table).to_csv(index=False),
        "pasr-pipeline-feedback.csv",
        "text/csv",
        icon=":material/download:",
    )
