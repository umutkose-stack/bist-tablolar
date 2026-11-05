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
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout, as_completed
from datetime import datetime, timezone
from pathlib import Path

import borsapy as bp
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STOCKS = DATA / "stocks"
WATCHLIST = ROOT / "watchlist.txt"

QUARTERS = 12          # kaç çeyrek geriye gidilsin
WORKERS = 8            # aynı anda işlenen hisse sayısı (çok artırma: kaynak engelleyebilir)
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


# ------------------------------------------------- enflasyon (TMS 29) düzeltmesi
#
# Kaynak (İş Yatırım) geçmiş dönemleri, bir sonraki yılın aynı dönem raporundaki
# YENİDEN DÜZENLENMİŞ karşılaştırmalı rakamlarla günceller. Örn. BİM 6A2025 satışları
# raporda 309,8 mlr TL (Haziran 2025 parası) iken kaynakta 409,3 mlr (Haziran 2026 parası).
# Bu yüzden ardışık kümülatif dönemler farklı tarihlerin parasıyla durur ve doğrudan
# çıkarılamaz. Çözüm: her kümülatif rakamın "hangi tarihin parası" olduğunu bul, TÜFE ile
# en son dönemin parasına çevir, sonra çıkar.

CPI: dict[str, float] = {}   # "YYYY-MM" -> zincirlenmiş TÜFE endeksi

# Fonksiyonel para birimi TL olmayan (USD/EUR) bilinen şirketler
FX_FUNCTIONAL = {"THYAO", "PGSUS", "EREGL", "ISDMR", "TAVHL"}


def load_cpi() -> dict[str, float]:
    try:
        df = bp.Inflation().tufe(start="2019-01-01")
    except Exception as e:  # noqa: BLE001
        print(f"TÜFE alınamadı: {e}", flush=True)
        return {}
    rows = []
    for idx, r in df.iterrows():
        ym = str(r.get("YearMonth") or "")
        m = re.match(r"(\d{4})[-/.]?(\d{1,2})", ym) or re.match(r"(\d{4})-(\d{2})", str(idx)[:7])
        mi = clean(r.get("MonthlyInflation"))
        if m and mi is not None:
            rows.append((f"{int(m.group(1)):04d}-{int(m.group(2)):02d}", mi))
    rows.sort()
    out, lvl = {}, 100.0
    for ym, mi in rows:
        lvl *= 1 + mi / 100
        out[ym] = lvl
    print(f"TÜFE: {len(out)} ay ({rows[0][0] if rows else '-'} → {rows[-1][0] if rows else '-'})", flush=True)
    return out


def cpi_at(col: str) -> float | None:
    """Çeyrek sonu ayının endeksi; henüz açıklanmadıysa en son bilinen ay."""
    if not CPI:
        return None
    y, q = period_key(col)
    key = f"{y:04d}-{q * 3:02d}"
    if key in CPI:
        return CPI[key]
    older = [k for k in CPI if k <= key]
    return CPI[max(older)] if older else None


def money_date(col: str, available: set[str], latest: str | None = None, mode: str = "tms29") -> str:
    """Kaynakta bu kümülatif rakam hangi tarihin parasıyla duruyor?
    - Ertesi yılın aynı dönemi yayımlandıysa: o raporun yeniden düzenlenmiş karşılaştırmalısı.
    - Yayımlanmadıysa ara dönemler kendi tarihinin parasıyla; son YILLIK rakam ise
      şirketin en son raporunun parasıyla (kaynak bunu da güncelliyor; ör. THY 12A2025
      raporda ~1 trilyon TL, kaynakta 1.188 mlr)."""
    y, q = period_key(col)
    nxt = f"{y + 1}Q{q}"
    if mode == "usd" and q != 4:
        # Fonksiyonel para birimi USD olanlar (THY, Erdemir…) ara dönemleri yeniden
        # düzenlemiyor; kaynak yalnızca yıllık rakamları güncelliyor.
        return col
    if nxt in available:
        return nxt
    if q == 4 and latest:
        return latest
    return col


def to_base(cum: dict[str, float | None], available: set[str], base: str, mode: str = "tms29") -> dict[str, float | None]:
    """Kümülatif rakamları 'base' döneminin parasına çevir."""
    ib = cpi_at(base)
    out = {}
    for c, v in cum.items():
        im = cpi_at(money_date(c, available, base, mode))
        out[c] = v * ib / im if (v is not None and ib and im) else None
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


# ------------------------------------------------------- şirket kartı oranları

