"""Analysis of the consent-scenario vignette study (LimeSurvey 841423).

Run from the repository root:

    python survey/analysis/analyze_survey.py [path/to/export.csv]

Reads the raw LimeSurvey CSV export ("code. question text" headers, answers as text),
drops every IP-address column on load, and writes tidy data, CSV + LaTeX (booktabs)
tables and PDF figures to survey/analysis/out/. No network access. Only MDMT v2, UEQ-S and PSI
Social Competence enter scored inferential analyses (exploratory, not preregistered).
Other questionnaire items are described individually, without composite scores or tests.
"""

from __future__ import annotations

import csv
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy import stats

from render_figures import render_results

HERE = Path(__file__).resolve().parent
DEFAULT_CSV = HERE.parent / "results-survey841423.csv"
OUT = HERE / "out"
SEED = 20261114

SCEN = {"S1": "A", "S2": "B", "S3": "C"}
SCEN_NAME = {
    "A": "A: disclose without asking",
    "B": "B: ask every time",
    "C": "C: ask once and remember",
}
POLICY = {"A": "always_disclose", "B": "always_ask", "C": "ask_once_per_bystander"}
CORRECT_CHK = {
    "A": "It did not ask Alex and said the reminder out loud straight away",
    "B": "It did not remember Jordan, so it asked Alex on the smartwatch again",
    "C": "It remembered Jordan and Alex's earlier Yes, so it did not ask again",
}
AGREE7 = {
    "Strongly disagree": 1,
    "Disagree": 2,
    "Somewhat disagree": 3,
    "Neither agree nor disagree": 4,
    "Somewhat agree": 5,
    "Agree": 6,
    "Strongly agree": 7,
}
RANK_OPTS = {
    "Say the reminder out loud without asking": "Say it aloud without asking",
    "Ask me on my smartwatch every time": "Ask on the watch every time",
    "Ask me once per person and remember my answer": "Ask once per person and remember",
    "Never say it out loud, only show it on my smartwatch": "Show only on the watch",
}
MRANK_OPTS = ["Microphone only", "Camera only", "Microphone first, then camera"]


def mdmt_items(code: str) -> list[str]:
    return [f"MDMT[{code}{i}]" for i in range(1, 5)]


MDMT_SUBSCALES = {
    "trust_perf": {"Reliable": mdmt_items("REL"), "Competent": mdmt_items("CAP")},
    "trust_moral": {
        "Ethical": mdmt_items("ETH"),
        "Sincere": mdmt_items("SIN"),
        "Benevolent": mdmt_items("BEN"),
    },
}
MDMT_PERF = [item for items in MDMT_SUBSCALES["trust_perf"].values() for item in items]
MDMT_MORAL = [item for items in MDMT_SUBSCALES["trust_moral"].values() for item in items]

