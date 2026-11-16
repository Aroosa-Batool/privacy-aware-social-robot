"""Analysis of the consent-scenario vignette study (LimeSurvey 841423).

Run from the repository root:

    uv run --with scipy --with statsmodels --with matplotlib \
        python -I survey/analysis/analyze_survey.py [path/to/export.csv]

Reads the raw LimeSurvey CSV export ("code. question text" headers, answers as text),
drops every IP-address column on load, and writes tidy data, CSV + LaTeX (booktabs)
tables and PDF figures to survey/analysis/out/. No network access. The analysis plan
(exclusion rules, tests, families) was fixed before outcomes were inspected; see the
docstrings below and survey/analysis/README.md.
"""

from __future__ import annotations

import csv
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
DEFAULT_CSV = HERE.parent / "results-survey841423.csv"
OUT = HERE / "out"
SEED = 20261114
N_BOOT = 10_000
ALPHA = 0.05

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
    "Say the reminder out loud without asking": "Say out loud without asking",
    "Ask me on my smartwatch every time": "Ask on watch every time",
    "Ask me once per person and remember my answer": "Ask once per person, remember",
    "Never say it out loud, only show it on my smartwatch": "Watch only, never out loud",
}
MRANK_OPTS = ["Microphone only", "Camera only", "Microphone first, then camera"]

# Measure definitions (hypotheses sheet). key -> (label, items, reverse items, kind)
MDMT_PERF = [f"MDMT[{d}{i}]" for d in ("REL", "CAP") for i in range(1, 5)]
MDMT_MORAL = [f"MDMT[{d}{i}]" for d in ("ETH", "SIN", "BEN") for i in range(1, 5)]
SCALES = {
    "privacy": (
        "Privacy awareness",
        ["PS[PRAW1]", "PS[PRAW2]", "PS[PRAW5]"],
        ["PS[PRAW1]"],
        "agree",
    ),
    "soccomp": ("Social competence", [f"SOC[SOC{i}]" for i in range(1, 5)], ["SOC[SOC3]"], "agree"),
    "trust_perf": ("Performance trust (MDMT)", MDMT_PERF, [], "mdmt"),
    "trust_moral": ("Moral trust (MDMT)", MDMT_MORAL, [], "mdmt"),
    "ueq_prag": ("UEQ pragmatic quality", [f"UEQ[UEQ{i}]" for i in range(1, 5)], [], "ueq"),
    "ueq_hed": ("UEQ hedonic quality", [f"UEQ[UEQ{i}]" for i in range(5, 9)], [], "ueq"),
}
SINGLE = {
    "acc": ("Acceptability (ACC)", "CON[ACC]"),
    "ctl": ("Control (CTL)", "CON[CTL]"),
    "int": ("Intention to use (INT)", "CON[INT]"),
    "saw": ("Social appropriateness (SAW1)", "PS[SAW1]"),
}
LABEL = {k: v[0] for k, v in {**SCALES, **SINGLE}.items()}
SHORT = {
    "privacy": "Privacy awareness",
    "acc": "Acceptability",
    "ctl": "Control",
    "ueq_prag": "Pragmatic quality",
    "ueq_hed": "Hedonic quality",
    "trust_perf": "Performance trust",
    "trust_moral": "Moral trust",
    "soccomp": "Social competence",
    "saw": "Appropriateness",
    "int": "Intention to use",
}

# Confirmatory hypotheses: (family, measure, higher, lower)
CONFIRMATORY = [
    ("H1", "privacy", "B", "A"),
    ("H1", "privacy", "C", "A"),
    ("H2", "acc", "B", "A"),
    ("H2", "acc", "C", "A"),
    ("H3", "ctl", "B", "C"),
    ("H4", "ueq_prag", "C", "B"),
]
EXPLORATORY_FRIEDMAN = ["trust_perf", "trust_moral", "soccomp", "saw", "int", "ueq_hed"]
COLORS = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a"}  # dataviz default slots 1-3
INK, INK2 = "#0b0b0b", "#52514e"


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
    df = raw.apply(lambda s: s.str.strip()).replace("", np.nan)
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
        return float(val) - 4  # 1..7 with positive word on the right -> -3..+3
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
            for key, (_, it) in SINGLE.items():
                rec[key] = code(r.get(pre + it), "agree")
            rec["open"] = r.get(pre + "OPEN")
            rows.append(rec)
    long = pd.DataFrame(rows)
    answered = long[[*SCALES, *SINGLE]].notna().any(axis=1)
    return long[answered].reset_index(drop=True)


