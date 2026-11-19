# Instrument-based analysis (LimeSurvey 841423)

The main statistical plots and comparisons use only the published item sets of MDMT v2, UEQ-S and PSI Social Competence. These instruments are present in the actual questionnaire; labels are not applied retrospectively to unrelated questions.

| Instrument | Score | Items and scoring |
|---|---|---|
| MDMT v2 (September 2025) | Performance trust | Reliable + Competent; 8 items, mean on 0–7 |
| MDMT v2 (September 2025) | Moral trust | Ethical + Sincere + Benevolent; 12 items, mean on 0–7 |
| UEQ-S | Pragmatic quality | UEQ1–4, subtract 4 then average; −3 to +3 |
| UEQ-S | Hedonic quality | UEQ5–8, subtract 4 then average; −3 to +3 |
| PSI Social Competence | Social competence | SOC1–4, reverse SOC3 as 8 − response; adapted 1–7 response format |

All items must be present for a score. The MDMT not-fit option was omitted; PSI uses seven rather than the original five response categories. The item sets remain published instruments, but these administration adaptations must be disclosed. PSI consistency in scenario A is alpha=.62; internal consistency does not establish validity.

Privacy-awareness items are adapted and are retained individually as response-category counts. Acceptability, control, social appropriateness and intention to use are study-specific single items, also descriptive only. There are no composites, significance tests or main statistical plots for these questions. Preference rankings and sensitivity are descriptive counts, presented in text/tables, with no scale-score plots or inferential tests.

## Sample and statistics

34 completers; 102 participant–scenario records. A = disclose without asking, B = ask every time, C = ask once and remember. All 34 appear in distribution plots. Paired comparisons require both relevant checks passed (B–A n=28, C–A n=29, C–B n=26); no-exclusion and all-checks-passed analyses are sensitivity checks.

Two-sided Wilcoxon signed-rank tests, Pratt zeros, explicit normal approximation, differences rounded to nine decimals. `p_holm` adjusts three pairs within a score; `p_holm_family` adjusts all 15 instrument-based comparisons per exclusion rule. Main interpretation uses the latter. Median paired difference with 95% percentile bootstrap CI (10,000 resamples, seed 20261114); rank-biserial effect size omits zeros. Friedman, paired t and mixed-model results are supplementary. The comparisons are exploratory, as disclosed briefly in the thesis methods.

## Figures and provenance

- `fig_hri_scales.*`: overview of the five instrument-based scores.
- `fig_primary.*`: consolidated MDMT v2 trust factors and PSI Social Competence, with family-adjusted comparisons.
- `fig_secondary.*`: UEQ-S pragmatic and hedonic quality.
- `fig_psi.*`: standalone PSI Social Competence for reuse.
- `fig_paired_memory.*`: existing C-minus-B median paired differences and unadjusted bootstrap intervals, grouped by instrument units.
- `fig_slide_rq2.*`, `fig_slide_rq3.*`, `fig_slide_secondary.*`: MDMT, UEQ-S and PSI slide figures.

Panels name the actual instrument and show its scoring range and sample size. Boxes represent IQRs; centre lines medians; whiskers reach observations within 1.5 IQR; diamonds mark observations beyond. Thesis distribution figures annotate all three pairs using `p_holm_family` from the existing comparison table, with the pair-specific n; they plot all 34 completers. Box definitions appear once in the thesis caption rather than being repeated in the graphic. Paired-difference intervals are descriptive and unadjusted, not equivalence tests. Instrument citations appear directly in the thesis captions and slides. Counts and adapted privacy responses do not appear as established-scale graphs. Earlier output folders are audit archives, not current results.

Sources: [MDMT v2 instructions](https://research.clps.brown.edu/SocCogSci/Measures/MDMT_v2_(2025)_Full_scale.pdf), [UEQ-S materials](https://www.ueq-online.org/), [PSI scoring](https://ipip.ori.org/PSIScalesandScoring.htm).

## Reproduce

```bash
python -m pip install -r survey/analysis/requirements-analysis.txt
python survey/analysis/analyze_survey.py /path/to/final-export.csv
```

Input is read only and IP columns are dropped on load. `out/` is ignored by git because it contains participant-level answers and free text. `environment.json` records versions. `validation.txt` records score and comparison checks. Python 3.9.6, numpy 2.0.2, pandas 2.3.3, scipy 1.13.1, statsmodels 0.14.6 and matplotlib 3.9.4 were used for the current calculation. The notebook uses the same scored-measure list.

To regenerate figures only from the existing scored exports, without rerunning statistical estimation:

```bash
python survey/analysis/render_figures.py
```
