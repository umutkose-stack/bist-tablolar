"""Veri çekme hesapları için regresyon testleri (ağ gerektirmez).

Çalıştırma:  python -m unittest discover -s tests -p "test_*.py"
"""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_data as fd  # noqa: E402


def quarters_back(end: str, n: int) -> list[str]:
    return [fd.shift_q(end, -i) for i in range(n)]


class TTMTests(unittest.TestCase):
    def test_shift_across_year(self):
        self.assertEqual(fd.shift_q("2026Q1", -1), "2025Q4")
        self.assertEqual(fd.shift_q("2025Q4", 1), "2026Q1")
        self.assertEqual(fd.shift_q("2026Q3", -4), "2025Q3")

    def test_ttm_across_year_boundary(self):
        single = {"2026Q2": 1, "2026Q1": 2, "2025Q4": 3, "2025Q3": 4}
        self.assertEqual(fd.ttm_at(single, "2026Q2"), 10)

    def test_ttm_with_one_missing_quarter_is_none(self):
        # BKRGY örneği: 2025Q4 yok; ilk dört kayıt 2026Q3, Q2, Q1, 2025Q3
        single = {"2026Q3": 1, "2026Q2": 1, "2026Q1": 1, "2025Q3": 1, "2025Q2": 1}
        self.assertIsNone(fd.ttm_at(single, "2026Q3"))
        self.assertIsNone(fd.ttm(single, ["2026Q3", "2026Q2", "2026Q1", "2025Q3"]))

    def test_margin_rule(self):
        self.assertAlmostEqual(fd.margin(5, 100), 0.05)
        self.assertIsNone(fd.margin(1725, 10))   # |oran| > 10
        self.assertIsNone(fd.margin(5, 0))
        self.assertIsNone(fd.margin(5, -1))


class SuspectQuarterTests(unittest.TestCase):
    """Negatif tek çeyrek satış -> o çeyrek TTM, büyüme ve PEG'e girmemeli."""

    def run_process(self, cum_revenue: dict, cum_net: dict):
        cols = sorted(cum_revenue, key=fd.period_key, reverse=True)
        df = pd.DataFrame(
            [[cum_revenue[c] for c in cols], [cum_net[c] for c in cols],
             [cum_net[c] for c in cols], [cum_net[c] for c in cols]],
            index=["Satış Gelirleri", "FAALİYET KARI (ZARARI)", "DÖNEM KARI (ZARARI)", "Ana Ortaklık Payları"],
            columns=cols)
        bal = pd.DataFrame([[1000.0] * len(cols)], index=["Ana Ortaklığa Ait Özkaynaklar"], columns=cols)
        fd.CPI = {}                                  # nominal (raw) yöntem
        fd.fetch_statements = lambda t, s: (df, bal, "XI_29")
        fd.company_metrics = lambda p, s: {"market_cap": 10000.0, "pe_ratio": 9.9, "pb_ratio": 9.9,
                                           "ev_ebitda": None, "net_debt": None, "na": []}

        class T:
            def __init__(self, sym): pass
            def _get_isyatirim(self):
                class P:
                    def get_realtime_quote(self, s): return {"last": 1.0}
                return P()
        fd.bp.Ticker = T
        tmp = Path(__file__).resolve().parent / "_tmp_stocks"
        tmp.mkdir(exist_ok=True)
        fd.STOCKS = tmp
        return fd.process("TEST", "Test")

    def test_suspect_quarter_does_not_leak(self):
        ends = quarters_back("2026Q3", 12)
        rev, net = {}, {}
        for c in ends:
            y, q = fd.period_key(c)
            rev[c] = 100.0 * q
            net[c] = 10.0 * q
        # 2025Q4 kümülatifi 9A'dan küçük -> tek çeyrek satış negatif
        rev["2025Q4"] = 250.0
        s = self.run_process(rev, net)
        self.assertIn("2025Q4", s["suspect_periods"])
        # 2025Q4 son 4 çeyrekte değil (2026Q3..2025Q4? -> evet, içinde): TTM hesaplanmamalı
        self.assertIsNone(s["revenue_ttm"])
        self.assertIsNone(s["net_ttm"])
        self.assertIsNone(s["net_growth"])
        self.assertIsNone(s["peg"])
        # F/K bizim hesaplanamadığı için kaynaktan gelir ve bu açıkça işaretlenir
        self.assertEqual(s["pe_basis"], "src")

    def test_clean_series_gives_consistent_pe(self):
        ends = quarters_back("2026Q3", 12)
        rev = {c: 100.0 * fd.period_key(c)[1] for c in ends}
        net = {c: 10.0 * fd.period_key(c)[1] for c in ends}
        s = self.run_process(rev, net)
        self.assertEqual(s["suspect_periods"], [])
        self.assertAlmostEqual(s["net_ttm"], 40.0)
        self.assertAlmostEqual(s["pe"], 10000.0 / 40.0)
        self.assertEqual(s["pe_basis"], "calc")
        self.assertAlmostEqual(s["pb"], 10.0)


if __name__ == "__main__":
    unittest.main()
