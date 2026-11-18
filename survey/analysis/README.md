# User-study analysis (LimeSurvey 841423)

```bash
uv run --with scipy==1.18.1 --with statsmodels==0.15.0 --with matplotlib==3.11.2 python -I survey/analysis/analyze_survey.py [export.csv]
```

Versions used for the thesis: Python 3.12.16, SciPy 1.18.1, statsmodels 0.15.0, pandas 3.1.0,
NumPy 2.5.4, matplotlib 3.11.2 (pandas and NumPy from `uv.lock`).

Reads the raw export (default `survey/results-survey841423_Latest.csv`), drops all IP columns on load,
and writes everything to `survey/analysis/out/` (git-ignored: it contains free text).
Re-run unchanged on a newer export; new free-text answers are listed as UNCODED in
`out/report.md` until they are added to `codebook.csv`.

## The study

One online vignette survey (LimeSurvey 841423), open from 10 to 18 November 2026. **34 participants**
submitted it; these 34 responses are the data set of the thesis. Each participant rated three
policies for a private reminder that becomes due while a visitor is present: A = disclose without
asking, B = ask every time, C = ask once and remember.

## Analysis

- **Sample:** submitted responses only. Partial responses appear only in the flow table. The incomplete
  records were deleted after the final export; `participant_flow.csv` keeps the counts of the
  full export (numbers only) and is used for the flow table when the export contains no
  incomplete records. All other outputs are the same with or without the incomplete records.
- **Questions:** the study asks open questions (Q2.1-Q3.4 in the thesis), so every pairwise test is
  two-sided.
- **Main comparisons:** privacy awareness, acceptability, control and UEQ-S pragmatic quality, each
  compared for all three pairs (B - A, C - A, C - B) and Holm-adjusted across the three pairs of a
  measure (`out/primary.*`, `out/primary_all_rules.csv`, `out/primary_robustness.*`).
- **Manipulation checks, primary rule:** a participant enters a paired comparison only if they passed
  the checks of both scenarios in it. Sensitivity: no exclusion; strict (all three passed).
- **Speeders:** flagged if total time < median/3; not excluded (none flagged).
- **Scoring:** scale means need all items. ACC, CTL and INT have six options scored 1, 2, 3, 5, 6, 7.
  UEQ-S scores are reported from 1 to 7 as answered (official UEQ-S score = value - 4), so that all
  figures and tables share one axis.
- **Tests:** Wilcoxon signed-rank (Pratt zero handling); matched-pairs rank-biserial r (zeros dropped);
  median paired difference with 95 % percentile bootstrap CI (10 000 resamples, seed 20261114). alpha = .05.
- **Robustness:** paired t; linear mixed model score ~ scenario + position + (1 | participant).
  No CLMM: R is not available and statsmodels' ordinal model has no random effects.
- **Remaining measures:** Friedman + Holm-corrected pairwise Wilcoxon (`out/exploratory_friedman.*`),
  repeated as a sensitivity analysis with the ratings of every failed-check scenario set to missing
  (`out/exploratory_friedman_checks.*`).
- **Other analyses:** order effects (Kruskal-Wallis by position, unadjusted); RANK/MRANK;
  INFOSENS correlations; free-text coding (single coder, inductive, `codebook_definitions.csv` +
  `codebook.csv`).
- **Figures:** box plots on a common axis from 0 to 7 (`fig_primary.pdf`, `fig_secondary.pdf`, slide
  variants `fig_slide_*.pdf`). In `fig_rankings.pdf` the options are ordered by the number of first
  ranks (then second ranks), most preferred at the top.

## Results summary (N = 34)

Power: with 34 pairs a two-sided test at alpha = .05 has 80 % power for d_z >= 0.50
(26 pairs: d_z >= 0.57).