# Measure definitions. key -> (label, items, reverse items, kind)
SCALES = {
    "soccomp": ("PSI social competence", [f"SOC[SOC{i}]" for i in range(1, 5)], ["SOC[SOC3]"], "agree"),
    "trust_perf": ("Performance trust (MDMT v2)", MDMT_PERF, [], "mdmt"),
    "trust_moral": ("Moral trust (MDMT v2)", MDMT_MORAL, [], "mdmt"),
    "ueq_prag": ("UEQ-S pragmatic quality", [f"UEQ[UEQ{i}]" for i in range(1, 5)], [], "ueq"),
    "ueq_hed": ("UEQ-S hedonic quality", [f"UEQ[UEQ{i}]" for i in range(5, 9)], [], "ueq"),
}
SINGLE = {
    "acc": ("Acceptability (ACC)", "CON[ACC]"),
    "ctl": ("Control (CTL)", "CON[CTL]"),
    "int": ("Intention to use (INT)", "CON[INT]"),
    "saw": ("Social appropriateness (SAW1)", "PS[SAW1]"),
}
# Each four-item trust subscale uses the same scored items as its parent factor.
ITEM_COLUMNS = {
    label: [f"{factor}__{item}" for item in items]
    for factor, subscales in MDMT_SUBSCALES.items()
    for label, items in subscales.items()
}
ITEM_COLUMNS.update({
    key: [f"{key}__{item}" for item in items]
    for key, (_, items, _, _) in SCALES.items()
})
MEASURE_GROUPS = {
    "mdmt_subscales": [label for subscales in MDMT_SUBSCALES.values() for label in subscales],
    "mdmt_factors": ["trust_perf", "trust_moral"],
    "ueqs": ["ueq_prag", "ueq_hed"],
    "psi_soc": ["soccomp"],
}
HRI_MEASURES = [key for group in MEASURE_GROUPS.values() for key in group]
SCORE_LABELS = {
    "trust_perf": "Performance trust",
    "trust_moral": "Moral trust",
    "ueq_prag": "Pragmatic quality",
    "ueq_hed": "Hedonic quality",
    "soccomp": "Social Competence",
}
PAIRS = (("B", "A"), ("C", "A"), ("C", "B"))
CONTEXT_ITEMS = {
    "privacy_violation": ("Ohbot violated my privacy", "PS[PRAW1]"),
    "privacy_boundaries": ("Ohbot understands privacy boundaries", "PS[PRAW2]"),
    "privacy_aware": ("Ohbot's behaviour was privacy-aware", "PS[PRAW5]"),
    "acc": ("Ohbot's way of handling my permission is acceptable to me", "CON[ACC]"),
    "ctl": ("I felt in control of what Ohbot said in front of Jordan", "CON[CTL]"),
    "int": ("I would use a robot that works this way", "CON[INT]"),
    "saw": ("Ohbot behaved appropriately in the social situation", "PS[SAW1]"),
}


# --------------------------------------------------------------------------- loading
def load(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, skipinitialspace=True, dtype=str, keep_default_na=False)
    if raw.columns[0].strip() == "Response ID":
        # Export with "question text" headings only: restore the codes by position from
        # export_columns.csv (headings of a "code. text" export), checking every text.
        known = pd.read_csv(HERE / "export_columns.csv", dtype=str, keep_default_na=False)
        with open(path, encoding="utf-8-sig", newline="") as f:  # pandas renames repeats
            texts = [c.strip() for c in next(csv.reader(f, skipinitialspace=True))]
        if texts != [t.strip() for t in known["text"]]:
            raise SystemExit("export columns do not match export_columns.csv")
        raw.columns = [f"{c}. {t}" for c, t in zip(known["code"], texts)]
    raw = raw.drop(columns=[c for c in raw.columns if c.lower().startswith("ipaddr")])
    raw.columns = [c.split(". ", 1)[0].strip() for c in raw.columns]
    stripped = raw.apply(lambda s: s.str.strip())
    df = stripped.mask(stripped.eq(""))
    df["id"] = df["id"].astype(int)
    df["completed"] = df["submitdate"].notna()
    df["lastpage"] = pd.to_numeric(df["lastpage"], errors="coerce")
    df["interviewtime"] = pd.to_numeric(df["interviewtime"], errors="coerce")
    return df


def code(val, kind: str):
    if pd.isna(val):
        return np.nan
    if kind == "agree":
        return AGREE7[val]
    if kind in (
        "mdmt",
        "infosens",
    ):  # "0 Not at all" ... "7 Very"; INFOSENS "7 Extremely sensitive"
        return float(str(val).split()[0])
    if kind == "ueq":
        # Standard UEQ-S scoring: positive word on right; neutral = 0.
        return float(val) - 4
    raise ValueError(kind)


