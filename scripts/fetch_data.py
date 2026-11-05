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
    out["sector"] = None
    if os.environ.get("DEBUG_HTML"):
        for mm in list(re.finditer(r"Sekt[öo]r|Faaliyet Alan", html))[:14]:
            j = mm.start()
            print(f"--- {symbol} @{j}: " + re.sub(r"\s+", " ", html[max(0, j-120):j+260]), flush=True)
    m = re.search(r"Sekt[öo]r[^<]{0,20}</t[hd]>\s*<td[^>]*>\s*(?:<a[^>]*>)?\s*([^<]+?)\s*<", html)
    if m:
        out["sector"] = m.group(1).strip()
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
        "sector": metrics.get("sector"),
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
    }
    (STOCKS / f"{symbol}.json").write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
    return summary


# ------------------------------------------------------------------ ana akış

def build_sector_map() -> dict[str, str]:
    """İş Yatırım hisse tarama ekranından sektör -> hisse eşlemesi (sektör başına bir istek)."""
    from borsapy._providers.isyatirim_screener import get_screener_provider
    prov = get_screener_provider()
    try:
        sectors = prov.get_sectors()
    except Exception as e:  # noqa: BLE001
        print(f"Sektör listesi alınamadı: {e}", flush=True)
        sectors = []
    if not sectors:  # sayfadaki açılır listenin kimliği değişmiş olabilir: içeriğinden bul
        try:
            prov._init_session()  # noqa: SLF001
            html = prov._get(prov.PAGE_URL).text  # noqa: SLF001
            for sel in re.findall(r"<select[^>]*>(.*?)</select>", html, flags=re.S):
                if "Sektör" not in sel:
                    continue
                opts = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]+)</option>', sel)
                cand = [{"id": v.strip(), "name": n.strip()} for v, n in opts if v.strip() and "Seçiniz" not in n]
                if len(cand) > len(sectors):
                    sectors = cand
            print(f"Sektör listesi sayfadan: {len(sectors)} ({', '.join(x['name'] for x in sectors[:6])}…)", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"Sektör sayfası okunamadı: {e}", flush=True)
    out: dict[str, str] = {}
    for sec in sectors:
        name = (sec.get("name") or "").strip()
        if not name:
            continue
        rows = []
        for key in (sec.get("id"), name):  # kaynak bazen id, bazen ad bekliyor
            if not key:
                continue
            try:
                rows = prov.screen(criterias=[("7", "0", "100000000", "False")], sector=str(key))
            except Exception:  # noqa: BLE001
                rows = []
            if rows:
                break
        for r in rows:
            out.setdefault(r["symbol"], name)
    print(f"Sektör: {len(sectors)} sektör, {len(out)} hisse eşlendi", flush=True)
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
                s["sector"] = sector_map.get(sym) or s.get("sector") or (old.get(sym) or {}).get("sector")
                if s["sector"]:  # detay dosyasına da yaz
                    fp = STOCKS / f"{sym}.json"
                    try:
                        d = json.loads(fp.read_text(encoding="utf-8")); d["sector"] = s["sector"]
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
