import itertools
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import analyze_survey as study


def enumerate_signs(differences):
    values = [d for d in differences if d]
    magnitudes = sorted(abs(d) for d in values)
    ranks = [
        np.mean([i for i, value in enumerate(magnitudes, 1) if value == abs(d)])
        for d in values
    ]
    observed = abs(sum(np.sign(d) * r for d, r in zip(values, ranks)))
    signs = itertools.product((-1, 1), repeat=len(values))
    extreme = sum(abs(sum(s * r for s, r in zip(assignment, ranks))) >= observed
                  for assignment in signs)
    return extreme / 2 ** len(values)


class StudyStatisticsTest(unittest.TestCase):
    def test_exact_distribution_including_ties_and_zeros(self):
        for values in ([0, 0], [2], [-2, 2, 0], [0, 1, -1, 2, 2, 2], [1, 2, 3, 4, 5, -6]):
            with self.subTest(values=values):
                expected = enumerate_signs(values)
                self.assertEqual(study.exact_signed_rank(np.array(values)), expected)
                self.assertEqual(study.exact_signed_rank(-np.array(values)), expected)

    def test_tied_changes_in_twelve_item_factor(self):
        totals_a = [14, 31, 55, 47, 62, 71]
        differences = [1, -1, 1, 2, 1, -1]
        rows = []
        for pid, (a, change) in enumerate(zip(totals_a, differences)):
            for condition, total in zip("ABC", [a, a + change, a]):
                # Spread the integer total over twelve valid 0–7 item ratings.
                items = [total // 12 + int(i < total % 12) for i in range(12)]
                row = dict(zip(study.ITEM_COLUMNS["trust_moral"], items))
                rows.append(dict(row, id=pid, scenario=condition, trust_moral=total / 12))
        with patch.object(study, "MEASURE_GROUPS", {"mdmt_factors": ["trust_moral"]}):
            _, _, pairs = study.instrument_results(pd.DataFrame(rows))
        ba = pairs.set_index(["first", "second"]).loc["B", "A"]
        self.assertEqual(ba.p_raw, enumerate_signs(differences))
        self.assertEqual(ba.n_nonzero, len(differences))

    def test_holm_preserves_input_order_and_ties(self):
        np.testing.assert_allclose(study.holm([.1, .01, .8, .01]), [.2, .04, .8, .04])

    def test_ranking_counts_include_zero_and_reject_duplicate_options(self):
        ballot = {f"MRANK[{i}]": x for i, x in enumerate(study.MRANK_OPTS, 1)}
        ballot.update({f"RANK[{i}]": x for i, x in enumerate(study.RANK_OPTS, 1)})
        data = pd.DataFrame([ballot])
        counts = study.ranking_counts(data)
        self.assertEqual(len(counts), 25)
        self.assertEqual(counts["count"].eq(0).sum(), 18)
        self.assertTrue(counts.groupby(["group", "rank"])["count"].sum().eq(1).all())
        data["MRANK[2]"] = data["MRANK[1]"]
        with self.assertRaisesRegex(ValueError, "Invalid sensing ranking"):
            study.ranking_counts(data)