def score(df: pd.DataFrame) -> pd.DataFrame:
    """One row per participant x scenario with all scored measures."""
    rows = []
    for _, r in df.iterrows():
        for pre, sc in SCEN.items():
            rec = {
                "id": r["id"],
                "scenario": sc,
                "policy": POLICY[sc],
                "position": pd.to_numeric(r.get(pre + "POS"), errors="coerce"),
                "chk": r.get(pre + "CHK"),
            }
            rec["chk_pass"] = (rec["chk"] == CORRECT_CHK[sc]) if pd.notna(rec["chk"]) else np.nan
            for key, (_, items, rev, kind) in SCALES.items():
                vals = []
                for it in items:
                    v = code(r.get(pre + it), kind)
                    if it in rev:
                        v = 8 - v
                    rec[f"{key}__{it}"] = v
                    vals.append(v)
                # scale mean requires all items (complete-case per scale)
                rec[key] = np.mean(vals) if not np.any(np.isnan(vals)) else np.nan
            for key, (_, it) in CONTEXT_ITEMS.items():
                rec[key] = code(r.get(pre + it), "agree")
            rec["open"] = r.get(pre + "OPEN")
            rows.append(rec)
    long = pd.DataFrame(rows)
    answered = long[[*SCALES, *SINGLE]].notna().any(axis=1)
    long = long.loc[answered].reset_index(drop=True)
    return pd.concat([long, mdmt_subscale_scores(long)], axis=1)


def mdmt_subscale_scores(long: pd.DataFrame) -> pd.DataFrame:
    """Score the four required items within each participant and policy."""
    return pd.DataFrame({
        label: long[ITEM_COLUMNS[label]].mean(axis=1, skipna=False)
        for label in MEASURE_GROUPS["mdmt_subscales"]
    })


def exact_signed_rank(differences: np.ndarray) -> float:
    """Two-sided sign permutation of the nonzero differences, conditional on tied midranks."""
    values = differences[differences != 0]
    if not len(values):
        return 1.0
    # A midrank can be a half integer. Doubling preserves all rank sums exactly.
    ranks = (2 * stats.rankdata(np.abs(values))).astype(int)
    positive_sum = int(ranks[values > 0].sum())
    lower_tail = min(positive_sum, int(ranks.sum()) - positive_sum)
    # Count assignments at or below the observed tail. Descending order uses each rank once.
    counts = [1] + [0] * lower_tail
    for rank in ranks:
        for total in range(lower_tail, rank - 1, -1):
            counts[total] += counts[total - rank]
    return min(1.0, 2 * sum(counts) / 2 ** len(values))


def holm(p: list[float]) -> list[float]:
    p = np.asarray(p, float)
    # A non-estimable test occupies its place in the declared family.
    finite = np.isfinite(p)
    order = np.argsort(np.where(finite, p, 1.0), kind="stable")
    adjusted = np.empty(len(p))
    adjusted[order] = np.minimum(1, np.maximum.accumulate(
        np.where(finite, p, 1.0)[order] * np.arange(len(p), 0, -1)
    ))
    adjusted[~finite] = np.nan
    return adjusted.tolist()


def cronbach_alpha(items: pd.DataFrame) -> float:
    items = items.dropna()
    k = items.shape[1]
    if len(items) < 3:
        return np.nan
    var_sum = items.var(ddof=1).sum()
    tot = items.sum(axis=1).var(ddof=1)
    return float(k / (k - 1) * (1 - var_sum / tot)) if tot > 0 else np.nan


