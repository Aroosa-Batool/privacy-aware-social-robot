"""Render the study plots and appendix tables from the scored survey exports."""

import argparse
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd


OUT = Path(__file__).resolve().parent / "out"
POLICIES = {
    "A": ("Disclose without asking", "#5596c7"),
    "B": ("Ask every time", "#e48d53"),
    "C": ("Ask once and remember", "#50aa8d"),
}
RANK_COLOURS = ["#205f73", "#77adb6", "#e5c9a7", "#ac6548"]
MDMT_CITE = "malle2023mdmt,ullman2023mdmt"
# group -> title, axis label, scale endpoints, instrument citations
INSTRUMENTS = {
    "mdmt_subscales": ("MDMT v2 trust subscales", "MDMT v2 subscale score", (0, 7), MDMT_CITE),
    "mdmt_factors": ("MDMT v2 trust factors", "MDMT v2 factor score", (0, 7), MDMT_CITE),
    "ueqs": ("UEQ-S pragmatic and hedonic quality", "UEQ-S score", (-3, 3), "schrepp2017ueqs"),
    "psi_soc": ("Social Competence subscale of PSI", "PSI Social Competence score", (1, 7),
                "barchard2020psi,barchard2018psimanual"),
}


def format_p(p):
    if pd.isna(p):
        return r"\mathrm{n/a}"
    if p < .001:
        return "<.001"
    # Three decimals would put a value on .050 even though it is on one side of .05.
    precision = 4 if f"{p:.3f}" == "0.050" and p != .05 else 3
    return f"{p:.{precision}f}".lstrip("0")


def save_plot(fig, directory, name):
    fig.savefig(directory / f"{name}.pdf", metadata={"CreationDate": None})
    fig.savefig(directory / f"{name}.png", dpi=200)
    plt.close(fig)


def plot_policies(scores, descriptions, pairs, group, directory):
    _, axis_label, (low, high), _ = INSTRUMENTS[group]
    measures = descriptions[["measure", "label"]].drop_duplicates()
    p_values = pairs.set_index(["measure", "first", "second"]).p_holm
    is_subscale = group == "mdmt_subscales"
    fig, ax = plt.subplots(figsize=(6.1, 3.12 if is_subscale else 2.85))
    fig.subplots_adjust(left=.085, right=.99, bottom=.235, top=.685 if is_subscale else .72)
    centres = np.arange(len(measures))
    offsets = {"A": -.27, "B": 0, "C": .27}
    trans = ax.get_xaxis_transform()
    for centre, measure in zip(centres, measures.measure):
        matched = scores.pivot(index="id", columns="scenario", values=measure).dropna()
        for policy, (_, colour) in POLICIES.items():
            ax.boxplot(matched[policy], positions=[centre + offsets[policy]], widths=.22,
                       patch_artist=True, manage_ticks=False, whis=1.5,
                       boxprops={"facecolor": colour, "edgecolor": "#253744", "linewidth": .8},
                       medianprops={"color": "#182a35", "linewidth": 1.25},
                       whiskerprops={"color": "#454e53", "linewidth": .75},
                       capprops={"color": "#454e53", "linewidth": .75},
                       flierprops={"marker": "d", "markersize": 2.5, "markerfacecolor": "#566570",
                                   "markeredgecolor": "#354851", "markeredgewidth": .45})
        for layer, (first, second) in enumerate([("B", "A"), ("C", "B"), ("C", "A")]):
            left, right = centre + offsets[second], centre + offsets[first]
            h = 1.025 + layer * .138
            ax.plot([left, left, right, right], [h - .022, h, h, h - .022], transform=trans,
                    color="#343e45", lw=.65, clip_on=False)
            value = format_p(p_values.loc[measure, first, second])
            annotation = f"p < {value[1:]}" if value.startswith("<") else f"p = {value}"
            ax.text((left + right) / 2, h + .010, annotation, transform=trans,
                    ha="center", va="bottom", fontsize=7.7)
    if is_subscale:
        ax.axvline(1.5, color="#c4cbd0", lw=.6)
        for centre, label in [(.5, "Performance trust"), (3, "Moral trust")]:
            ax.text(centre, 1.52, label, transform=trans, ha="center", va="center",
                    weight="semibold", fontsize=8.6)
    ax.set_xlim(-.55, len(measures) - .45)
    ax.set_ylim(low - .12, high + .12)
    ax.set_yticks(range(low, high + 1))
    ax.set_ylabel(axis_label)
    ax.set_xticks(centres, ["Social Competence (SOC)"] if group == "psi_soc" else measures.label)
    ax.tick_params(axis="x", length=0, pad=4)
    ax.tick_params(axis="y", length=2.5)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#e3e7e8", lw=.55)
    if group == "ueqs":
        ax.axhline(0, color="#59666d", linestyle="--", linewidth=.8)
    handles = [Patch(facecolor=c, edgecolor="#384857", lw=.6, label=f"{p}  {lab}")
               for p, (lab, c) in POLICIES.items()]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.53, .072), ncol=3,
               handlelength=1.3, handletextpad=.42, columnspacing=1.4, frameon=False, fontsize=8.1)
    sizes = descriptions.n.unique()
    sample = f"{sizes[0]} participants" if len(sizes) == 1 else f"{sizes.min()}–{sizes.max()} participants per score"
    fig.text(.53, .028, f"{sample}   ·   Brackets show Holm-adjusted p across 30 paired tests",
             ha="center", color="#414d54", fontsize=7.3)
    save_plot(fig, directory, f"fig_{group}")


