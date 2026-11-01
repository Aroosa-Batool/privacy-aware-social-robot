"""The calibration chart: one dot per sample, at its similarity to the enrolled owner, the
owner's row above the other people's, and the threshold as a line between them."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import altair as alt
import pandas as pd

from pasr.dashboard.components.palette import colors, theme

OWNER = "You"
OTHERS = "Other people"
SERIES = {  # the live view's owner blue and someone-else orange, stepped for each theme
    "light": ("#2a78d6", "#eb6834"),
    "dark": ("#3987e5", "#d95926"),
}
DOMAIN = (-0.2, 1.0)
"""Similarity shown: below about 0 a face is unrelated, about 1 is the same picture."""
ROW_PX = 60
AROUND_PX = 175
"""The axis, its title, the legend and the labels above the line: Streamlit fits the whole
chart, not just its plot, into the height."""
SPREAD = 0.13
"""How far apart (in rows) samples sit vertically, so close scores do not hide each other."""


def score_chart(
    owner: Sequence[float], others: Sequence[float], threshold: float
) -> alt.LayerChart:
    palette = colors()
    rows = [(OWNER, 0, score) for score in owner] + [(OTHERS, 1, score) for score in others]
    data = pd.DataFrame(rows, columns=["who", "row", "score"])
    data["sample"] = data.groupby("who").cumcount() + 1
    data["y"] = data["row"] + (data["sample"] % 5 - 2) * SPREAD
    count = 2 if others else 1
    x_scale = alt.Scale(domain=DOMAIN, clamp=True)
    y = alt.Y(
        "y:Q",
        title=None,
        scale=alt.Scale(domain=[-0.5, count - 0.5], reverse=True),
        axis=alt.Axis(
            values=list(range(count)),
            labelExpr=f"datum.value == 0 ? '{OWNER}' : '{OTHERS}'",
            labelFontSize=13,
            grid=False,
            ticks=False,
            domain=False,
        ),
    )
    dots = (
        alt.Chart(data)
        .mark_circle(size=90, opacity=1, stroke=palette["page"], strokeWidth=2)
        .encode(
            x=alt.X(
                "score:Q",
                title="Similarity to your enrolment",
                scale=x_scale,
                axis=alt.Axis(values=[-0.2, 0, 0.2, 0.4, 0.6, 0.8, 1.0], format=".1f"),
            ),
            y=y,
            color=alt.Color(  # one row: its label names it, no legend
                "who:N",
                scale=alt.Scale(domain=[OWNER, OTHERS][:count], range=SERIES[theme()][:count]),
                legend=alt.Legend(title=None, orient="bottom") if count > 1 else None,
            ),
            tooltip=[
                alt.Tooltip("who:N", title="Who"),
                alt.Tooltip("sample:Q", title="Sample"),
                alt.Tooltip("score:Q", title="Similarity", format=".2f"),
            ],
        )
    )
    line = pd.DataFrame({"threshold": [threshold]})
    rule = (
        alt.Chart(line)
        .mark_rule(color=palette["text"], strokeWidth=2)
        .encode(
            x=alt.X("threshold:Q", scale=x_scale),
            tooltip=[alt.Tooltip("threshold:Q", title="Threshold", format=".2f")],
        )
    )

    def side(text: str, align: Literal["left", "right"], dx: int) -> alt.Chart:
        label: alt.Chart = (
            alt.Chart(line)
            .mark_text(
                text=text, align=align, dx=dx, baseline="bottom", y=-6, color=palette["muted"]
            )
            .encode(x=alt.X("threshold:Q", scale=x_scale))
        )
        return label

    layers = dots + rule + side("← someone else", "right", -6) + side("counts as you →", "left", 6)
    chart: alt.LayerChart = layers.properties(
        height=ROW_PX * count + AROUND_PX, padding={"top": 22}
    )
    return chart