def _tr_num(txt: str):
    """'-1.234,5' -> -1234.5 (işareti korur; borsapy net borçta eksiyi siliyor)."""
    txt = txt.strip().replace("\xa0", "")
    neg = txt.startswith("-") or txt.startswith("(")
    num = re.sub(r"[^\d,]", "", txt).replace(",", ".")
    if not num:
        return None
    try:
        v = float(num)
    except ValueError:
        return None
    return -v if neg else v


def company_metrics(prov, symbol: str) -> dict:
    """İş Yatırım şirket kartındaki 'Cari Değerler' tablosu."""
    url = f"https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/sirket-karti.aspx?hisse={symbol}"
    out = {"market_cap": None, "pe_ratio": None, "pb_ratio": None, "ev_ebitda": None, "net_debt": None}
    html = None
    for attempt in range(3):
        try:
            r = prov._client.get(url, timeout=15)  # noqa: SLF001
            r.raise_for_status()
            html = r.text
            break
        except Exception:  # noqa: BLE001
            time.sleep(1 + attempt)
    if not html:
        return out
    i = html.find("Cari Değerler")
    if i < 0:
        return out
    for label, value in re.findall(r"<th[^>]*>([^<]+)</th>\s*<td[^>]*>([^<]+)</td>", html[i:i + 3000]):
        label = label.strip()
        v = _tr_num(value)
        if v is None:
            continue
        if "F/K" in label and "FD" not in label:
            out["pe_ratio"] = v
        elif "PD/DD" in label:
            out["pb_ratio"] = v
        elif "FD/FAVÖK" in label:
            out["ev_ebitda"] = v
        elif "Piyasa Değeri" in label:
            out["market_cap"] = v * 1_000_000   # mnTL
        elif "Net Borç" in label:
            out["net_debt"] = v * 1_000_000     # mnTL
    return out


# -------------------------------------------------------------- tek hisse

ROWS = {
    # anahtar: (desenler, hariç tutulacaklar)
    "revenue":   ([r"^satis gelirleri$", r"^hasilat$", r"^satis gelirleri"], []),
    "gross":     ([r"^brut kar zarar$", r"^brut kar"], []),
    # Esas faaliyet karı: diğer faaliyet gelir/giderleri dahil, finansman öncesi
    "operating": ([r"^faaliyet kari zarari$", r"^esas faaliyet kari"], [r"oncesi"]),
    "net_parent":([r"^ana ortaklik paylari$", r"ana ortakliga ait"], [r"ozkaynak", r"kontrol gucu olmayan"]),
    "net":       ([r"^donem kari zarari$", r"^donem net kar", r"^net donem kari"], []),
}

EQUITY_ROWS = {
    "equity_parent": ([r"ana ortakliga ait ozkaynaklar"], []),
    "equity":        ([r"^ozkaynaklar$", r"^toplam ozkaynaklar"], []),
}


def recent_quarters(n: int) -> list[tuple[int, int]]:
    """Bugünden geriye, bitmiş son çeyrekten başlayarak (yıl, ay) listesi.
    Henüz açıklanmamış çeyrek boş gelir ve sonra atılır; böylece yeni bilanço
    açıklandığı gün yakalanır."""
    now = datetime.now()
    y, m = now.year, (now.month - 1) // 3 * 3  # bitmiş son çeyreğin son ayı
    if m == 0:
        y, m = y - 1, 12
    out = []
    for _ in range(n):
        out.append((y, m))
        m -= 3
        if m == 0:
            y, m = y - 1, 12
    return out


def _merge(parts):
    parts = [p for p in parts if p is not None and not p.empty]
    if not parts:
        return None
    base = parts[0]
    for p in parts[1:]:
        if len(p) == len(base) and list(p.index) == list(base.index):
            base = pd.concat([base, p[[c for c in p.columns if c not in base.columns]]], axis=1)
        else:  # şablon farklıysa ada göre birleştir (yinelenen adlarda ilki)
            p = p[~p.index.duplicated()]
            b = base[~base.index.duplicated()]
            base = b.join(p[[c for c in p.columns if c not in b.columns]], how="outer")
    return base


def fetch_statements(t: bp.Ticker, symbol: str):
    """Önce sanayi (XI_29), olmazsa banka (UFRS) formatını dene.
    Her istek tüm tabloları birlikte döndürür; gelir tablosu ve bilançoyu tek istekten ayırırız."""
    prov = t._get_isyatirim()  # noqa: SLF001
    url = f"{prov.BASE_URL}/Data.aspx/MaliTablo"
    periods = recent_quarters(QUARTERS + 4)
    batches = [periods[i:i + 4] for i in range(0, len(periods), 4)]
    last_err = None
    for group in ("XI_29", "UFRS"):
        inc_parts, bal_parts = [], []
        for batch in batches:
            params = {"companyCode": symbol, "exchange": "TRY", "financialGroup": group}
            for i, (yy, pp) in enumerate(batch, 1):
                params[f"year{i}"], params[f"period{i}"] = yy, pp
            try:
                data = prov._get(url, params=params).json()  # noqa: SLF001
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
            inc_parts.append(prov._parse_financial_response(data, batch, quarterly=True, statement_type="income_stmt"))  # noqa: SLF001
            bal_parts.append(prov._parse_financial_response(data, batch, quarterly=True, statement_type="balance_sheet"))  # noqa: SLF001
        inc = _merge(inc_parts)
        if inc is not None and inc.notna().any().any():
            return inc, _merge(bal_parts), group
    raise RuntimeError(f"tablo alınamadı: {last_err or 'boş yanıt'}")


