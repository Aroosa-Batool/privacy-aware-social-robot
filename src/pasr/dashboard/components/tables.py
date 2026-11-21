"""Tables whose yes/no columns are readable: Streamlit draws a read-only checkbox in a table pale
grey (too faint to see, and it cannot be coloured), so a yes is the words "✓ Yes" in blue."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
from pandas.io.formats.style import Styler

from pasr.dashboard.components.palette import colors

YES, NO = "✓ Yes", "No"


def with_flags(rows: Sequence[Mapping[str, Any]], *columns: str) -> Styler:
    """``rows`` for ``st.dataframe``, each of ``columns`` shown as "✓ Yes" (blue) or "No"."""
    frame = pd.DataFrame(rows)
    for column in columns:
        frame[column] = frame[column].map({True: YES, False: NO}).fillna(",")
    accent = colors()["accent"]
    return frame.style.map(
        lambda value: f"color: {accent}; font-weight: 600" if value == YES else "",
        subset=list(columns),
    )