def plot_agreement(scores, directory):
    items = {"ctl": "Felt in control", "acc": "Found it acceptable", "int": "Would use it"}
    answers = scores.set_index("scenario")[list(items)]
    counts = answers.isin([5, 6, 7]).groupby(level=0).sum().reindex(POLICIES, fill_value=0)
    denominators = answers.groupby(level=0).count().reindex(POLICIES, fill_value=0)
    n = scores.id.nunique()
    complete = denominators.eq(n).all().all()

    fig, axes = plt.subplots(1, 3, sharey=True, figsize=(7.1, 2.77))
    fig.subplots_adjust(left=.224, right=.978, bottom=.244, top=.695, wspace=.195)
    fig.text(.012, .959, "Agreement with each disclosure policy", va="top",
             fontsize=14.0, weight="bold")
    subtitle = (f"Number of participants who agreed, out of {n}" if complete
                else "Number of participants who agreed / number who answered")
    fig.text(.012, .825, subtitle, va="top", fontsize=8.9)

    ticks = MaxNLocator(nbins=4, integer=True, steps=[1, 2, 5, 10]).tick_values(0, n)
    ticks = [tick for tick in ticks if 0 <= tick <= .85 * n] + [n]
    rows = np.arange(len(POLICIES))
    colours = [colour for _, colour in POLICIES.values()]
    axes[0].set_yticks(rows, [label for label, _ in POLICIES.values()])
    axes[0].set_ylim(len(rows) - .5, -.5)
    for ax, (item, title) in zip(axes, items.items()):
        values = counts[item].to_numpy(dtype=int)
        ax.barh(rows, values, height=.49, color=colours, zorder=2)
        for y, (value, answered) in enumerate(zip(values, denominators[item])):
            label = str(value) if complete else f"{value}/{answered}"
            inside = value > (.85 if complete else .65) * n
            ax.annotate(label, (value, y), xytext=(-3 if inside else 3, 0),
                        textcoords="offset points", va="center", ha="right" if inside else "left",
                        color="white" if inside else "#182a35", weight="bold", fontsize=8.7)
        ax.set_title(title, fontsize=9.6, weight="bold", pad=4)
        ax.set_xlim(0, n)
        ax.set_xticks(ticks)
        ax.tick_params(axis="both", length=0, labelsize=8.1, pad=3)
        ax.set_axisbelow(True)
        ax.grid(axis="x", color="#dce1e4", linewidth=.65)
        for spine in ax.spines.values():
            spine.set_visible(False)
    note = "Agreement includes “somewhat agree”, “agree” and “strongly agree”."
    if complete:
        note += f" The same {n} participants rated all three policies."
    fig.text(.012, .045, note, va="bottom", fontsize=7.3)
    save_plot(fig, directory, "fig_agreement")


def plot_rankings(ranks, directory):
    fig, axes = plt.subplots(2, 1, figsize=(6.1, 3.72), gridspec_kw={"height_ratios": [3, 4]})
    fig.subplots_adjust(left=.355, right=.985, bottom=.12, top=.915, hspace=.58)
    headings = {"Sensing": "Detecting a bystander", "Handling": "Handling a private reminder"}
    for ax, (group, title) in zip(axes, headings.items()):
        data = ranks[ranks.group.eq(group)]
        counts = data.pivot(index="option", columns="rank", values="count").loc[data.option.unique()]
        left = np.zeros(len(counts), dtype=int)
        for position in counts:
            width = counts[position].to_numpy()
            bars = ax.barh(counts.index, width, left=left, height=.66,
                           color=RANK_COLOURS[position - 1], edgecolor="white", linewidth=.7)
            labels = [str(n) if n else "" for n in width]
            ax.bar_label(bars, labels=labels, label_type="center", fontsize=8.5,
                         color="white" if position in (1, 4) else "#19333b")
            left += width
        ax.set_xlim(0, int(data.n.max()))
        ax.invert_yaxis()
        ax.set_title(title, loc="left", fontsize=10, weight="semibold", pad=4)
        ax.set_xticks([])
        ax.tick_params(axis="y", length=0, labelsize=8, pad=4)
        for spine in ax.spines.values():
            spine.set_visible(False)
    handles = [Patch(facecolor=c, label=label) for c, label in
               zip(RANK_COLOURS, ["1st choice", "2nd choice", "3rd choice", "4th choice"])]
    fig.legend(handles=handles, loc="lower center", frameon=False, ncol=4,
               handlelength=1.5, columnspacing=1.6, fontsize=8.2)
    save_plot(fig, directory, "fig_rankings")


