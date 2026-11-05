# BIST Tablolar

Kişisel kullanım için BIST şirketlerinin mali tablolarını gösteren ücretsiz arayüz.
Öne çıkanlar: **F/K, PD/DD, esas faaliyet kâr marjı, net kâr marjı** (son 12 ay ve son çeyrek).

## Nasıl çalışır
1. `scripts/fetch_data.py` borsapy ile İş Yatırım'daki mali tabloları çeker, `data/` klasörüne JSON yazar.
2. GitHub Actions bunu her gün otomatik çalıştırır ve değişiklikleri depoya kaydeder.
3. `index.html` GitHub Pages'te yayınlanır ve bu JSON'ları okur. Sunucu yok, ücret yok.

## Kurulum (bir kerelik)
1. GitHub'da yeni bir depo aç (ör. `bist-tablolar`) ve bu klasördeki her şeyi yükle.
2. **Settings → Pages**: Source = *Deploy from a branch*, Branch = `main` / `root`.
3. **Actions** sekmesi → *Verileri güncelle* → **Run workflow**. İlk çalıştırma BIST 100 için ~5-10 dk sürer.
4. Bitince `https://<kullanıcı-adın>.github.io/bist-tablolar/` adresini aç.

Sadece belli hisseleri istiyorsan `watchlist.txt` içine kodları satır satır yaz.

## Yerelde denemek
```bash
pip install -r requirements.txt
python scripts/fetch_data.py THYAO ASELS BIMAS
python -m http.server 8000   # sonra http://localhost:8000
```
(`index.html`'i doğrudan dosya olarak açarsan tarayıcı JSON okumaz; örnek veri görürsün.)

## Tanımlar
- **Esas faaliyet kârı**: gelir tablosundaki "FAALİYET KARI (ZARARI)" satırı (diğer faaliyet gelir/giderleri dahil, finansman öncesi).
- **Net kâr**: ana ortaklık payı.
- **Son 12 ay**: son 4 çeyreğin toplamı. Kaynak çeyrekleri kümülatif verdiği için tek çeyrekler fark alınarak bulunur.
- **F/K, PD/DD**: İş Yatırım şirket kartındaki değerler; yoksa piyasa değeri / 12 aylık net kâr ve piyasa değeri / ana ortaklık özkaynakları ile hesaplanır.
- Bankalar farklı tablo formatında (UFRS) gelir; "esas faaliyet kârı" orada aynı anlama gelmeyebilir.

## Uyarılar
- borsapy yalnızca kişisel ve eğitim amaçlı kullanım içindir; ticari kullanılamaz.
- Veri kaynağı sitesi değişirse çekme bozulabilir; o durumda `pip install -U borsapy` genelde çözer.
- Satır adları değişirse `fetch_data.py` içindeki `ROWS` desenlerini güncelle.
