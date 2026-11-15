# User-study analysis (LimeSurvey 841423)

```bash
uv run --with scipy --with statsmodels --with matplotlib python -I survey/analysis/analyze_survey.py [export.csv]
```

Reads the raw export (default `survey/results-survey841423.csv`), drops all IP columns on load,
and writes everything to `survey/analysis/out/` (git-ignored: it contains free text).
Re-run unchanged on a newer export; new free-text answers are listed as UNCODED in
`out/report.md` until they are added to `codebook.csv`.

## Decisions fixed before looking at outcomes (approved 2026-11-14)

- **Sample:** submitted responses only. Partial responses appear only in the flow table.
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
| H1 privacy awareness C > A | supported | W = 163.0 | < .001 | .91 | 2.00 [1.00, 3.67] | 18 |
| H2 acceptability B > A | supported | W = 160.0 | < .001 | .97 | 2.00 [1.00, 4.00] | 18 |
| H2 acceptability C > A | supported | W = 157.5 | < .001 | .90 | 2.50 [1.50, 4.00] | 18 |
| H3 control B > C | supported (modest; CI touches 0) | W = 102.5 | .030 | .57 | 2.00 [0.00, 3.00] | 16 |
| H4 pragmatic quality C > B | not supported | W = 68.5 | .490 | .01 | 0.38 [-1.00, 0.88] | 16 |
| Expl. acceptability C vs B (two-sided) | no difference detected | W = 45.0 | .413 | -.24 | 0.00 [-1.00, 0.50] | 16 |

H1/H2 hold under all three exclusion rules, paired t and the mixed model. H3: no exclusion
p = .048 (n = 21), paired t p = .025, LMM p = .020. H4: p >= .48 everywhere.
Reliability: UEQ pragmatic alpha = .57 in scenario C, social competence alpha = .63 in A.
