"""Veri kontrolü (scripts/check_data.py) için testler."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_data as cd  # noqa: E402


def stock(sym, **kw):
    base = {"symbol": sym, "price": 10.0, "market_cap": 1e9, "pe": 8.0, "revenue_ttm": 5e8, "last_period": "2026Q3"}
    base.update(kw)
    return base


def pkg(stocks, failed=0):
    return {"stocks": stocks, "failed": [f"F{i}" for i in range(failed)]}


OLD = pkg([stock(f"S{i}") for i in range(100)], failed=14)


class CheckDataTests(unittest.TestCase):
    def test_same_data_passes(self):
        r = cd.check(OLD, OLD)
        self.assertEqual(r["blocks"], [])
        self.assertEqual(r["warnings"], [])

    def test_count_drop_blocks(self):
        r = cd.check(pkg([stock(f"S{i}") for i in range(60)], 14), OLD)
        self.assertTrue(any("Hisse sayısı" in b for b in r["blocks"]))

    def test_mass_missing_prices_blocks(self):
        new = pkg([stock(f"S{i}", price=None if i < 50 else 10.0) for i in range(100)], 14)
        self.assertTrue(any("Fiyatı boş" in b for b in cd.check(new, OLD)["blocks"]))

    def test_mass_missing_pe_blocks(self):
        new = pkg([stock(f"S{i}", pe=None if i < 30 else 8.0) for i in range(100)], 14)
        self.assertTrue(any("F/K" in b for b in cd.check(new, OLD)["blocks"]))

    def test_many_new_failures_block(self):
        self.assertTrue(cd.check(pkg(OLD["stocks"], 40), OLD)["blocks"])

    def test_single_price_jump_only_warns(self):
        new = pkg([stock(f"S{i}", price=20.0 if i == 3 else 10.0) for i in range(100)], 14)
        r = cd.check(new, OLD)
        self.assertEqual(r["blocks"], [])
        self.assertEqual([w["symbol"] for w in r["warnings"]], ["S3"])

    def test_revenue_jump_same_period_warns(self):
        new = pkg([stock(f"S{i}", revenue_ttm=5e9 if i == 7 else 5e8) for i in range(100)], 14)
        r = cd.check(new, OLD)
        self.assertEqual([w["kind"] for w in r["warnings"]], ["revenue_jump"])

    def test_new_period_revenue_change_is_fine(self):
        new = pkg([stock(f"S{i}", revenue_ttm=5e9, last_period="2026Q4") if i == 7 else stock(f"S{i}") for i in range(100)], 14)
        self.assertEqual(cd.check(new, OLD)["warnings"], [])

    def test_period_going_back_many_blocks(self):
        new = pkg([stock(f"S{i}", last_period="2026Q2" if i < 10 else "2026Q3") for i in range(100)], 14)
        self.assertTrue(any("geriye" in b for b in cd.check(new, OLD)["blocks"]))

    def test_no_previous_is_not_blocking(self):
        self.assertEqual(cd.check(OLD, None)["blocks"], [])


if __name__ == "__main__":
    unittest.main()
