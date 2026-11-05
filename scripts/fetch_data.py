"""
BIST mali tablo verilerini çekip arayüzün okuyacağı JSON dosyalarını üretir.

Çıktılar:
  data/summary.json          -> tarama tablosu (tüm hisseler, ana oranlar)
  data/stocks/<KOD>.json     -> hisse detayı (çeyreklik seriler + tam tablolar)

Kullanım:
  python scripts/fetch_data.py                 # watchlist.txt varsa onu, yoksa BIST 100'ü çeker
  python scripts/fetch_data.py THYAO ASELS     # sadece verilen hisseler

Veri kaynağı: borsapy (İş Yatırım mali tabloları). Sadece kişisel kullanım içindir.
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout, as_completed
from datetime import datetime, timezone
from pathlib import Path

import borsapy as bp

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STOCKS = DATA / "stocks"
WATCHLIST = ROOT / "watchlist.txt"

QUARTERS = 12          # kaç çeyrek geriye gidilsin
WORKERS = 6            # aynı anda işlenen hisse sayısı (çok artırma: kaynak engelleyebilir)
PRICE_TIMEOUT = 8      # fiyat sorgusu en fazla kaç sn beklesin

# İş Yatırım çeyreklik gelir tablosu değerleri yıl başından itibaren KÜMÜLATİF gelir.
# (3A, 6A, 9A, 12A). Tek çeyrek değerini fark alarak buluyoruz.
# Eğer bir gün kaynak tek çeyrek vermeye başlarsa bunu False yapın.
INCOME_IS_CUMULATIVE = True


# ---------------------------------------------------------------- yardımcılar

def norm(s: str) -> str:
    """Satır adlarını karşılaştırma için sadeleştir (Türkçe karakter + boşluk)."""
    s = str(s).strip()
    tr = str.maketrans("İIıŞşĞğÜüÖöÇç", "iiissgguuoocc")
    s = s.translate(tr).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def clean(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def find_row(df, patterns: list[str], exclude: list[str] | None = None):
    """Satır adını regex listesiyle sırayla ara; ilk eşleşen satırı döndür."""
    exclude = exclude or []
    names = {idx: norm(idx) for idx in df.index}
    for pat in patterns:
        rx = re.compile(pat)
        for idx, n in names.items():
            if rx.search(n) and not any(re.search(e, n) for e in exclude):
                row = df.loc[idx]
                if hasattr(row, "ndim") and row.ndim > 1:  # aynı adlı birden çok satır
                    row = row.iloc[0]
                return row
    return None


def period_key(col: str) -> tuple[int, int]:
    m = re.match(r"(\d{4})Q(\d)", col)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def to_single_quarters(series: dict[str, float | None]) -> dict[str, float | None]:
    """Kümülatif değerleri tek çeyreğe çevir."""
    if not INCOME_IS_CUMULATIVE:
        return series
    out = {}
    for col, val in series.items():
        y, q = period_key(col)
        if q == 1:
            out[col] = val
        else:
            prev = series.get(f"{y}Q{q-1}")
            out[col] = val - prev if (val is not None and prev is not None) else None
    return out


def ttm(single: dict[str, float | None], cols_desc: list[str]) -> float | None:
    vals = [single.get(c) for c in cols_desc[:4]]
    if len(vals) < 4 or any(v is None for v in vals):
        return None
    return sum(vals)


def ratio(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


def df_to_table(df) -> dict:
    cols = list(df.columns)
    rows = []
    for pos in range(len(df.index)):
        rows.append([str(df.index[pos]).strip()] + [clean(df.iat[pos, j]) for j in range(len(cols))])
    return {"columns": cols, "rows": rows}


# -------------------------------------------------------------- tek hisse

ROWS = {
    # anahtar: (desenler, hariç tutulacaklar)
    "revenue":   ([r"^satis gelirleri$", r"^hasilat$", r"^satis gelirleri"], []),
    "gross":     ([r"^brut kar", r"^ticari faaliyetlerden brut kar"], []),
    # Esas faaliyet karı: diğer faaliyet gelir/giderleri dahil, finansman öncesi
    "operating": ([r"^faaliyet kari", r"^esas faaliyet kari"], [r"^net faaliyet"]),
    "net_parent":([r"ana ortaklik paylari", r"ana ortakliga ait"], [r"ozkaynak", r"kontrol gucu olmayan"]),
    "net":       ([r"^donem net kar", r"^donem kari", r"^net donem kari"], []),
}

EQUITY_ROWS = {
    "equity_parent": ([r"ana ortakliga ait ozkaynaklar"], []),
    "equity":        ([r"^ozkaynaklar$", r"^toplam ozkaynaklar"], []),
}


def fetch_statements(t: bp.Ticker):
    """Önce sanayi (XI_29), olmazsa banka (UFRS) formatını dene."""
    last_err = None
    for group in ("XI_29", "UFRS"):
        try:
            inc = t.get_income_stmt(quarterly=True, financial_group=group, last_n=QUARTERS + 3)
            bal = t.get_balance_sheet(quarterly=True, financial_group=group, last_n=QUARTERS)
            if inc is not None and not inc.empty:
                return inc, bal, group
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"tablo alınamadı: {last_err}")


def process(symbol: str, name: str = "") -> dict | None:
    t = bp.Ticker(symbol)
    inc, bal, group = fetch_statements(t)

    cols_all = sorted([c for c in inc.columns if period_key(c) != (0, 0)], key=period_key, reverse=True)
    # Son çeyrek tamamen boş olabilir (henüz açıklanmamış) -> at
    while cols_all and inc[cols_all[0]].isna().all():
        cols_all.pop(0)
    if not cols_all:
        return None

    series = {}
    for key, (pats, excl) in ROWS.items():
        row = find_row(inc, pats, excl)
        cum = {c: clean(row[c]) if row is not None and c in row.index else None for c in cols_all}
        series[key] = to_single_quarters(cum)
    if all(v is None for v in series["net_parent"].values()):
        series["net_parent"] = series["net"]

    cols = cols_all[:QUARTERS]

    # Bilanço: özkaynak (dönem sonu, kümülatif değil)
    eq = {}
    if bal is not None and not bal.empty:
        for key, (pats, excl) in EQUITY_ROWS.items():
            row = find_row(bal, pats, excl)
            if row is not None:
                eq[key] = {c: clean(row[c]) if c in row.index else None for c in cols}
    equity = eq.get("equity_parent") or eq.get("equity") or {}

    quarters = []
    for c in cols:
        rev = series["revenue"].get(c)
        quarters.append({
            "period": c,
            "revenue": rev,
            "gross": series["gross"].get(c),
            "operating": series["operating"].get(c),
            "net": series["net_parent"].get(c),
            "equity": equity.get(c),
            "op_margin": ratio(series["operating"].get(c), rev),
            "net_margin": ratio(series["net_parent"].get(c), rev),
        })

    rev_ttm = ttm(series["revenue"], cols)
    op_ttm = ttm(series["operating"], cols)
    net_ttm = ttm(series["net_parent"], cols)
    last_equity = next((equity.get(c) for c in cols if equity.get(c) is not None), None)

    # Piyasa değeri ve İş Yatırım'ın hesapladığı oranlar
    metrics = {}
    try:
        metrics = t._get_isyatirim().get_company_metrics(symbol)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        pass
    mcap = clean(metrics.get("market_cap"))
    price = None
    try:  # fiyat yavaş bir kaynaktan geliyor; takılırsa beklemeden geç
        ex = ThreadPoolExecutor(1)
        price = clean(ex.submit(lambda: t.fast_info["last_price"]).result(timeout=PRICE_TIMEOUT))
        ex.shutdown(wait=False)
    except (FutTimeout, Exception):  # noqa: BLE001
        pass

    # Kendi hesabımız (kaynak oranı yoksa yedek)
    pe_calc = ratio(mcap, net_ttm) if net_ttm and net_ttm > 0 else None
    pb_calc = ratio(mcap, last_equity) if last_equity and last_equity > 0 else None

    summary = {
        "symbol": symbol,
        "name": name,
        "group": "banka" if group == "UFRS" else "sanayi",
        "last_period": cols[0],
        "price": price,
        "market_cap": mcap,
        "pe": clean(metrics.get("pe_ratio")) or pe_calc,
        "pb": clean(metrics.get("pb_ratio")) or pb_calc,
        "ev_ebitda": clean(metrics.get("ev_ebitda")),
        "revenue_ttm": rev_ttm,
        "operating_ttm": op_ttm,
        "net_ttm": net_ttm,
        "op_margin_ttm": ratio(op_ttm, rev_ttm),
        "net_margin_ttm": ratio(net_ttm, rev_ttm),
        "op_margin_q": quarters[0]["op_margin"],
        "net_margin_q": quarters[0]["net_margin"],
    }

    detail = {
        **summary,
        "quarters": quarters,
        "income_statement": df_to_table(inc[cols]),
        "balance_sheet": df_to_table(bal[[c for c in cols if c in bal.columns]]) if bal is not None and not bal.empty else None,
        "income_is_cumulative": INCOME_IS_CUMULATIVE,
    }
    (STOCKS / f"{symbol}.json").write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
    return summary


# ------------------------------------------------------------------ ana akış

def symbol_list(argv: list[str]) -> list[tuple[str, str]]:
    if argv:
        return [(s.upper(), "") for s in argv]
    if WATCHLIST.exists():
        syms = [l.split("#")[0].strip().upper() for l in WATCHLIST.read_text(encoding="utf-8").splitlines()]
        syms = [s for s in syms if s]
        if syms:
            return [(s, "") for s in syms]
    comps = bp.index("XU100").components
    return [(c["symbol"], c.get("name", "")) for c in comps]


def main():
    STOCKS.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    targets = symbol_list(sys.argv[1:])
    print(f"{len(targets)} hisse işlenecek ({time.time()-t0:.0f} sn)", flush=True)

    # Şirket adlarını tamamla
    try:
        comp = bp.companies()
        names = dict(zip(comp["ticker"], comp["name"]))
    except Exception:  # noqa: BLE001
        names = {}

    # Önceki özet: hata alan hissenin eski verisi kaybolmasın
    old = {}
    summary_path = DATA / "summary.json"
    if summary_path.exists():
        try:
            old = {s["symbol"]: s for s in json.loads(summary_path.read_text(encoding="utf-8"))["stocks"]}
        except Exception:  # noqa: BLE001
            pass

    results, failed = [], []
    n = len(targets)

    def work(item):
        sym, name = item
        t1 = time.time()
        r = process(sym, name or names.get(sym, ""))
        print(f"   {sym}: {time.time()-t1:.0f} sn", flush=True)
        return r

    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(work, it): it[0] for it in targets}
        for i, fut in enumerate(as_completed(futs), 1):
            sym = futs[fut]
            try:
                s = fut.result()
                if not s:
                    raise RuntimeError("boş veri")
                results.append(s)
                print(f"[{i}/{n}] {sym} ✓ {s['last_period']}", flush=True)
            except Exception as e:  # noqa: BLE001
                failed.append(sym)
                print(f"[{i}/{n}] {sym} ✗ {e}", flush=True)
                if sym in old:
                    results.append(old[sym])

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "demo": False,
        "failed": failed,
        "stocks": sorted(results, key=lambda s: s["symbol"]),
    }
    summary_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\nBitti: {len(results)} hisse, {len(failed)} hata, {time.time()-t0:.0f} sn")


if __name__ == "__main__":
    main()