def instrument_results(long: pd.DataFrame):
    """Descriptives, omnibus tests and exact pairwise tests on matched completers."""
    descriptions, overall, pairs = [], [], []
    for group, keys in MEASURE_GROUPS.items():
        for key in keys:
            wide = long.pivot(index="id", columns="scenario", values=key).reindex(columns=list("ABC")).dropna()
            n = len(wide)
            if n < 2:
                raise ValueError(f"{key} has fewer than two complete sets of policy scores")
            columns = ITEM_COLUMNS[key]
            common = {"group": group, "measure": key, "label": SCORE_LABELS.get(key, key), "n": n}
            item_counts = len(columns)
            # Scores are means of integer items. Use their sums so theoretically equal
            # differences (especially twelfths for moral trust) receive identical ranks.
            totals = np.rint(wide * item_counts).astype(int)
            for policy in "ABC":
                scores = wide[policy]
                avg, sd = scores.mean(), scores.std(ddof=1)
                margin = stats.t.ppf(.975, n - 1) * sd / np.sqrt(n)
                matched = long.loc[long.scenario.eq(policy) & long.id.isin(wide.index), columns]
                descriptions.append({
                    **common, "policy": policy, "items": item_counts, "mean": avg, "sd": sd,
                    "median": scores.median(), "ci_low": avg - margin, "ci_high": avg + margin,
                    "alpha": cronbach_alpha(matched),
                })
            if totals.nunique(axis=1).gt(1).any():
                chi2, p = stats.friedmanchisquare(totals.A, totals.B, totals.C)
            else:
                chi2, p = np.nan, np.nan  # All three conditions tied for every participant.
            overall.append({**common, "df": 2, "chi2": chi2, "p_raw": p, "kendall_w": chi2 / (2 * n)})
            for first, second in PAIRS:
                difference = (totals[first] - totals[second]).to_numpy()
                pairs.append({
                    **common, "first": first, "second": second,
                    "n_nonzero": np.count_nonzero(difference),
                    "median_difference": np.median(difference) / item_counts,
                    "p_raw": exact_signed_rank(difference),
                })
    omnibus = pd.DataFrame(overall)
    comparisons = pd.DataFrame(pairs)
    omnibus["p_holm"] = holm(omnibus.p_raw)
    comparisons["p_holm"] = holm(comparisons.p_raw)
    return pd.DataFrame(descriptions), omnibus, comparisons


def ranking_counts(comp: pd.DataFrame) -> pd.DataFrame:
    """Count each option at every rank for complete ballots, including zero counts."""
    groups = [
        ("Sensing", "MRANK", {option: option for option in MRANK_OPTS}),
        ("Handling", "RANK", RANK_OPTS),
    ]
    result = []
    for group, prefix, options in groups:
        positions = comp[[f"{prefix}[{i}]" for i in range(1, len(options) + 1)]].dropna()
        if positions.empty:
            raise ValueError(f"No complete {group.lower()} rankings")
        if any(set(ballot) != set(options) for ballot in positions.itertuples(index=False, name=None)):
            raise ValueError(f"Invalid {group.lower()} ranking: each option must appear once")
        counts = {option: positions.eq(option).sum().tolist() for option in options}
        for option in sorted(options, key=counts.get, reverse=True):
            for rank, count in enumerate(counts[option], 1):
                result.append((group, options[option], rank, count, len(positions)))
    return pd.DataFrame(result, columns=["group", "option", "rank", "count", "n"])


