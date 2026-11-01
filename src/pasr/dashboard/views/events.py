from __future__ import annotations

import csv
import io
import json
from collections import Counter

import streamlit as st

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