| Measure | Pair | n | Mdn diff [95 % CI] | W | p (Holm) | r_rb |
|---|---|---|---|---|---|---|
| Privacy awareness | B - A | 28 | 3.50 [2.33, 4.50] | 15.0 | < .001 | .95 |
| | C - A | 29 | 2.33 [1.00, 3.67] | 39.0 | < .001 | .85 |
| | C - B | 26 | -0.50 [-2.00, 0.17] | 82.5 | .025 | -.60 |
| Acceptability (ACC) | B - A | 28 | 3.00 [2.00, 4.00] | 7.0 | < .001 | .99 |
| | C - A | 29 | 2.00 [1.00, 4.00] | 28.5 | < .001 | .90 |
| | C - B | 26 | 0.00 [-1.50, 0.00] | 100.5 | .171 | -.39 |
| Control (CTL) | B - A | 27 | 4.00 [2.00, 5.00] | 16.5 | < .001 | .95 |
| | C - A | 29 | 1.00 [0.00, 3.00] | 45.0 | .002 | .83 |
| | C - B | 26 | -1.50 [-3.00, 0.00] | 53.5 | .003 | -.71 |
| UEQ-S pragmatic quality | B - A | 28 | 0.50 [0.00, 1.25] | 111.0 | .127 | .46 |
| | C - A | 29 | 0.25 [0.00, 1.00] | 150.0 | .351 | .30 |
| | C - B | 26 | -0.12 [-0.75, 0.50] | 162.5 | .750 | -.07 |

Both asking policies are rated far above disclosing without asking on privacy awareness, acceptability
and control under every exclusion rule, in paired t tests and in the mixed model. Control is lower
when the answer is remembered than when the robot asks every time, also under every variant
(no exclusion p = .003, paired t p = .002, LMM p < .001; with equally spaced control options and in a
sign test as well, `out/control_scoring.*`). Privacy awareness C - B is not robust (no exclusion
p = .087). Pragmatic quality and acceptability do not differ detectably between B and C.
Reliability: only social competence in scenario A is below .70 (alpha = .62).

## Reliability and bootstrap details

- **McDonald's omega_t:** one-factor maximum-likelihood factor model on the items
  (`statsmodels.multivariate.factor.Factor`, `method="ml"`), omega = (sum of |loadings|)^2 /
  ((sum of |loadings|)^2 + sum of uniquenesses). Reported as not estimable (`--`) if the scale has
  at least as many items as complete cases, an item has zero variance, the fit fails, or a
  uniqueness is below .005 (Heywood case). Non-convergence is detected from statsmodels'
  `ConvergenceWarning`; in this data set every non-converged fit was also a Heywood case, so the
  check removes no reported value.
- **Bootstrap:** percentile CI of the median paired difference, 10 000 resamples; every CI starts
  a new `numpy.random.default_rng(20261114)`, so each interval is reproducible on its own.
- **Ties:** score differences are rounded to 9 decimals before ranking (Wilcoxon and Spearman),
  so mathematically equal differences of item means tie exactly.
- **Wilcoxon p values:** `scipy.stats.wilcoxon(..., zero_method="pratt")` with the default
  `method="auto"`. Because every comparison has tied or zero differences and n > 13, SciPy uses
  the normal approximation with tie and Pratt zero correction and no continuity correction; the
  method actually used is recorded per test in the `p_method` column of
  `out/primary_all_rules.csv`.

## Free-text coding audit trail

`codebook_definitions.csv` defines the 18 codes and their five themes; `codebook.csv` assigns codes
to each of the 35 answers (response id, question, codes). Single coder; `out/report.md` lists any
answer not yet coded as UNCODED.

Procedure: (1) all answers were read; (2) each answer (one text field of one participant) received
one or more short codes close to its wording; (3) overlapping codes were merged and every code was
given a written definition (`codebook_definitions.csv`); (4) all answers were coded again with these
definitions (`codebook.csv`); (5) codes were grouped into themes by the question they address.

Second coder (optional): give a second person `codebook_definitions.csv` and
`out/coding_sheet_second_coder.csv` (answers in shuffled order, without codes; written to `out/`
only because it contains the raw answers). They fill the `codes` column with codes from the
definitions, separated by `;`, and save it as `codebook_coder2.csv` (columns `id,field,codes`) next
to `codebook.csv`. The next run reports Cohen's kappa over all answer x code decisions, kappa per
code and the share of answers with identical code sets (`out/free_text_agreement.csv`).
