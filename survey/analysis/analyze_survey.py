"""Analysis of the consent-scenario vignette study (LimeSurvey 841423).

Run from the repository root:

    uv run --with scipy --with statsmodels --with matplotlib \
        python -I survey/analysis/analyze_survey.py [path/to/export.csv]

Reads the raw LimeSurvey CSV export ("code. question text" headers, answers as text),
drops every IP-address column on load, and writes tidy data, CSV + LaTeX (booktabs)
tables and PDF figures to survey/analysis/out/. No network access. Only MDMT v2, UEQ-S and PSI
Social Competence enter scored inferential analyses (exploratory, not preregistered).
Other questionnaire items are described individually, without composite scores or tests.
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

# Measure definitions. key -> (label, items, reverse items, kind)
MDMT_PERF = [f"MDMT[{d}{i}]" for d in ("REL", "CAP") for i in range(1, 5)]
MDMT_MORAL = [f"MDMT[{d}{i}]" for d in ("ETH", "SIN", "BEN") for i in range(1, 5)]
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

# Exploratory, not preregistered.
HRI_MEASURES = ["trust_perf", "trust_moral", "soccomp", "ueq_prag", "ueq_hed"]
PRIMARY = [("RQ2, RQ3", m) for m in HRI_MEASURES]
PAIRS = (("B", "A"), ("C", "A"), ("C", "B"))
SECONDARY = []
CONTEXT_ITEMS = {
    "privacy_violation": ("Ohbot violated my privacy", "PS[PRAW1]"),
    "privacy_boundaries": ("Ohbot understands privacy boundaries", "PS[PRAW2]"),
    "privacy_aware": ("Ohbot's behaviour was privacy-aware", "PS[PRAW5]"),
    "acc": ("Ohbot's way of handling my permission is acceptable to me", "CON[ACC]"),
    "ctl": ("I felt in control of what Ohbot said in front of Jordan", "CON[CTL]"),
    "int": ("I would use a robot that works this way", "CON[INT]"),
    "saw": ("Ohbot behaved appropriately in the social situation", "PS[SAW1]"),
}
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
    # All current comparisons have n > 13 and tied/zero differences. Explicitly
    # use the normal approximation for consistency across SciPy versions.
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
        w = stats.wilcoxon(d, zero_method="pratt", alternative=alternative, method="approx")
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
    # The flow is computed from the full export (incomplete records included).
    save(flow, "flow", "Participant flow from started to analysed responses.", "tab:study-flow")
    import platform, scipy, statsmodels, matplotlib
    environment = {"python": platform.python_version(), "numpy": np.__version__,
                   "pandas": pd.__version__, "scipy": scipy.__version__,
                   "statsmodels": statsmodels.__version__, "matplotlib": matplotlib.__version__}
    import json
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
    measures = HRI_MEASURES
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
        note="Ranges: PSI Social Competence 1--7 (adapted response format); UEQ-S -3 to +3 (0 = neutral); MDMT 0--7.",
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
            dmin = pw.solve_power(nobs=nn, alpha=ALPHA, power=0.8, alternative="two-sided")
            say(
                f"Power: n = {nn} pairs, two-sided alpha .05, 80% power -> d_z >= {dmin:.2f} "
                "(paired-t sensitivity benchmark only; not Wilcoxon power)"
            )
    except Exception:
        pass

    # ---- main comparisons: two-sided Wilcoxon, Holm across the three pairs of a measure
    conf_rows = []
    for rule in ("per_comparison", "none", "strict"):
        for rq, m in PRIMARY:
            res = [
                {
                    "rule": rule,
                    "rq": rq,
                    "measure": m,
                    **paired(wide_for(m, rule, a, b), a, b, "two-sided"),
                }
                for a, b in PAIRS
            ]
            for r, ph in zip(res, holm([r["p"] for r in res])):
                r["p_holm"] = ph
            conf_rows += res
    conf = pd.DataFrame(conf_rows)
    # robustness: mixed models on all completers (two-sided p of the scenario contrast)
    for _rq, m in PRIMARY:
        for a, b in PAIRS:
            coef = mixed_model(long, m, b)["coefs"].get(a, (np.nan, np.nan, np.nan))
            conf.loc[
                (conf.measure == m) & (conf.comparison == f"{a} - {b}"), ["lmm_b", "lmm_p"]
            ] = [coef[0], coef[2]]
    conf["p_holm_family"] = np.nan
    for rule in conf.rule.unique():
        mask = conf.rule == rule
        conf.loc[mask, "p_holm_family"] = holm(conf.loc[mask, "p"].tolist())
    conf.to_csv(OUT / "primary_all_rules.csv", index=False)

    prim = conf[conf.rule == "per_comparison"]
    tab = pd.DataFrame(
        {
            "RQ": prim.rq,
            "Measure": prim.measure.map(LABEL),
            "Comparison": prim.comparison,
            "n": prim.n,
            "Mdn diff [95% CI]": [
                f"{a:.2f} [{b:.2f}, {c:.2f}]"
                for a, b, c in zip(prim.median_diff, prim.ci_lo, prim.ci_hi)
            ],
            "+/0/-": [
                f"{a}/{b}/{c}" for a, b, c in zip(prim.n_pos, prim.n_zero, prim.n_neg)
            ],
            "W": prim.W.map(lambda x: f2(x, 1)),
            "p": prim.p.map(fmt_p),
            "p Holm": prim.p_holm.map(fmt_p),
            "p family": prim.p_holm_family.map(fmt_p),
            "r_rb": prim.r_rb.map(f2),
            "dz": prim.dz.map(f2),
        }
    )
    save(
        tab,
        "primary",
        "Exploratory HRI comparisons (two-sided Wilcoxon signed-rank tests, Pratt zero handling; "
        "per-comparison exclusion).",
        "tab:study-primary",
        colspec="lllrlrrrrrrr",
        note=r"Mdn diff = median of paired differences (first $-$ second) with 95\% percentile "
        r"bootstrap CI. +/0/$-$ = number of positive, zero and negative differences. $W$ = smaller "
        r"rank sum. Holm correction across three pairs per score; p family corrects all 15 instrument-based comparisons. "
        r"$r_{rb}$ = matched-pairs rank-biserial correlation.",
    )
    rob_tab = []
    for (m, cmpn), g in conf.groupby(["measure", "comparison"], sort=False):
        gg = g.set_index("rule")
        pr = gg.loc["per_comparison"]
        rob_tab.append(
            [
                LABEL[m],
                cmpn,
                f"{fmt_p(pr.p_holm)} ({pr.n})",
                f"{fmt_p(gg.loc['none'].p_holm)} ({gg.loc['none'].n})",
                f"{fmt_p(gg.loc['strict'].p_holm)} ({gg.loc['strict'].n})",
                f"{fmt_p(pr.p_t)} (dz = {f2(pr.dz)})",
                f"{f2(pr.lmm_b)}; {fmt_p(pr.lmm_p)}",
            ]
        )
    rob_tab = pd.DataFrame(
        rob_tab,
        columns=[
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
        "primary_robustness",
        "Sensitivity and robustness of the main comparisons.",
        "tab:study-robustness",
        colspec="lllllll",
        note=r"All $p$ two-sided. Wilcoxon $p$ values are Holm-adjusted across the three pairs of "
        r"a measure. Paired $t$ uses the primary sample (unadjusted). LMM: linear mixed model "
        r"(score $\sim$ scenario + position + (1 $|$ participant)) on all completers; $b$ is the "
        r"scenario contrast.",
    )
    say("\n## Exploratory HRI comparisons (per-comparison rule, two-sided)\n" + tab.to_string(index=False))
    say("\n## Robustness\n" + rob_tab.to_string(index=False))

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

    # ---- exploratory: Friedman + pairwise (no check exclusions; all completers with 3 scores)
    fr_rows = []
    for m in HRI_MEASURES:
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
                for p, q in zip(pair, ph)
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
        "Omnibus (Friedman) and pairwise two-sided Wilcoxon tests for the five instrument-based scores, "
        "all completers with three scores.",
        "tab:study-exploratory",
        colspec="lrrrrlll",
        note="Pairwise cells: median paired difference; Holm-adjusted $p$ across the three pairs; "
        "rank-biserial $r$. "
        "All five scores are exploratory; the check-filtered comparisons are in "
        "Table~\\ref{tab:study-primary}.",
    )
    say("\n## Exploratory Friedman\n" + fr_tab.to_string(index=False))

    # ---- sensitivity: the ratings of a scenario
    # whose manipulation check was failed are set to missing. Friedman: participants with all three
    # checks passed; pairwise: participants who passed both checks of the pair.
    fs_rows = []
    for m in HRI_MEASURES:
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
                for p, q in zip(pair, ph)
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
    for m in HRI_MEASURES:
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
    # ---- rankings
    def rank_table(cols, opts):
        rk = pd.DataFrame(index=comp["id"], columns=opts, dtype=float)
        for k, c in enumerate(cols, start=1):
            for pid, v in zip(comp["id"], comp[c]):
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
        for c in rank_order(rk):
            rk_rows.append(
                [nm, c, int((rk[c] == 1).sum())]
            )
    rk_tab = pd.DataFrame(
        rk_rows, columns=["Ranking", "Option", "Ranked first"]
    )
    save(
        rk_tab,
        "rankings",
        "Preferred handling of private reminders (RANK) and preferred sensing (MRANK).",
        "tab:study-rankings",
        colspec="llr",
        note="Rank 1 = most preferred.",
    )
    say(rk_tab.to_string(index=False))
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
    figures(long, rank, mrank, inf, conf)

    (OUT / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


def rank_order(rk: pd.DataFrame) -> list[str]:
    """Options from most to least preferred: by the number of first ranks, then second ranks, ...,
    so that the option most participants ranked first is listed (and drawn) first."""
    rk = rk.dropna()
    k = rk.shape[1]
    return sorted(
        rk.columns, key=lambda c: tuple(-int((rk[c] == r).sum()) for r in range(1, k + 1))
    )


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


def figures(long: pd.DataFrame, rank: pd.DataFrame, mrank: pd.DataFrame, inf: pd.Series,
            comparisons: pd.DataFrame) -> None:
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
    primary = comparisons[comparisons.rule == "per_comparison"]

    def panel(ax, m, annotate=False):
        w = long.pivot(index="id", columns="scenario", values=m).dropna()
        bp = ax.boxplot([w[sc].to_numpy() for sc in "ABC"], positions=range(3),
                        widths=.54, patch_artist=True, showfliers=True,
                        medianprops={"color": INK, "lw": 1.4},
                        boxprops={"edgecolor": INK2, "lw": .8},
                        whiskerprops={"color": INK2, "lw": .8},
                        capprops={"color": INK2, "lw": .8},
                        flierprops={"marker": "d", "markersize": 3,
                                    "markerfacecolor": INK2, "markeredgecolor": INK2})
        for box, sc in zip(bp["boxes"], "ABC"):
            box.set_facecolor(COLORS[sc]); box.set_alpha(.88)
        if m.startswith("ueq"):
            ax.set_ylim(-3.25, 3.25); ax.set_yticks(range(-3, 4))
            ax.axhline(0, color=INK2, ls="--", lw=.65)
            ylabel = "UEQ-S score (-3 to +3)"
        elif m.startswith("trust"):
            ax.set_ylim(-.25, 7.25); ax.set_yticks(range(8)); ylabel = "MDMT v2 score (0 to 7)"
        elif m == "privacy":
            ax.set_ylim(.75, 7.25); ax.set_yticks(range(1, 8)); ylabel = "Privacy awareness score (1 to 7)"
        else:
            ax.set_ylim(.75, 7.25); ax.set_yticks(range(1, 8)); ylabel = "PSI score (adapted 1 to 7)"
        ylabel = {
            "trust_perf": "Performance trust score",
            "trust_moral": "Moral trust score",
            "soccomp": "Social competence score",
            "ueq_prag": "Pragmatic quality score",
            "ueq_hed": "Hedonic quality score",
        }[m]
        ax.set_ylabel(ylabel, fontsize=9)
        labels = (["A", "B", "C"] if annotate else
                  ["A\nDisclose without\nasking", "B\nAsk every\ntime", "C\nAsk once and\nremember"])
        ax.set_xticks(range(3), labels, fontsize=8)
        ax.set_axisbelow(True)
        names = {"trust_perf": "Performance trust (MDMT v2)",
                 "trust_moral": "Moral trust (MDMT v2)",
                 "soccomp": "Social competence (PSI)",
                 "ueq_prag": "Pragmatic quality (UEQ-S)",
                 "ueq_hed": "Hedonic quality (UEQ-S)"}
        title = names[m].replace(" (", "\n(") if annotate else names[m]
        ax.set_title(title + f"\nDistributions: N = {len(w)}",
                     fontsize=9, pad=67 if annotate else 9)
        if annotate:
            # Axes-fraction heights leave the score axis on its original range.
            for level, (pair, left, right) in enumerate(
                    [("B - A", 0, 1), ("C - B", 1, 2), ("C - A", 0, 2)]):
                row = primary[(primary.measure == m) & (primary.comparison == pair)].iloc[0]
                y = 1.035 + level * .12
                trans = ax.get_xaxis_transform()
                ax.plot([left, left, right, right], [y-.015, y, y, y-.015],
                        color=INK2, lw=.65, transform=trans, clip_on=False)
                p = float(row.p_holm_family)
                pv = "< .001" if p < .001 else f"= {p:.3f}".replace("= 0.", "= .")
                ax.text((left+right)/2, y+.013,
                        rf"$p_{{15}}$ {pv}; n = {int(row.n)}",
                        ha="center", va="bottom", fontsize=8,
                        transform=trans, clip_on=False)

    def grid(ms, name, ncol=None, legend=False, annotate=False):
        nc = ncol or len(ms); nr = -(-len(ms) // nc)
        panel_width = 2.3 if annotate and nc == 3 else 3.05
        fig, axes = plt.subplots(nr, nc, figsize=(panel_width * nc, (4.25 if annotate else 3.55) * nr),
                                 constrained_layout=True)
        axes = np.atleast_1d(axes).ravel()
        for ax, m in zip(axes, ms): panel(ax, m, annotate)
        for ax in axes[len(ms):]: ax.axis("off")
        if legend:
            fig.supxlabel("Boxes = interquartile range; centre line = median.\n"
                          "Whiskers = observations within 1.5 IQR; diamonds = outliers.\n"
                          f"All {long.id.nunique()} completers; axes retain each measure's scoring range.", fontsize=8)
        for ext in ("pdf", "png", "svg"):
            fig.savefig(OUT / f"{name}.{ext}", dpi=220)
        plt.close(fig)

    grid(HRI_MEASURES, "fig_hri_scales", ncol=3)
    grid(["trust_perf", "trust_moral", "soccomp"], "fig_primary", annotate=True)
    grid(["ueq_prag", "ueq_hed"], "fig_secondary", annotate=True)
    grid(["soccomp"], "fig_psi", legend=False)
    grid(["trust_perf", "trust_moral"], "fig_slide_rq2", legend=False)
    grid(["ueq_prag", "ueq_hed"], "fig_slide_rq3", legend=False)
    grid(["soccomp"], "fig_slide_secondary", legend=False)

    # Display the already-computed paired differences; no tests are recalculated.
    fig, axes = plt.subplots(1, 3, figsize=(6.8, 2.7), constrained_layout=True,
                             gridspec_kw={"width_ratios": [1.3, 1.15, 1.3]})
    groups = [(["trust_perf", "trust_moral"], ["Performance", "Moral"], "MDMT v2 points"),
              (["soccomp"], ["Social\ncompetence"], "PSI points (adapted)"),
              (["ueq_prag", "ueq_hed"], ["Pragmatic", "Hedonic"], "UEQ-S points")]
    for ax, (measures, labels, unit) in zip(axes, groups):
        rows = primary[(primary.comparison == "C - B")].set_index("measure").loc[measures]
        y = np.arange(len(measures))
        for yy, (_, row) in zip(y, rows.iterrows()):
            ax.plot([row.ci_lo, row.ci_hi], [yy, yy], color=COLORS["C"], lw=2)
            ax.plot(row.median_diff, yy, "o", color=INK, ms=5)
        ax.axvline(0, color=INK2, lw=.8, ls="--")
        ax.set_yticks(y, labels, fontsize=8)
        ax.set_ylim(len(measures)-.5, -.65)
        ax.set_xlim(min(-.25, rows.ci_lo.min()-.2), max(.25, rows.ci_hi.max()+.2))
        ax.set_xlabel("C minus B (points)", fontsize=9)
        instrument = "MDMT v2" if measures[0].startswith("trust") else "PSI (adapted)" if measures[0] == "soccomp" else "UEQ-S"
        ax.set_title(instrument + f"\nn = {int(rows.n.iloc[0])} pairs", fontsize=9)
    for ext in ("pdf", "png", "svg"):
        fig.savefig(OUT / f"fig_paired_memory.{ext}", dpi=220)
    plt.close(fig)



if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV)