def process(symbol: str, name: str = "") -> dict | None:
    t = bp.Ticker(symbol)
    inc, bal, group = fetch_statements(t, symbol)

    cols_all = sorted([c for c in inc.columns if period_key(c) != (0, 0)], key=period_key, reverse=True)
    # Son çeyrek tamamen boş olabilir (henüz açıklanmamış) -> at
    while cols_all and inc[cols_all[0]].isna().all():
        cols_all.pop(0)
    if not cols_all:
        return None

    cums = {}
    for key, (pats, excl) in ROWS.items():
        row = find_row(inc, pats, excl)
        cums[key] = {c: clean(row[c]) if row is not None and c in row.index else None for c in cols_all}
    if all(v is None for v in cums["net_parent"].values()):
        cums["net_parent"] = cums["net"]

    # Ham (nominal) tek çeyrekler ve TÜFE ile aynı paraya çevrilmiş tek çeyrekler
    available = {c for c in cols_all if cums["revenue"].get(c) is not None}
    base = cols_all[0]
    variants = {"raw": {k: to_single_quarters(v) for k, v in cums.items()}}
    if CPI:
        for mode in ("tms29", "usd"):
            variants[mode] = {k: to_single_quarters(to_base(v, available, base, mode)) for k, v in cums.items()}
    # Bankalar TMS 29 uygulamıyor (BDDK); fonksiyonel para birimi USD/EUR olanlar ara
    # dönemleri yeniden düzenlemiyor; geri kalan herkes TMS 29.
    if not CPI or group == "UFRS":
        method = "raw"
    elif symbol in FX_FUNCTIONAL:
        method = "usd"
    else:
        method = "tms29"
    series = variants[method]
    use_adj = method != "raw"

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
    metrics = company_metrics(t._get_isyatirim(), symbol)  # noqa: SLF001
    mcap = clean(metrics.get("market_cap"))
    price = None
    try:  # önce İş Yatırım'ın hızlı fiyat servisi
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            price = clean(t._get_isyatirim().get_realtime_quote(symbol).get("last")) or None  # noqa: SLF001
    except Exception:  # noqa: BLE001
        pass
    if price is None:
        try:  # yedek: TradingView (yavaş olabilir; takılırsa beklemeden geç)
            ex = ThreadPoolExecutor(1)
            price = clean(ex.submit(lambda: t.fast_info["last_price"]).result(timeout=PRICE_TIMEOUT))
            ex.shutdown(wait=False)
        except (FutTimeout, Exception):  # noqa: BLE001
            pass

    # Kendi hesabımız (kaynak oranı yoksa yedek)
    pe_calc = ratio(mcap, net_ttm) if net_ttm and net_ttm > 0 else None
    pb_calc = ratio(mcap, last_equity) if last_equity and last_equity > 0 else None
    pe = clean(metrics.get("pe_ratio")) or pe_calc
    pb = clean(metrics.get("pb_ratio")) or pb_calc

    # FAVÖK (12 ay): İş Yatırım'ın FD/FAVÖK'ünden geri hesaplanır -> FD = piyasa değ. + net borç
    ev_ebitda = clean(metrics.get("ev_ebitda"))
    net_debt = clean(metrics.get("net_debt"))
    ev = mcap + net_debt if (mcap is not None and net_debt is not None) else None
    ebitda = ev / ev_ebitda if (ev is not None and ev_ebitda) else None
    nd_ebitda = net_debt / ebitda if (net_debt is not None and ebitda and ebitda > 0) else None

    # PEG = F/K ÷ (yıllık net kâr büyümesi, %). Büyüme: son 12 ay vs bir önceki yılın 12 ayı.
    net_ttm_prev = ttm(series["net_parent"], cols_all[4:])
    growth = None
    if net_ttm is not None and net_ttm_prev and net_ttm_prev > 0:
        growth = net_ttm / net_ttm_prev - 1
    peg = pe / (growth * 100) if (pe and pe > 0 and growth and growth > 0) else None

    summary = {
        "symbol": symbol,
        "name": name,
        "group": "banka" if group == "UFRS" else "sanayi",
        "last_period": cols[0],
        "price": price,
        "market_cap": mcap,
        "pe": pe,
        "pb": pb,
        "ev_ebitda": ev_ebitda,
        "net_debt": net_debt,
        "ebitda_ttm": ebitda,
        "nd_ebitda": nd_ebitda,
        "net_growth": growth,
        "peg": peg,
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
        "inflation_adjusted": use_adj,
        "adjust_method": method,
        "money_base": base if use_adj else None,
    }
    (STOCKS / f"{symbol}.json").write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
    return summary


