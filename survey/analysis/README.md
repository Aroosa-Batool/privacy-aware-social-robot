# User-study analysis (LimeSurvey 841423)

```bash
uv run --with scipy==1.18.1 --with statsmodels==0.15.0 --with matplotlib==3.11.2 python -I survey/analysis/analyze_survey.py [export.csv]
```

Versions used for the thesis: Python 3.12.16, SciPy 1.18.1, statsmodels 0.15.0, pandas 3.1.0,
NumPy 2.5.4, matplotlib 3.11.2 (pandas and NumPy from `uv.lock`).

Reads the raw export (default `survey/results-survey841423.csv`), drops all IP columns on load,
and writes everything to `survey/analysis/out/` (git-ignored: it contains free text).
Re-run unchanged on a newer export; new free-text answers are listed as UNCODED in
`out/report.md` until they are added to `codebook.csv`.

## Decisions fixed before looking at outcomes (approved 2026-11-14)

- **Sample:** submitted responses only. Partial responses appear only in the flow table. The incomplete
  records were deleted after the final export; `participant_flow.csv` keeps the counts of the
  full export (numbers only) and is used for the flow table when the export contains no
  incomplete records. All other outputs are the same with or without the incomplete records.
- **Manipulation checks, primary rule:** a participant enters a paired comparison only if they passed
  the checks of both scenarios in it. Sensitivity: no exclusion; strict (all three passed).
- **Added after the primary results (2026-11-14), sensitivity only:** exploratory Friedman and pairwise
  tests repeated with the ratings of every failed-check scenario set to missing
  (`out/exploratory_friedman_checks.*`). Not a replacement for the planned all-completer analysis.
- **Speeders:** flagged if total time < median/3; not excluded (none flagged on 14 Nov).
- **Scoring:** as in `Hypotheses – consent-scenario user study.xlsx` (scale means need all items).
- **Confirmatory:** one-sided Wilcoxon signed-rank (Pratt zero handling); matched-pairs rank-biserial r
  (zeros dropped); median paired difference with 95 % percentile bootstrap CI (10 000 resamples,
  seed 20261114). Holm within H1 and within H2; H3 and H4 are single tests. alpha = .05.
- **Robustness:** paired t; linear mixed model score ~ scenario + position + (1 | participant).
  No CLMM: R is not available and statsmodels' ordinal model has no random effects.
- **Exploratory:** two-sided ACC C vs B; Friedman + Holm-corrected pairwise Wilcoxon; order effects
  (Kruskal-Wallis by position, unadjusted); RANK/MRANK; INFOSENS correlations; free-text coding
  (single coder, inductive, `codebook_definitions.csv` + `codebook.csv`).

## Results summary (export of 2026-11-14, N = 22 completers)

Power: with 22 pairs a one-sided test at alpha = .05 has 80 % power only for d_z >= 0.55
(16 pairs: d_z >= 0.65).

| Hypothesis | Verdict | Test (primary rule) | p (Holm) | r_rb | Mdn diff [95 % CI] | n |
|---|---|---|---|---|---|---|
| H1 privacy awareness B > A | supported | W = 168.0 | < .001 | .99 | 3.17 [2.00, 4.33] | 18 |
| H1 privacy awareness C > A | supported | W = 162.0 | < .001 | .89 | 2.00 [1.00, 3.67] | 18 |
| H2 acceptability B > A | supported | W = 160.0 | < .001 | .97 | 2.00 [1.00, 4.00] | 18 |
| H2 acceptability C > A | supported | W = 157.5 | < .001 | .90 | 2.50 [1.50, 4.00] | 18 |
| H3 control B > C | supported (modest; CI touches 0) | W = 102.5 | .030 | .57 | 2.00 [0.00, 3.00] | 16 |
| H4 pragmatic quality C > B | not supported | W = 68.5 | .490 | .01 | 0.38 [-1.00, 0.88] | 16 |
| Expl. acceptability C vs B (two-sided) | no difference detected | W = 45.0 | .413 | -.24 | 0.00 [-1.00, 0.50] | 16 |

H1/H2 hold under all three exclusion rules, paired t and the mixed model. H3: no exclusion
p = .048 (n = 21), paired t p = .025, LMM p = .020. H4: p >= .48 everywhere.
Reliability: UEQ pragmatic alpha = .57 in scenario C, social competence alpha = .63 in A.

H3 also depends on the scoring of the control item: with equally spaced options (1-6) p = .032,
without exclusions p = .054; sign test (10 vs 4) p = .090. These variants are written to
`out/h3_scoring.csv` / `.tex` and to `out/report.md`.

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
  `out/confirmatory_all_rules.csv` and `out/explore_acc_BC.csv`.

## Free-text coding audit trail

`codebook_definitions.csv` defines the 17 codes and their five themes; `codebook.csv` assigns codes
to each of the 24 answers (response id, question, codes). Single coder; `out/report.md` lists any
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
