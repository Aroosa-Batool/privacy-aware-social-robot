"""Regenerate publication figures from scored exports without rerunning tests.

Run analyze_survey.py first when the underlying dataset changes.
"""
import pandas as pd

from analyze_survey import OUT, figures


if __name__ == "__main__":
    scores = pd.read_csv(OUT / "long_scores.csv")
    comparisons = pd.read_csv(OUT / "primary_all_rules.csv")
    figures(scores, pd.DataFrame(), pd.DataFrame(), pd.Series(dtype=float), comparisons)
    print(f"Figures regenerated from existing exports in {OUT}")