def latex_table(
    df: pd.DataFrame,
    path: Path,
    caption: str,
    label: str,
    colspec: str | None = None,
    note: str | None = None,
) -> None:
    colspec = colspec or ("l" + "r" * (df.shape[1] - 1))

    def esc(s: object) -> str:
        return (
            str(s)
            .replace("&", r"\&")
            .replace("%", r"\%")
            .replace("_", r"\_")
            .replace("<", r"$<$")
            .replace(">", r"$>$")
        )

    lines = [
        r"% generated by survey/analysis/analyze_survey.py -- do not edit by hand",
        r"\begin{table}[htbp]",
        r"\centering",
        r"\small",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
        rf"\begin{{tabular}}{{{colspec}}}",
        r"\toprule",
        " & ".join(esc(c) for c in df.columns) + r" \\",
        r"\midrule",
    ]
    for _, row in df.iterrows():
        lines.append(" & ".join(esc(v) for v in row) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    if note:
        lines.append(rf"\par\smallskip\footnotesize\raggedright {note}")
    lines.append(r"\end{table}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save(
    df: pd.DataFrame,
    name: str,
    caption: str,
    label: str,
    note: str | None = None,
    colspec: str | None = None,
) -> None:
    df.to_csv(OUT / f"{name}.csv", index=False)
    latex_table(df, OUT / f"{name}.tex", caption, label, colspec, note)


# --------------------------------------------------------------------------- analysis
def main(csv: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report: list[str] = []

    def say(s: str = "") -> None:
        report.append(s)

    df = load(csv)
    long_all = score(df)
    comp_ids = set(df.loc[df["completed"], "id"])
    long = long_all[long_all["id"].isin(comp_ids)].copy()
    long.drop(columns=["open"]).to_csv(OUT / "long_scores.csv", index=False)
    comp = df[df["completed"]].copy()
    n = len(comp)

    # ---- participant flow
    n_scen = long_all.groupby("id").size().reindex(df["id"], fill_value=0)
    flow = pd.DataFrame(
        [
            ("Responses in export", len(df)),
            (
                "Answered at least one demographic item",
                int(df[["DM01", "DM02", "DM03", "DM04"]].notna().any(axis=1).sum()),
            ),
            ("Answered at least one scenario", int((n_scen > 0).sum())),
            ("Answered all three scenarios", int((n_scen == 3).sum())),
            ("Submitted (complete; analysed)", n),
        ],
        columns=["Stage", "N"],
    )
    # The flow is computed from the full export (incomplete records included).
    save(flow, "flow", "Participant flow from started to analysed responses.", "tab:study-flow")
    import matplotlib
    environment = {"python": platform.python_version(), "numpy": np.__version__,
                   "pandas": pd.__version__, "scipy": scipy.__version__,
                   "matplotlib": matplotlib.__version__}
    (OUT / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    say("# Survey analysis report")
    say("Instrument-based analysis: MDMT v2, UEQ-S and PSI Social Competence; other questions descriptive.")
    say("Environment: " + str(environment))
    say(f"Export: {csv.name}; rows: {len(df)}; submitted: {n}")
    say("lastpage: " + str(df["lastpage"].value_counts(dropna=False).sort_index().to_dict()))
    say(flow.to_string(index=False))

    # ---- descriptives: demographics of the completers (the analysed sample)
    demo_rows = []
    for col, lab in [
        ("DM01", "Gender"),
        ("DM04", "Highest degree"),
        ("DM03", "Country"),
        ("TE01", "Interacted with a social robot"),
        ("TE03", "Uses a smartwatch"),
        ("TE04", "Uses a voice assistant"),
    ]:
        for k, v in comp[col].value_counts(dropna=True).items():
            demo_rows.append((lab, k, int(v)))
    age_c = pd.to_numeric(comp["DM02"], errors="coerce")
    demo_rows.append(
        ("Age", "Median (range)", f"{age_c.median():.0f} ({age_c.min():.0f}-{age_c.max():.0f})")
    )
    demo = pd.DataFrame(demo_rows, columns=["Variable", "Level", "n"]).astype(str)
    save(
        demo,
        "demographics",
        f"Sample characteristics of the completers ($N = {n}$).",
        "tab:study-demographics",
        colspec="llr",
    )
    say("\n## Demographics (completers)")
    say(demo.to_string(index=False))
    say(
        f"interviewtime completers (s): median {comp.interviewtime.median():.0f}, "
        f"min {comp.interviewtime.min():.0f}, max {comp.interviewtime.max():.0f}"
    )
    speed_cut = comp.interviewtime.median() / 3
    speeders = comp.loc[comp.interviewtime < speed_cut, "id"].tolist()
    say(f"Speeder flag (< median/3 = {speed_cut:.0f} s): {len(speeders)} -> not excluded")

    # ---- order + manipulation checks
    order = long.sort_values("position").groupby("id")["scenario"].apply(lambda s: "".join(s))
    order_tab = order.value_counts().rename_axis("Order").reset_index(name="N")
    save(
        order_tab,
        "order_counts",
        "Scenario orders among completers (randomised).",
        "tab:study-orders",
    )
    say("\n## Orders\n" + order_tab.to_string(index=False))

    chk = long.pivot(index="id", columns="scenario", values="chk_pass")
    chk_tab = pd.DataFrame(
        {
            "Scenario": [SCEN_NAME[s] for s in "ABC"],
            "Passed": [int((chk[s] == True).sum()) for s in "ABC"],  # noqa: E712
            "Failed": [int((chk[s] == False).sum()) for s in "ABC"],  # noqa: E712
            "Blank": [int(chk[s].isna().sum()) for s in "ABC"],
        }
    )
    n_fail = (chk == False).sum(axis=1)  # noqa: E712
    save(
        chk_tab,
        "manipulation_checks",
        "Manipulation-check results among completers.",
        "tab:study-checks",
        note="Participants failing 0/1/2/3 checks: "
        + "/".join(str(int((n_fail == k).sum())) for k in range(4))
        + ".",
    )
    say("\n## Manipulation checks\n" + chk_tab.to_string(index=False))
    say("fails per participant: " + str(n_fail.value_counts().sort_index().to_dict()))
    # wrong answers chosen
    wrong = long[long.chk_pass == False].groupby(["scenario", "chk"]).size()  # noqa: E712
    say(wrong.to_string())

    descriptions, omnibus, pairs = instrument_results(long)
    for filename, table in [("measure_descriptives", descriptions), ("policy_omnibus", omnibus),
                            ("policy_pairs", pairs)]:
        table.to_csv(OUT / f"{filename}.csv", index=False)
        say(f"\n## {filename.replace('_', ' ')}\n" + table.to_string(index=False))

    # ---- contextual items: counts only, in original wording and response categories.
    # Privacy and study-specific judgements are individual response counts only; no composite or inferential analysis.
    context_rows = []
    inverse = {v: k for k, v in AGREE7.items()}
    for key, (label, _) in CONTEXT_ITEMS.items():
        for scenario in "ABC":
            v = long.loc[long.scenario == scenario, key]
            options = [1, 2, 3, 5, 6, 7] if key in ("acc", "ctl", "int") else list(range(1, 8))
            for option in options:
                context_rows.append([key, label, scenario, inverse[option], int((v == option).sum()), int(v.notna().sum())])
            context_rows.append([key, label, scenario, "Missing", int(v.isna().sum()), len(v)])
    context = pd.DataFrame(context_rows, columns=["item", "wording", "scenario", "response", "count", "denominator"])
    context.to_csv(OUT / "context_response_counts.csv", index=False)
    say("\n## Contextual questionnaire responses (counts only; no composite scores or tests)\n" + context.to_string(index=False))

    ranks = ranking_counts(comp)
    ranks.to_csv(OUT / "ranking_counts.csv", index=False)
    say("\n## Ranks assigned to each option\n" + ranks.to_string(index=False))
    # Sensitivity is contextual; retain its response frequencies without correlations.
    inf = comp.set_index("id")["INFOSENS[REM]"].map(lambda v: code(v, "infosens"))
    inf.value_counts().sort_index().rename_axis("response").reset_index(name="count").to_csv(OUT / "sensitivity_counts.csv", index=False)

    # ---- free text export (for coding; stays in out/, which is git-ignored)
    ft = []
    for pre, sc in SCEN.items():
        for pid, v in zip(comp["id"], comp[pre + "OPEN"]):
            if pd.notna(v):
                ft.append((pid, f"OPEN_{sc}", v))
    for col in ("MOTHER", "FINAL"):
        for pid, v in zip(comp["id"], comp[col]):
            if pd.notna(v):
                ft.append((pid, col, v))
    ft = pd.DataFrame(ft, columns=["id", "field", "text"])
    ft.to_csv(OUT / "free_text.csv", index=False)
    code_free_text(ft, say)

    # ---- figures
    render_results(long, descriptions, omnibus, pairs, ranks, OUT)

    (OUT / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


def code_free_text(ft: pd.DataFrame, say) -> None:
    """Apply the hand-made codebook (codebook.csv: id, field, codes separated by ';').
    Uncoded new answers are listed so a newer export can be coded incrementally."""
    cb_path = HERE / "codebook.csv"
    if not cb_path.exists():
        say(f"\n## Free text: {len(ft)} answers; codebook.csv not found")
        return
    cb = pd.read_csv(cb_path, dtype={"id": int})
    m = ft.merge(cb[["id", "field", "codes"]], on=["id", "field"], how="left")
    uncoded = m[m.codes.isna()]
    rows = m.dropna(subset=["codes"]).assign(code=lambda d: d.codes.str.split(";")).explode("code")
    rows["code"] = rows.code.str.strip()
    rows = rows[rows.code != ""]
    defs = pd.read_csv(HERE / "codebook_definitions.csv")
    cnt = (
        rows.groupby("code")
        .agg(answers=("text", "size"), participants=("id", "nunique"))
        .reset_index()
    )
    tab = defs.merge(cnt, on="code", how="left").fillna({"answers": 0, "participants": 0})
    tab[["answers", "participants"]] = tab[["answers", "participants"]].astype(int)
    tab = tab.sort_values(["theme", "participants"], ascending=[True, False])
    out = tab[["theme", "code", "definition", "participants", "answers"]]
    out.columns = ["Theme", "Code", "Definition", "Participants", "Answers"]
    save(
        out,
        "free_text_codes",
        "Codes from the free-text answers (inductive, single coder).",
        "tab:study-freetext",
        colspec="llp{6cm}rr",
    )
    say(
        f"\n## Free text: {len(ft)} answers from {ft.id.nunique()} participants; uncoded: "
        f"{len(uncoded)}"
    )
    say(out.to_string(index=False))
    if len(uncoded):
        say("UNCODED (add to codebook.csv):\n" + uncoded[["id", "field"]].to_string(index=False))

    # Blank sheet for an independent second coder: the answers without the codes, in a
    # shuffled order (fixed seed). It contains raw answers and is written to out/ only.
    sheet = ft.sample(frac=1, random_state=SEED)[["id", "field", "text"]].assign(codes="")
    sheet.to_csv(OUT / "coding_sheet_second_coder.csv", index=False)
    agreement(cb, set(defs.code), say)


def agreement(cb: pd.DataFrame, codes: set[str], say) -> None:
    """Agreement of the codebook with codebook_coder2.csv (same columns), if present.

    Each answer x code pair is one yes/no decision. Reported: Cohen's kappa over all
    decisions, the share of answers with identical code sets, and kappa per code."""
    path = HERE / "codebook_coder2.csv"
    if not path.exists():
        say("Second coder: codebook_coder2.csv not found, agreement not computed")
        return
    c2 = pd.read_csv(path, dtype={"id": int}).fillna({"codes": ""})

    def sets(d: pd.DataFrame) -> dict:
        return {
            (r.id, r.field): {c.strip() for c in str(r.codes).split(";") if c.strip()}
            for r in d.itertuples()
        }

    a, b = sets(cb), sets(c2)
    keys = sorted(set(a) & set(b))
    unknown = set().union(*b.values()) - codes
    if unknown:
        say(f"Second coder: unknown codes ignored: {sorted(unknown)}")

    def kappa(x: np.ndarray, y: np.ndarray) -> float:
        po = float(np.mean(x == y))
        pe = float(x.mean() * y.mean() + (1 - x.mean()) * (1 - y.mean()))
        return np.nan if pe == 1 else (po - pe) / (1 - pe)

    order = sorted(codes)
    x = np.array([[c in a[k] for c in order] for k in keys], dtype=float)
    y = np.array([[c in b[k] for c in order] for k in keys], dtype=float)
    rows = [{"Code": c, "kappa": kappa(x[:, i], y[:, i])} for i, c in enumerate(order)]
    same = np.mean([a[k] & codes == b[k] & codes for k in keys])
    rows.append({"Code": "All decisions (pooled)", "kappa": kappa(x.ravel(), y.ravel())})
    tab = pd.DataFrame(rows).round(2)
    tab.to_csv(OUT / "free_text_agreement.csv", index=False)
    say(
        f"\n### Second coder: {len(keys)} answers compared; identical code sets: {same:.0%}; "
        f"pooled kappa = {tab.kappa.iloc[-1]:.2f}"
    )
    say(tab.to_string(index=False))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV)