# --------------------------------------------------------------------------- stats helpers
def rank_biserial(d: np.ndarray) -> float:
    """Matched-pairs rank-biserial r (Kerby 2014): (R+ - R-)/(R+ + R-), zero differences dropped."""
    d = d[d != 0]
    if len(d) == 0:
        return 0.0
    r = stats.rankdata(np.abs(d))
    rp, rm = r[d > 0].sum(), r[d < 0].sum()
    return float((rp - rm) / (rp + rm))


def boot_ci(d: np.ndarray, fn=np.median, rng=None) -> tuple[float, float]:
    rng = rng or np.random.default_rng(SEED)
    idx = rng.integers(0, len(d), size=(N_BOOT, len(d)))
    b = fn(d[idx], axis=1)
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def paired(wide: pd.DataFrame, hi: str, lo: str, alternative: str) -> dict:
    sub = wide[[hi, lo]].dropna()
    x, y = sub[hi].to_numpy(float), sub[lo].to_numpy(float)
    # Scale means are floats, so equal differences (e.g. 5.67 - 4.33 and 3.00 - 1.67) can differ in
    # the last bits and would be ranked as unequal. Rounding keeps theoretical ties tied.
    d = np.round(x - y, 9)
    nz = d[d != 0]
    # How SciPy's method="auto" resolves the p value (SciPy 1.18): exact without ties or zeros
    # for n <= 50; with ties or zeros, exhaustive permutation for n <= 13, otherwise the normal
    # approximation with tie and zero correction (no continuity correction).
    if len(np.unique(np.abs(nz))) == len(nz) == len(d) and len(d) <= 50:
        p_method = "exact"
    elif len(d) <= 13:
        p_method = "permutation"
    else:
        p_method = "normal approximation"
    out = {
        "n": len(d),
        "p_method": p_method,
        "comparison": f"{hi} - {lo}",
        "median_hi": np.median(x),
        "median_lo": np.median(y),
        "mean_diff": d.mean(),
        "median_diff": np.median(d),
        "n_pos": int((d > 0).sum()),
        "n_zero": int((d == 0).sum()),
        "n_neg": int((d < 0).sum()),
    }
    if len(d) < 3 or np.all(d == 0):
        return {
            **out,
            "W": np.nan,
            "p": np.nan,
            "r_rb": np.nan,
            "ci_lo": np.nan,
            "ci_hi": np.nan,
            "t": np.nan,
            "p_t": np.nan,
            "dz": np.nan,
        }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        w = stats.wilcoxon(d, zero_method="pratt", alternative=alternative)
        t = stats.ttest_rel(x, y, alternative=alternative)
    lo_ci, hi_ci = boot_ci(d)
    sd = d.std(ddof=1)
    return {
        **out,
        "W": float(w.statistic),
        "p": float(w.pvalue),
        "r_rb": rank_biserial(d),
        "ci_lo": lo_ci,
        "ci_hi": hi_ci,
        "t": float(t.statistic),
        "p_t": float(t.pvalue),
        "dz": float(d.mean() / sd) if sd > 0 else np.nan,
    }