def write_tables(descriptions, omnibus, directory):
    lines = ["% Generated by survey/analysis/render_figures.py from the survey exports."]
    for group, (title, _, _, sources) in INSTRUMENTS.items():
        rows = descriptions[descriptions.group.eq(group)]
        tests = omnibus[omnibus.group.eq(group)]
        sizes = rows.n.unique()
        sample = (f"Each policy includes the same {sizes[0]} participants."
                  if len(sizes) == 1 else "The sample for each score comprises complete sets of three policy ratings.")
        if group == "mdmt_factors":
            lines.append(r"\clearpage")
        lines.extend([
            r"\begin{center}\begin{minipage}{\linewidth}", r"\captionsetup{type=table}",
            r"\centering\footnotesize",
            rf"\caption[{title} by policy]{{{title} by policy~\cite{{{sources}}}. {sample}}}",
            rf"\label{{tab:study-{group.replace('_', '-')}}}",
            r"\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}lcrrrrr@{}}", r"\toprule",
            r"Score & Policy & Mean & SD & Median & 95\,\% CI of mean & $\alpha$ \\",
            r"\midrule",
        ])
        for row in rows.itertuples():
            label = row.label if row.policy == "A" else ""
            if row.policy == "A" and row.Index != rows.index[0]:
                lines.append(r"\addlinespace[2pt]")
            alpha = rf"${row.alpha:.2f}$" if pd.notna(row.alpha) else "--"
            lines.append(rf"{label} & {row.policy} & ${row.mean:.2f}$ & ${row.sd:.2f}$ & "
                         rf"${row.median:.2f}$ & $[{row.ci_low:.2f}, {row.ci_high:.2f}]$ & {alpha} \\")
        lines.extend([
            r"\bottomrule\end{tabular*}", r"\par\medskip",
            r"\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}lrrrr@{}}", r"\toprule",
            r"Score & Friedman $\chi^2(2)$ & Raw $p$ & Holm $p$ & Kendall's $W$ \\",
            r"\midrule",
        ])
        for row in tests.itertuples():
            chi = f"{row.chi2:.2f}" if pd.notna(row.chi2) else r"\mathrm{n/a}"
            w = f"{row.kendall_w:.3f}" if pd.notna(row.kendall_w) else r"\mathrm{n/a}"
            lines.append(rf"{row.label} & ${chi}$ & ${format_p(row.p_raw)}$ & "
                         rf"${format_p(row.p_holm)}$ & ${w}$ \\")
        lines.extend([r"\bottomrule\end{tabular*}", r"\end{minipage}\end{center}", ""])
    (directory / "study_instruments.tex").write_text("\n".join(lines), encoding="utf-8")


def render_results(scores, descriptions, omnibus, pairs, rankings, directory):
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 8.6,
                         "pdf.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#637079", "axes.linewidth": .65,
                         "text.color": "#182a35", "xtick.color": "#273840", "ytick.color": "#273840"}):
        for group in INSTRUMENTS:
            plot_policies(scores, descriptions[descriptions.group.eq(group)], pairs, group, directory)
        plot_agreement(scores, directory)
        plot_rankings(rankings, directory)
    write_tables(descriptions, omnibus, directory)


def publish_to_thesis(directory, thesis):
    if not (thesis / "main.tex").is_file():
        raise ValueError(f"{thesis} does not contain the thesis main.tex")
    images = thesis / "images" / "study"
    tables = thesis / "tables"
    images.mkdir(parents=True, exist_ok=True)
    tables.mkdir(exist_ok=True)
    for name in [*INSTRUMENTS, "agreement", "rankings"]:
        shutil.copyfile(directory / f"fig_{name}.pdf", images / f"fig_{name}.pdf")
    shutil.copyfile(directory / "study_instruments.tex", tables / "study_instruments.tex")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thesis-dir", type=Path, help="Copy the study figure PDFs and editable tables into this LaTeX project")
    args = parser.parse_args()
    stems = ["long_scores", "measure_descriptives", "policy_omnibus", "policy_pairs", "ranking_counts"]
    inputs = [pd.read_csv(OUT / f"{stem}.csv", float_precision="round_trip") for stem in stems]
    render_results(*inputs, OUT)
    if args.thesis_dir:
        publish_to_thesis(OUT, args.thesis_dir)
