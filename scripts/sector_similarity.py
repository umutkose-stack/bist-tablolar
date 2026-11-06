"""
Sektör etiketleri arasındaki anlam yakınlığını vektör gömmeleriyle (embedding) ölçer.

Her sektör iki biçimde vektöre çevrilir:
  1) yalnızca etiket            -> "Gıda Perakende"
  2) etiket + içindeki şirketler -> "Sektör: Gıda Perakende. Şirketler: BİM, Migros, ..."
Sonra kosinüs benzerliği hesaplanır, en yakın çiftler ve eşik bazlı kümeler çıkarılır.
Bu bir ÖNERİ listesidir; birleştirme kararı elle verilir.

Çıktı: data/sector_similarity.json
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"   # Türkçe destekli
MAX_COMPANIES = 15


def clean_name(n: str) -> str:
    for suf in (" A.Ş.", " A.S.", " AŞ", " T.A.Ş.", " SANAYİ VE TİCARET", " SAN. VE TİC.", " SAN. TİC."):
        n = n.replace(suf, "")
    return n.strip().title()


def main():
    stocks = json.loads((ROOT / "data" / "summary.json").read_text(encoding="utf-8"))["stocks"]
    members = defaultdict(list)
    for s in stocks:
        if s.get("sector"):
            members[s["sector"]].append(s)
    labels = sorted(members, key=lambda x: (-len(members[x]), x))

    def ctx(lbl):
        names = [clean_name(s.get("name") or s["symbol"]) for s in
                 sorted(members[lbl], key=lambda s: -(s.get("market_cap") or 0))[:MAX_COMPANIES]]
        return f"Sektör: {lbl}. Şirketler: {', '.join(names)}"

    model = SentenceTransformer(MODEL)
    e_lbl = model.encode(labels, normalize_embeddings=True)
    e_ctx = model.encode([ctx(l) for l in labels], normalize_embeddings=True)
    sim_lbl = e_lbl @ e_lbl.T
    sim_ctx = e_ctx @ e_ctx.T
    sim = (sim_lbl + sim_ctx) / 2          # birleşik skor

    n = len(labels)
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append({"a": labels[i], "b": labels[j],
                          "na": len(members[labels[i]]), "nb": len(members[labels[j]]),
                          "label": round(float(sim_lbl[i, j]), 3),
                          "context": round(float(sim_ctx[i, j]), 3),
                          "score": round(float(sim[i, j]), 3)})
    pairs.sort(key=lambda p: -p["score"])

    # Ortalama bağlantılı (average linkage) basit hiyerarşik kümeleme
    def clusters(th):
        groups = [[i] for i in range(n)]
        while True:
            best, bi, bj = -1, -1, -1
            for a in range(len(groups)):
                for b in range(a + 1, len(groups)):
                    v = float(np.mean([sim[i, j] for i in groups[a] for j in groups[b]]))
                    if v > best:
                        best, bi, bj = v, a, b
            if best < th:
                break
            groups[bi] += groups[bj]
            del groups[bj]
        out = [sorted((labels[i] for i in g), key=lambda x: -len(members[x])) for g in groups if len(g) > 1]
        return sorted(out, key=lambda g: -sum(len(members[x]) for x in g))

    nearest = {}
    for i, l in enumerate(labels):
        order = np.argsort(-sim[i])
        nearest[l] = [{"sector": labels[j], "score": round(float(sim[i, j]), 3)} for j in order[1:4]]

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "model": MODEL,
        "sectors": [{"sector": l, "count": len(members[l]), "context": ctx(l)} for l in labels],
        "top_pairs": pairs[:80],
        "nearest": nearest,
        "clusters": {str(th): clusters(th) for th in (0.80, 0.70, 0.62)},
    }
    (ROOT / "data" / "sector_similarity.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{n} sektör, {len(pairs)} çift. En yakın 15:")
    for p in pairs[:15]:
        print(f"  {p['score']:.3f}  {p['a']} ({p['na']})  ~  {p['b']} ({p['nb']})   [ad {p['label']:.2f} · içerik {p['context']:.2f}]")


if __name__ == "__main__":
    main()