def holm(p: list[float]) -> list[float]:
    p = np.asarray(p, float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    running = 0.0
    m = len(p)
    for k, i in enumerate(order):
        running = max(running, min(1.0, (m - k) * p[i]))
        adj[i] = running
    return adj.tolist()


def cronbach_alpha(items: pd.DataFrame) -> float:
    items = items.dropna()
    k = items.shape[1]
    if len(items) < 3:
        return np.nan
    var_sum = items.var(ddof=1).sum()
    tot = items.sum(axis=1).var(ddof=1)
    return float(k / (k - 1) * (1 - var_sum / tot)) if tot > 0 else np.nan


def omega_total(items: pd.DataFrame) -> float:
    """McDonald's omega from a one-factor ML model on standardised items (may fail for small n)."""
    items = items.dropna()
    if len(items) <= items.shape[1] or (items.std() == 0).any():
        return np.nan
    try:
        from statsmodels.multivariate.factor import Factor
        from statsmodels.tools.sm_exceptions import ConvergenceWarning

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fa = Factor(items.to_numpy(float), n_factor=1, method="ml").fit()
        if any(issubclass(w.category, ConvergenceWarning) for w in caught):
            return np.nan  # the optimiser did not converge
        lam = np.abs(np.asarray(fa.loadings).ravel())
        psi = np.asarray(fa.uniqueness).ravel()
        if np.any(psi < 0.005):  # Heywood case
            return np.nan
        return float(lam.sum() ** 2 / (lam.sum() ** 2 + psi.sum()))
    except Exception:
        return np.nan


def mixed_model(long: pd.DataFrame, measure: str, ref: str) -> dict:
    """Linear mixed model: measure ~ scenario + position + (1 | id). Robustness check only."""
    import statsmodels.formula.api as smf

    d = long[["id", "scenario", "position", measure]].dropna()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = smf.mixedlm(
                f"{measure} ~ C(scenario, Treatment('{ref}')) + position", d, groups=d["id"]
            ).fit(reml=True)
        coefs = {}
        for name, b in m.params.items():
            if name.startswith("C(scenario"):
                lvl = name.split("T.")[1].rstrip("]")
                coefs[lvl] = (float(b), float(m.bse[name]), float(m.pvalues[name]))
        pos = (float(m.params["position"]), float(m.pvalues["position"]))
        return {"coefs": coefs, "position": pos, "ok": bool(m.converged)}
    except Exception as e:  # pragma: no cover
        return {"coefs": {}, "position": (np.nan, np.nan), "ok": False, "err": str(e)}


# --------------------------------------------------------------------------- output helpers
def fmt_p(p: float) -> str:
    if pd.isna(p):
        return "--"
    return "< .001" if p < 0.001 else f"{p:.3f}".lstrip("0")


def f2(x, nd=2):
    return "--" if pd.isna(x) else f"{x:.{nd}f}"


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
    # The incomplete records were deleted after the final export, as promised to the
    # participants. participant_flow.csv keeps the counts of the full export (numbers only);
    # on an export without incomplete records the recorded counts are reported instead.
    recorded = HERE / "participant_flow.csv"
    if recorded.exists() and len(df) == n:
        rec = pd.read_csv(recorded)
        if int(rec["N"].iloc[-1]) != n:
            raise SystemExit(
                "participant_flow.csv does not match the number of submitted responses"
            )
        flow = rec
    save(flow, "flow", "Participant flow from started to analysed responses.", "tab:study-flow")
    say("# Survey analysis report")
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

    # ---- reliability
    rel_rows = []
    for key, (lab, items, _rev, _) in SCALES.items():
        row = [lab, len(items)]
        for s in "ABC":
            it = long.loc[long.scenario == s, [f"{key}__{i}" for i in items]]
            a, o = cronbach_alpha(it), omega_total(it)
            row += [f2(a), f2(o)]
        rel_rows.append(row)
    rel = pd.DataFrame(
        rel_rows,
        columns=[
            "Scale",
            "Items",
            "alpha A",
            "omega A",
            "alpha B",
            "omega B",
            "alpha C",
            "omega C",
        ],
    )
    save(
        rel,
        "reliability",
        "Internal consistency per scale and scenario (completers).",
        "tab:study-reliability",
        note=r"Cronbach's $\alpha$ and McDonald's $\omega_t$ (one-factor ML model); "
        r"-- = not estimable. Values below .70 are interpreted with caution.",
    )
    say("\n## Reliability\n" + rel.to_string(index=False))

    # ---- descriptives per scenario
    measures = [*SCALES, *SINGLE]
    desc_rows = []
    for m in measures:
        row = [LABEL[m]]
        for s in "ABC":
            v = long.loc[long.scenario == s, m].dropna()
            row.append(
                f"{v.median():.2f} [{v.quantile(0.25):.2f}, {v.quantile(0.75):.2f}]; "
                f"{v.mean():.2f} ({v.std():.2f})"
            )
        desc_rows.append(row)
    desc = pd.DataFrame(desc_rows, columns=["Measure", "A", "B", "C"])
    save(
        desc,
        "descriptives",
        "Scores per scenario: median [IQR]; mean (SD), completers.",
        "tab:study-descriptives",
        colspec="lp{3.6cm}p{3.6cm}p{3.6cm}",
        note="Ranges: agreement items and scales 1--7; MDMT 0--7; UEQ $-3$ to $+3$.",
    )
    say("\n## Descriptives (median [IQR]; mean (SD))\n" + desc.to_string(index=False))

    # ---- exclusion sets
    def wide_for(m, rule, a, b):
        w = long.pivot(index="id", columns="scenario", values=m)
        if rule == "none":
            keep = w.index
        elif rule == "per_comparison":
            keep = chk.index[(chk[a] == True) & (chk[b] == True)]  # noqa: E712
        elif rule == "strict":
            keep = chk.index[(chk == True).all(axis=1)]  # noqa: E712
        return w.loc[w.index.intersection(keep)]

    # ---- power
    try:
        from statsmodels.stats.power import TTestPower

        pw = TTestPower()
        # smallest pair count under the primary rule, and all completers
        n_pair = min(
            int(((chk[a] == True) & (chk[b] == True)).sum())  # noqa: E712
            for a, b in (("A", "B"), ("A", "C"), ("B", "C"))
        )
        for nn in sorted({n_pair, len(chk)}):
            dmin = pw.solve_power(nobs=nn, alpha=ALPHA, power=0.8, alternative="larger")
            say(
                f"Power: n = {nn} pairs, one-sided alpha .05, 80% power -> d_z >= {dmin:.2f} "
                f"(Wilcoxon ARE .955 -> ~{dmin / np.sqrt(0.955):.2f})"
            )
    except Exception:
        pass

    # ---- confirmatory
    conf_rows = []
    for rule in ("per_comparison", "none", "strict"):
        res = []
        for fam, m, hi, lo in CONFIRMATORY:
            r = paired(wide_for(m, rule, hi, lo), hi, lo, "greater")
            res.append({"rule": rule, "family": fam, "measure": m, **r})
        res = pd.DataFrame(res)
        res["p_holm"] = np.nan
        for _fam, g in res.groupby("family"):
            res.loc[g.index, "p_holm"] = holm(g["p"].tolist())
        conf_rows.append(res)
    conf = pd.concat(conf_rows, ignore_index=True)
    # robustness: mixed models on the per-comparison-independent full completer set
    mm = {}
    for _fam, m, hi, lo in CONFIRMATORY:
        key = (m, lo)
        if key not in mm:
            mm[key] = mixed_model(long, m, lo)
        b = mm[key]["coefs"].get(hi, (np.nan, np.nan, np.nan))
        p1 = b[2] / 2 if b[0] > 0 else 1 - b[2] / 2
        conf.loc[(conf.measure == m) & (conf.comparison == f"{hi} - {lo}"), ["lmm_b", "lmm_p1"]] = [
            b[0],
            p1,
        ]
    conf.to_csv(OUT / "confirmatory_all_rules.csv", index=False)

    prim = conf[conf.rule == "per_comparison"]
    tab = pd.DataFrame(
        {
            "H": prim.family,
            "Measure": prim.measure.map(LABEL),
            "Comparison": prim.comparison.str.replace(" - ", " > "),
            "n": prim.n,
            "Mdn diff [95% CI]": [
                f"{a:.2f} [{b:.2f}, {c:.2f}]"
                for a, b, c in zip(prim.median_diff, prim.ci_lo, prim.ci_hi, strict=False)
            ],
            "+/0/-": [
                f"{a}/{b}/{c}" for a, b, c in zip(prim.n_pos, prim.n_zero, prim.n_neg, strict=False)
            ],
            "W": prim.W.map(lambda x: f2(x, 1)),
            "p": prim.p.map(fmt_p),
            "p Holm": prim.p_holm.map(fmt_p),
            "r_rb": prim.r_rb.map(f2),
        }
    )
    save(
        tab,
        "confirmatory",
        "Confirmatory tests (one-sided Wilcoxon signed-rank, Pratt zero handling; "
        "primary per-comparison exclusion).",
        "tab:study-confirmatory",
        colspec="lllrlrrrrr",
        note=r"Mdn diff = median of paired differences (higher $-$ lower) with 95\% percentile "
        r"bootstrap CI. "
        r"+/0/$-$ = number of positive, zero and negative differences. Holm correction within H1 "
        r"and within H2. "
        r"$r_{rb}$ = matched-pairs rank-biserial correlation.",
    )
    rob_tab = []
    for (fam, m, cmpn), g in conf.groupby(["family", "measure", "comparison"], sort=False):
        gg = g.set_index("rule")
        pr = gg.loc["per_comparison"]
        rob_tab.append(
            [
                fam,
                LABEL[m],
                cmpn.replace(" - ", " > "),
                f"{fmt_p(pr.p_holm)} ({pr.n})",
                f"{fmt_p(gg.loc['none'].p_holm)} ({gg.loc['none'].n})",
                f"{fmt_p(gg.loc['strict'].p_holm)} ({gg.loc['strict'].n})",
                f"{fmt_p(pr.p_t)} (dz = {f2(pr.dz)})",
                f"{f2(pr.lmm_b)}; {fmt_p(pr.lmm_p1)}",
            ]
        )
    rob_tab = pd.DataFrame(
        rob_tab,
        columns=[
            "H",
            "Measure",
            "Comparison",
            "Primary p (n)",
            "No excl. p (n)",
            "Strict p (n)",
            "Paired t p",
            "LMM b; p",
        ],
    )
    save(
        rob_tab,
        "confirmatory_robustness",
        "Sensitivity and robustness of the confirmatory tests.",
        "tab:study-robustness",
        colspec="lllllllll",
        note=r"Wilcoxon $p$ values are Holm-adjusted within H1/H2. Paired $t$ uses the primary "
        r"sample "
        r"(one-sided, unadjusted). LMM: linear mixed model (score $\sim$ scenario + position + (1 "
        r"$|$ participant)) "
        r"on all completers; $b$ is the scenario contrast, $p$ one-sided.",
    )
    say("\n## Confirmatory (primary rule)\n" + tab.to_string(index=False))
    say("\n## Robustness\n" + rob_tab.to_string(index=False))

    # ---- H3 scoring sensitivity: CTL has no midpoint (codes 1-3, 5-7). "Equal spacing" closes
    # the gap (5, 6, 7 -> 4, 5, 6); the sign test uses only the direction of each difference.
    h3_rows = []
    for rule in ("per_comparison", "none"):
        w = wide_for("ctl", rule, "B", "C")[["B", "C"]].dropna()
        for scoring, ww in (("original", w), ("equal spacing", w.replace({5: 4, 6: 5, 7: 6}))):
            r = paired(ww, "B", "C", "greater")
            h3_rows.append(
                {
                    "rule": rule,
                    "test": f"Wilcoxon, {scoring}",
                    "n": r["n"],
                    "W": r["W"],
                    "p": r["p"],
                }
            )
        d = (w["B"] - w["C"]).to_numpy(float)
        k, n_nz = int((d > 0).sum()), int((d != 0).sum())
        h3_rows.append(
            {
                "rule": rule,
                "test": f"Sign test ({k} of {n_nz} non-zero differences favour B)",
                "n": len(d),
                "W": np.nan,
                "p": float(stats.binomtest(k, n_nz, alternative="greater").pvalue),
            }
        )
    h3 = pd.DataFrame(h3_rows)
    save(
        pd.DataFrame(
            {
                "Exclusion": h3.rule.map({"per_comparison": "Primary", "none": "None"}),
                "Test": h3.test,
                "n": h3.n,
                "W": h3.W.map(lambda x: f2(x, 1)),
                "p": h3.p.map(fmt_p),
            }
        ),
        "h3_scoring",
        "Sensitivity of H3 (control, B $>$ C) to the scoring of the control item.",
        "tab:study-h3-scoring",
        colspec="llrrr",
        note=r"One-sided tests. Equal spacing scores the answers without a midpoint as 1 to 6.",
    )
    say("\n## H3 scoring sensitivity\n" + h3.to_string(index=False))

    # ---- exploratory: ACC B vs C two-sided
    ex_rows = []
    for rule in ("per_comparison", "none"):
        r = paired(wide_for("acc", rule, "C", "B"), "C", "B", "two-sided")
        ex_rows.append({"rule": rule, **r})
    exbc = pd.DataFrame(ex_rows)
    exbc.to_csv(OUT / "explore_acc_BC.csv", index=False)
    say("\n## Exploratory ACC C - B (two-sided)")
    say(
        exbc[
            [
                "rule",
                "n",
                "median_hi",
                "median_lo",
                "mean_diff",
                "median_diff",
                "ci_lo",
                "ci_hi",
                "n_pos",
                "n_zero",
                "n_neg",
                "W",
                "p",
                "r_rb",
            ]
        ].to_string(index=False)
    )

    # ---- exploratory: Friedman + pairwise (no check exclusions; all completers with 3 scores)
    fr_rows = []
    for m in EXPLORATORY_FRIEDMAN + ["privacy", "acc", "ctl", "ueq_prag"]:
        w = long.pivot(index="id", columns="scenario", values=m).dropna()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fr = stats.friedmanchisquare(w.A, w.B, w.C)
        kw = fr.statistic / (len(w) * 2)
        pair = []
        for a, b in (("B", "A"), ("C", "A"), ("C", "B")):
            pair.append(paired(w, a, b, "two-sided"))
        ph = holm([p["p"] for p in pair])
        fr_rows.append(
            [LABEL[m], len(w), f2(fr.statistic), fmt_p(fr.pvalue), f2(kw)]
            + [
                f"{f2(p['median_diff'])}; {fmt_p(q)}; {f2(p['r_rb'])}"
                for p, q in zip(pair, ph, strict=False)
            ]
        )
    fr_tab = pd.DataFrame(
        fr_rows,
        columns=[
            "Measure",
            "n",
            "chi2(2)",
            "p",
            "Kendall W",
            "B-A: Mdn; p_Holm; r",
            "C-A: Mdn; p_Holm; r",
            "C-B: Mdn; p_Holm; r",
        ],
    )
    save(
        fr_tab,
        "exploratory_friedman",
        "Exploratory omnibus (Friedman) and pairwise two-sided Wilcoxon tests, "
        "all completers with three scores.",
        "tab:study-exploratory",
        colspec="lrrrrlll",
        note="Pairwise cells: median paired difference; Holm-adjusted $p$ across the three pairs; "
        "rank-biserial $r$. "
        "Confirmatory measures are included for completeness; their confirmatory tests are in "
        "Table~\\ref{tab:study-confirmatory}.",
    )
    say("\n## Exploratory Friedman\n" + fr_tab.to_string(index=False))

    # ---- sensitivity (added 2026-11-14, after the primary results): the ratings of a scenario
    # whose manipulation check was failed are set to missing. Friedman: participants with all three
    # checks passed; pairwise: participants who passed both checks of the pair.
    fs_rows = []
    for m in EXPLORATORY_FRIEDMAN + ["privacy", "acc", "ctl", "ueq_prag"]:
        wm = long.pivot(index="id", columns="scenario", values=m).where(chk == True)  # noqa: E712
        w3 = wm.dropna()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fr = stats.friedmanchisquare(w3.A, w3.B, w3.C)
        pair = [paired(wm, a, b, "two-sided") for a, b in (("B", "A"), ("C", "A"), ("C", "B"))]
        ph = holm([p["p"] for p in pair])
        fs_rows.append(
            [
                LABEL[m],
                len(w3),
                f2(fr.statistic),
                fmt_p(fr.pvalue),
                f2(fr.statistic / (len(w3) * 2)),
            ]
            + [
                f"{f2(p['median_diff'])}; {fmt_p(q)}; {f2(p['r_rb'])} ({p['n']})"
                for p, q in zip(pair, ph, strict=False)
            ]
        )
    fs_tab = pd.DataFrame(
        fs_rows,
        columns=[
            "Measure",
            "n",
            "chi2(2)",
            "p",
            "Kendall W",
            "B-A: Mdn; p_Holm; r (n)",
            "C-A: Mdn; p_Holm; r (n)",
            "C-B: Mdn; p_Holm; r (n)",
        ],
    )
    save(
        fs_tab,
        "exploratory_friedman_checks",
        "Sensitivity of the exploratory comparisons: ratings of a "
        "scenario whose manipulation check was failed are excluded.",
        "tab:study-exploratory-checks",
        colspec="lrrrrlll",
        note="Friedman: participants who passed all three checks. Pairwise cells: median paired "
        "difference; "
        "Holm-adjusted $p$ across the three pairs; rank-biserial $r$; $n$ = participants who "
        "passed both checks.",
    )
    say(
        "\n## Exploratory Friedman, failed scenarios excluded (sensitivity)\n"
        + fs_tab.to_string(index=False)
    )

    # ---- order effects
    ord_rows = []
    for m in ["privacy", "acc", "ctl", "ueq_prag", "int"]:
        for s in "ABC":
            g = long[long.scenario == s].dropna(subset=[m, "position"])
            grp = [g.loc[g.position == k, m].to_numpy() for k in (1, 2, 3)]
            ok = [x for x in grp if len(x) > 0]
            p = (
                stats.kruskal(*ok).pvalue
                if len(ok) > 1 and len(np.unique(np.concatenate(ok))) > 1
                else np.nan
            )
            ord_rows.append(
                [LABEL[m], s]
                + [f"{np.median(x):.2f} ({len(x)})" if len(x) else "--" for x in grp]
                + [fmt_p(p)]
            )
    ord_tab = pd.DataFrame(
        ord_rows,
        columns=[
            "Measure",
            "Scen.",
            "Pos. 1 Mdn (n)",
            "Pos. 2 Mdn (n)",
            "Pos. 3 Mdn (n)",
            "Kruskal-Wallis p",
        ],
    )
    save(
        ord_tab,
        "order_effects",
        "Ratings by the position in which a scenario was seen (exploratory, unadjusted).",
        "tab:study-order",
        colspec="llllll",
    )
    say("\n## Order effects\n" + ord_tab.to_string(index=False))
    # first-position only (between-subjects, free of carry-over)
    first = long[long.position == 1]
    say(
        "First-seen scenario only (between-subjects): "
        + ", ".join(
            f"{s}: n={len(first[first.scenario == s])}, ACC "
            f"Mdn={first.loc[first.scenario == s, 'acc'].median()}, "
            f"privacy Mdn={first.loc[first.scenario == s, 'privacy'].median():.2f}"
            for s in "ABC"
        )
    )

    # ---- rankings
    def rank_table(cols, opts):
        rk = pd.DataFrame(index=comp["id"], columns=opts, dtype=float)
        for k, c in enumerate(cols, start=1):
            for pid, v in zip(comp["id"], comp[c], strict=False):
                if pd.notna(v):
                    rk.loc[pid, v] = k
        return rk

    rank = rank_table([f"RANK[{i}]" for i in range(1, 5)], list(RANK_OPTS)).rename(
        columns=RANK_OPTS
    )
    mrank = rank_table([f"MRANK[{i}]" for i in range(1, 4)], MRANK_OPTS)
    rk_rows = []
    for nm, rk in (("Handling", rank), ("Sensing", mrank)):
        rkc = rk.dropna()
        fr = stats.friedmanchisquare(*[rkc[c] for c in rkc.columns])
        say(
            f"\n## Ranking {nm}: n={len(rkc)}, Friedman "
            f"chi2({rkc.shape[1] - 1})={fr.statistic:.2f}, "
            f"p={fmt_p(fr.pvalue)}, W={fr.statistic / (len(rkc) * (rkc.shape[1] - 1)):.2f}"
        )
        for c in rk.columns:
            rk_rows.append(
                [nm, c, int((rk[c] == 1).sum()), f2(rk[c].mean()), f2(rk[c].median(), 1)]
            )
        rk_rows.append(
            [
                nm,
                f"Friedman chi2({rkc.shape[1] - 1}) = {fr.statistic:.2f}, p = {fmt_p(fr.pvalue)}, "
                f"n = {len(rkc)}",
                "",
                "",
                "",
            ]
        )
    rk_tab = pd.DataFrame(
        rk_rows, columns=["Ranking", "Option", "Ranked first", "Mean rank", "Median rank"]
    )
    save(
        rk_tab,
        "rankings",
        "Preferred handling of private reminders (RANK) and preferred sensing (MRANK).",
        "tab:study-rankings",
        colspec="llrrr",
        note="Rank 1 = most preferred.",
    )
    say(rk_tab.to_string(index=False))
    # pairwise among handling options (exploratory)
    rkc = rank.dropna()
    cols = list(rkc.columns)
    pw_rows = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = paired(rkc, cols[i], cols[j], "two-sided")
            pw_rows.append((cols[i], cols[j], r["mean_diff"], r["p"]))
    adj = holm([x[3] for x in pw_rows])
    say(
        "Pairwise RANK (mean rank diff i-j; Holm p): "
        + "; ".join(
            f"{a} vs {b}: {d:+.2f}, p={fmt_p(p)}"
            for (a, b, d, _), p in zip(pw_rows, adj, strict=False)
        )
    )
    say("RANK = position of each option per participant:\n" + rank.astype("Int64").to_string())

    # ---- INFOSENS
    inf = comp.set_index("id")["INFOSENS[REM]"].map(lambda v: code(v, "infosens"))
    say(
        f"\n## INFOSENS: n={inf.notna().sum()}, median={inf.median()}, mean={inf.mean():.2f}, "
        f"dist={inf.value_counts().sort_index().to_dict()}"
    )
    inf_rows = []
    for m in ("privacy", "acc"):
        w = long.pivot(index="id", columns="scenario", values=m)
        for hi in ("B", "C"):
            # round like paired(): mathematically equal differences of means must tie exactly
            dd = (w[hi] - w["A"]).round(9).rename("d").to_frame().join(inf.rename("s")).dropna()
            rho = stats.spearmanr(dd.s, dd.d)
            inf_rows.append([LABEL[m], f"{hi} - A", len(dd), f2(rho.statistic), fmt_p(rho.pvalue)])
    inf_tab = pd.DataFrame(inf_rows, columns=["Measure", "Difference", "n", "Spearman rho", "p"])
    save(
        inf_tab,
        "infosens",
        "Association between rated sensitivity of the reminder and the advantage of B/C over A "
        "(exploratory, unadjusted).",
        "tab:study-infosens",
        colspec="llrrr",
    )
    say(inf_tab.to_string(index=False))

    # ---- free text export (for coding; stays in out/, which is git-ignored)
    ft = []
    for pre, sc in SCEN.items():
        for pid, v in zip(comp["id"], comp[pre + "OPEN"], strict=False):
            if pd.notna(v):
                ft.append((pid, f"OPEN_{sc}", v))
    for col in ("MOTHER", "FINAL"):
        for pid, v in zip(comp["id"], comp[col], strict=False):
            if pd.notna(v):
                ft.append((pid, col, v))
    ft = pd.DataFrame(ft, columns=["id", "field", "text"])
    ft.to_csv(OUT / "free_text.csv", index=False)
    code_free_text(ft, say)

    # ---- figures
    figures(long, rank, mrank, inf)

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


def figures(long: pd.DataFrame, rank: pd.DataFrame, mrank: pd.DataFrame, inf: pd.Series) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 9,
            "axes.edgecolor": INK2,
            "axes.labelcolor": INK,
            "xtick.color": INK2,
            "ytick.color": INK2,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
        }
    )
    rng = np.random.default_rng(SEED)

    def panel(ax, m, ylim, yticks):
        w = long.pivot(index="id", columns="scenario", values=m).dropna()
        jit = rng.uniform(-0.12, 0.12, size=(len(w), 3))
        for i, (_, r) in enumerate(w.iterrows()):
            ax.plot(np.arange(3) + jit[i], r[["A", "B", "C"]], color="#c3c2b7", lw=0.6, zorder=1)
        for k, s in enumerate("ABC"):
            ax.scatter(
                k + jit[:, k], w[s], s=14, color=COLORS[s], edgecolor="#fcfcfb", lw=0.6, zorder=2
            )
            med = w[s].median()
            ax.plot(
                [k - 0.28, k + 0.28], [med, med], color=INK, lw=2, solid_capstyle="round", zorder=3
            )
        ax.set_xticks(range(3), ["A", "B", "C"])
        ax.set_ylim(*ylim)
        ax.set_yticks(yticks)
        ax.yaxis.grid(True, color="#e8e7e2", lw=0.5)
        ax.set_axisbelow(True)
        ax.set_title(f"{SHORT[m]}\n(n = {len(w)})", fontsize=9, color=INK, loc="left")

    def grid(ms, name, ncol=None):
        legend = (
            "A = disclose without asking, B = ask every time, C = ask once and remember\n"
            "black bar = median, grey lines join one participant"
        )
        if ncol is None:  # one row
            fig, axes = plt.subplots(
                1, len(ms), figsize=(1.5 * len(ms) + 0.3, 2.6), constrained_layout=True
            )
        else:  # several rows, so that the figure fits the text width without shrinking
            nrow = -(-len(ms) // ncol)
            fig, axes = plt.subplots(
                nrow, ncol, figsize=(1.85 * ncol + 0.3, 2.45 * nrow), constrained_layout=True
            )
        axes = np.atleast_1d(axes).ravel()
        for ax, m in zip(axes, ms, strict=False):
            if m.startswith("ueq"):
                panel(ax, m, (-3.3, 3.3), range(-3, 4))
            elif m.startswith("trust"):
                panel(ax, m, (-0.3, 7.3), range(0, 8))
            else:
                panel(ax, m, (0.7, 7.3), range(1, 8))
        spare = axes[len(ms) :]
        for ax in spare:
            ax.axis("off")
        if len(spare):  # the legend goes into the first empty panel
            spare[0].text(
                0.06, 0.5, legend.replace(", ", ",\n"), fontsize=7.5, color=INK2, va="center"
            )
        else:
            fig.supxlabel(legend, fontsize=7.5, color=INK2)
        fig.savefig(OUT / f"{name}.pdf")
        plt.close(fig)

    grid(["privacy", "acc", "ctl", "ueq_prag"], "fig_confirmatory")
    grid(["trust_perf", "trust_moral", "soccomp", "saw", "int"], "fig_exploratory", ncol=3)

    # rankings: share of participants placing each option at each rank (sequential blues)
    blues = ["#184f95", "#2a78d6", "#5598e7", "#86b6ef"]  # sequential, light end >= 2:1 on white
    fig, axes = plt.subplots(
        2, 1, figsize=(6.2, 3.8), constrained_layout=True, gridspec_kw={"height_ratios": [4, 3]}
    )
    for ax, rk, title in (
        (axes[0], rank, "Preferred handling (RANK)"),
        (axes[1], mrank, "Preferred sensing (MRANK)"),
    ):
        rk = rk.dropna()
        k = rk.shape[1]
        order = rk.mean().sort_values(ascending=False).index
        left = np.zeros(len(order))
        for r in range(1, k + 1):
            vals = np.array([(rk[c] == r).sum() for c in order])
            ax.barh(
                range(len(order)),
                vals,
                left=left,
                color=blues[r - 1],
                edgecolor="#fcfcfb",
                lw=1,
                label=f"Rank {r}",
                height=0.62,
            )
            left += vals
        ax.set_yticks(range(len(order)), [f"{c} (mean {rk[c].mean():.2f})" for c in order])
        ax.set_xlim(0, len(rk))
        ax.set_xlabel(f"Participants (n = {len(rk)})")
        ax.set_title(title, fontsize=9, loc="left", color=INK)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=4, fontsize=7.5, frameon=False, loc="outside lower center")
    fig.savefig(OUT / "fig_rankings.pdf")
    plt.close(fig)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV)
