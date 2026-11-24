# Ohbot disclosure-policy study (LimeSurvey 841423)

The questionnaire export contains 284 records. The 34 submitted questionnaires supply 102 participant–policy records. A means disclose without asking, B means ask every time and C means ask once and remember. The same 34 participants supplied all three ratings for every score. The manipulation checks describe understanding of the stories.

| Instrument | Participant score | Scoring |
|---|---|---|
| MDMT v2 | Reliable, Competent, Ethical, Sincere, Benevolent | Mean of four 0–7 items per subscale. The survey omitted the optional *Does not fit* response. |
| MDMT v2 | Performance trust and moral trust | Performance averages Reliable and Competent (8 items). Moral averages Ethical, Sincere and Benevolent (12 items). |
| UEQ-S | Pragmatic and hedonic quality | Subtract 4 from each response. Average items 1–4 and 5–8 separately. Both scales range from −3 to +3. |
| PSI | Social Competence subscale (SOC) | Average SOC1–4 after reversing SOC3 as 8 minus the response on the adapted 1–7 scale. |

All constituent items are required. Each score is compared within participants who have that score in all three policies. The group of completers is the same for all ten scores in this export. The original instruments and scoring rules are cited in the thesis. [MDMT paper](https://arxiv.org/abs/2311.14887) · [MDMT v2 scoring guide](https://research.clps.brown.edu/SocCogSci/Measures/MDMT_v2_%282025%29_Full_scale.pdf) · [UEQ-S paper](https://doi.org/10.9781/ijimai.2017.09.001) · [PSI paper](https://doi.org/10.1145/3415139) · [PSI scoring key](https://ipip.ori.org/PSIScalesandScoring.htm)

## Reproduce the results

With Python 3.12, run these commands from the robot repository root.

```sh
python -m pip install -r survey/analysis/requirements-analysis.txt
python survey/analysis/analyze_survey.py
```

The script accepts an optional path to a LimeSurvey CSV. It reads the export locally and drops the IP column. The ignored `out/` directory holds participant scores and free text alongside the aggregate results. The questionnaire export and participant-level files stay in the research workspace.

To regenerate the six figures and editable appendix tables from the saved result tables and copy the publication assets into the adjacent thesis project, run:

```sh
python survey/analysis/render_figures.py --thesis-dir ../write-up
```

## Statistical outputs

- The score file contains one row per respondent and policy. The descriptive export gives the sample SD, median, mean, unadjusted 95% Student *t* interval for each policy mean, and Cronbach’s alpha calculated across the constituent items within policy.
- The omnibus export gives ten tie-corrected Friedman tests with two degrees of freedom, the raw and ten-test Holm *p* values, and Kendall’s *W*.
- The paired export compares B−A, C−A and C−B for each score. Two-sided Wilcoxon signed-rank tests omit zero differences and assign tied magnitudes their average ranks. The null distribution counts all possible sign assignments to the nonzero differences. Integer item sums preserve ties in fractional score means. Each row gives the full paired sample, the count of nonzero differences, the median change in score points, and raw and 30-test Holm *p* values. Figures use the full-precision adjusted results and show .0496 where three decimals would display .050.
- The rankings export counts each option at every rank in complete ballots, including zero counts. The three sensing options and four handling options each have 34 complete ballots. Individual privacy, social appropriateness, control, acceptability, intention-to-use and sensitivity responses are reported descriptively.
- The agreement figure counts respondents who selected *Somewhat agree*, *Agree* or *Strongly agree* for control (CTL), acceptability (ACC) and intention to use (INT) under each policy. The response-category counts for these items are in **context_response_counts.csv**.

The instrument outputs are **measure_descriptives.csv**, **policy_omnibus.csv** and **policy_pairs.csv**. The rankings are in **ranking_counts.csv**. The publication figures are **fig_mdmt_subscales**, **fig_mdmt_factors**, **fig_ueqs**, **fig_psi_soc**, **fig_agreement** and **fig_rankings**. The renderer creates vector PDFs, PNG previews and the four labelled LaTeX tables in **study_instruments.tex**.

## Optional comments

The codebook records the codes assigned to each of 34 answers from 20 completers. Its accompanying definitions describe each code. The main script reports counts by answer and by participant. A completed independent second-coder sheet can also be used to calculate agreement. Free text and coding sheets are local research data.
