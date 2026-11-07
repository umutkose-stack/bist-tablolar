"""
Yeni çekilen veriyi bir önceki yayımlanmış veriyle kıyaslar ve yayımlamadan önce denetler.

İki seviye:
  ENGEL  -> veri toptan bozuk görünüyor: yeni veri YAYIMLANMAZ, data/ eski hâline döner.
  UYARI  -> genel tablo sağlam ama bazı hisselerde olağandışı değişim var: yayımlanır, raporlanır.

Sonuç data/data_check.json dosyasına yazılır (site bunu okuyup kullanıcıya gösterir).
Kullanım (iş akışında):  python scripts/check_data.py [--previous ESKİ_SUMMARY.json]
Önceki veri verilmezse git HEAD'deki data/summary.json kullanılır.
Çıkış kodu her zaman 0'dır; engel durumu GITHUB_OUTPUT'a blocked=true olarak yazılır.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# --- eşikler (ayarlanabilir)
MIN_COUNT_RATIO = 0.90        # hisse sayısı öncekinin %90'ının altına düşerse engel
MAX_PRICE_MISSING = 0.20      # fiyatı boş hisse oranı %20'yi aşarsa ...
MAX_MISSING_JUMP = 0.15       # ... ya da bir oran (F/K, satış) boşluğu 15 puandan fazla artarsa engel
MAX_PERIOD_BACK = 0.05        # son bilanço dönemi GERİYE giden hisse oranı %5'i aşarsa engel
MAX_NEW_FAILED = 20           # çekilemeyen hisse sayısı 20'den fazla artarsa engel
PRICE_JUMP = 0.40             # tek hissede fiyat/piyasa değeri %40'tan fazla değişirse uyarı
REVENUE_JUMP = 3.0            # bilanço dönemi aynıyken 12 aylık satış 3 kattan fazla değişirse uyarı


def frac(stocks, pred):
    return sum(1 for s in stocks if pred(s)) / len(stocks) if stocks else 0.0


def rel_change(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b - 1


def check(new: dict, old: dict | None) -> dict:
    blocks, warns = [], []
    N, O = new.get("stocks") or [], (old or {}).get("stocks") or []
    if not N:
        blocks.append("Yeni veride hiç hisse yok.")
        return {"blocks": blocks, "warnings": warns}
    if not O:
        return {"blocks": blocks, "warnings": warns, "note": "Kıyaslanacak önceki veri yok."}

    # --- genel (engelleyen) kontroller
    if len(N) < MIN_COUNT_RATIO * len(O):
        blocks.append(f"Hisse sayısı {len(O)} → {len(N)} düştü.")
    pm_new, pm_old = frac(N, lambda s: s.get("price") is None), frac(O, lambda s: s.get("price") is None)
    if pm_new > MAX_PRICE_MISSING and pm_new - pm_old > 0.10:
        blocks.append(f"Fiyatı boş hisse oranı %{pm_old*100:.0f} → %{pm_new*100:.0f}.")
    for key, label in (("pe", "F/K"), ("revenue_ttm", "12 aylık satış"), ("market_cap", "piyasa değeri")):
        a, b = frac(N, lambda s: s.get(key) is None), frac(O, lambda s: s.get(key) is None)
        if a - b > MAX_MISSING_JUMP:
            blocks.append(f"{label} boş olan hisse oranı %{b*100:.0f} → %{a*100:.0f}.")
    fn, fo = len(new.get("failed") or []), len(old.get("failed") or [])
    if fn - fo > MAX_NEW_FAILED:
        blocks.append(f"Çekilemeyen hisse sayısı {fo} → {fn}.")

    # --- hisse bazında (uyarı) kontroller
    old_by = {s["symbol"]: s for s in O}
    back = 0
    for s in N:
        p = old_by.get(s["symbol"])
        if not p:
            continue
        sym = s["symbol"]
        if s.get("last_period") and p.get("last_period") and s["last_period"] < p["last_period"]:
            back += 1
            warns.append({"symbol": sym, "kind": "period_back",
                          "text": f"Son bilanço dönemi geriye gitti ({p['last_period']} → {s['last_period']})"})
        for key, label in (("price", "Fiyat"), ("market_cap", "Piyasa değeri")):
            ch = rel_change(s.get(key), p.get(key))
            if ch is not None and abs(ch) > PRICE_JUMP:
                warns.append({"symbol": sym, "kind": key + "_jump",
                              "text": f"{label} bir günde %{ch*100:+.0f} değişti ({p[key]:,.2f} → {s[key]:,.2f})".replace(",", "X").replace(".", ",").replace("X", ".")})
                break
        if s.get("last_period") == p.get("last_period"):
            a, b = s.get("revenue_ttm"), p.get("revenue_ttm")
            if a and b and a > 0 and b > 0 and (a / b > REVENUE_JUMP or b / a > REVENUE_JUMP):
                warns.append({"symbol": sym, "kind": "revenue_jump",
                              "text": f"Bilanço dönemi aynıyken 12 aylık satış {b/1e9:.2f} → {a/1e9:.2f} mlr TL oldu"})
        if p.get("price") is not None and s.get("price") is None:
            warns.append({"symbol": sym, "kind": "price_lost", "text": "Fiyat dün vardı, bugün gelmedi"})
    if back / len(N) > MAX_PERIOD_BACK:
        blocks.append(f"{back} hissede son bilanço dönemi geriye gitti.")
    return {"blocks": blocks, "warnings": warns}


def load_previous(path: str | None) -> dict | None:
    if path:
        p = Path(path)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    try:
        raw = subprocess.check_output(["git", "-C", str(ROOT), "show", "HEAD:data/summary.json"], stderr=subprocess.DEVNULL)
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return None


def restore_previous():
    """Engel: data/ klasörünü son yayımlanmış hâline döndür (yalnızca git içinde)."""
    subprocess.run(["git", "-C", str(ROOT), "checkout", "HEAD", "--", "data"], check=False)
    subprocess.run(["git", "-C", str(ROOT), "clean", "-fdq", "--", "data"], check=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--previous")
    ap.add_argument("--no-restore", action="store_true")
    a = ap.parse_args()
    new = json.loads((DATA / "summary.json").read_text(encoding="utf-8"))
    old = load_previous(a.previous)
    res = check(new, old)
    blocked = bool(res["blocks"])
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "status": "blocked" if blocked else ("warn" if res["warnings"] else "ok"),
        "blocks": res["blocks"],
        "warnings": res["warnings"][:200],
        "warning_count": len(res["warnings"]),
        "new_count": len(new.get("stocks") or []),
        "previous_count": len((old or {}).get("stocks") or []),
        "previous_updated_at": (old or {}).get("updated_at"),
        "rejected_updated_at": new.get("updated_at") if blocked else None,
    }
    if blocked:
        if not a.no_restore:
            restore_previous()
        print("ENGEL: yeni veri yayımlanmadı, önceki veri korunuyor.")
        for b in res["blocks"]:
            print("  ENGEL -", b)
    else:
        print(f"KONTROL: tamam ({report['new_count']} hisse, {report['warning_count']} uyarı)")
    for w in res["warnings"][:40]:
        print(f"  UYARI - {w['symbol']}: {w['text']}")
    if len(res["warnings"]) > 40:
        print(f"  UYARI - ... ve {len(res['warnings']) - 40} uyarı daha")
    (DATA / "data_check.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"blocked={'true' if blocked else 'false'}\n")
            f.write(f"warnings={len(res['warnings'])}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