# ------------------------------------------------------------------ ana akış

def build_sector_map() -> dict[str, dict]:
    """TradingView tarayıcısından tüm BIST hisselerinin sektör/alt sektörü (tek istek)."""
    from tradingview_screener import Query
    from sectors_tr import INDUSTRY_TR, OVERRIDES, tr_label
    _, df = (Query().set_markets("turkey").select("name", "sector", "industry")
             .limit(3000).get_scanner_data())
    out: dict[str, dict] = {}
    unmapped = set()
    for _, r in df.iterrows():
        sym = str(r.get("name") or str(r["ticker"]).split(":")[-1]).upper()
        sec = r.get("sector") if isinstance(r.get("sector"), str) else None
        ind = r.get("industry") if isinstance(r.get("industry"), str) else None
        label, main = OVERRIDES.get(sym) or tr_label(sec, ind)
        if label:
            out[sym] = {"sector": label, "sector_main": main}
            if ind and ind not in INDUSTRY_TR:
                unmapped.add(ind)
    print(f"Sektör: {len(out)} hisse eşlendi; çevrilmemiş alt sektörler: {sorted(unmapped)[:30]}", flush=True)
    return out


INDEXES = ["XUTUM", "XU100"]   # sırayla dene: BIST Tüm, olmazsa BIST 100


def symbol_list(argv: list[str]) -> list[tuple[str, str]]:
    """Komut satırı verilirse sadece onlar; yoksa BIST Tüm + watchlist.txt'deki ekler."""
    if argv:
        return [(s.upper(), "") for s in argv]
    out: dict[str, str] = {}
    for idx in INDEXES:
        try:
            comps = bp.index(idx).components
            if comps:
                out = {c["symbol"]: c.get("name", "") for c in comps}
                print(f"Endeks: {idx} ({len(out)} hisse)", flush=True)
                break
        except Exception as e:  # noqa: BLE001
            print(f"Endeks {idx} alınamadı: {e}", flush=True)
    if WATCHLIST.exists():
        extra = [l.split("#")[0].strip().upper() for l in WATCHLIST.read_text(encoding="utf-8").splitlines()]
        for sym in filter(None, extra):
            out.setdefault(sym, "")
    return list(out.items())


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

    global CPI
    CPI = load_cpi()
    if CPI:  # denetim ve şeffaflık için
        (DATA / "cpi.json").write_text(json.dumps(CPI), encoding="utf-8")

    try:
        sector_map = build_sector_map()
    except Exception as e:  # noqa: BLE001
        print(f"Sektör eşlemesi başarısız: {e}", flush=True)
        sector_map = {}

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
                sec = sector_map.get(sym) or {}
                prev = old.get(sym) or {}
                s["sector"] = sec.get("sector") or prev.get("sector")
                s["sector_main"] = sec.get("sector_main") or prev.get("sector_main")
                if s["sector"]:  # detay dosyasına da yaz
                    fp = STOCKS / f"{sym}.json"
                    try:
                        d = json.loads(fp.read_text(encoding="utf-8"))
                        d["sector"], d["sector_main"] = s["sector"], s["sector_main"]
                        fp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                    except Exception:  # noqa: BLE001
                        pass
                results.append(s)
                print(f"[{i}/{n}] {sym} ✓ {s['last_period']}", flush=True)
            except Exception as e:  # noqa: BLE001
                failed.append(sym)
                print(f"[{i}/{n}] {sym} ✗ {e}", flush=True)
                if sym in old:
                    results.append(old[sym])

    # Belirli hisseler çalıştırıldıysa diğerlerinin eski verisini koru
    merged = results
    if sys.argv[1:]:
        done = {r["symbol"] for r in results}
        merged = results + [v for k, v in old.items() if k not in done]
        failed = [f for f in failed if f not in old]

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "demo": False,
        "failed": failed,
        "stocks": sorted(merged, key=lambda s: s["symbol"]),
    }
    summary_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\nBitti: {len(results)} hisse, {len(failed)} hata, {time.time()-t0:.0f} sn")


if __name__ == "__main__":
    main()
