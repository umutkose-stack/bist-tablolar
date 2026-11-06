/* Presentation-only metadata and availability. No inferred quote timestamps. */
(function(root) {
  function reason(s, k, value) {
    const v = value === undefined ? s[k] : value;
    const na = s.source_na || [];                        // kaynakta "A/D" yazan oranlar
    const fmtP = p => String(p).replace(/(\d{4})Q(\d)/, (_, y, q) => `${y}/${q * 3}`);
    const recentGap = (s.missing_periods || []).filter(p => (s.last_period ? p >= shiftBack(s.last_period, 3) : true));
    const recentSus = (s.suspect_periods || []).filter(p => (s.last_period ? p >= shiftBack(s.last_period, 3) : true));
    const susMsg = recentSus.length ? `Son 4 çeyrekte hesaplamaya alınmayan dönem var (${recentSus.map(fmtP).join(', ')}: çeyreklik satış negatif hesaplandı); 12 aylık değer hesaplanmadı` : null;
    const gapMsg = recentGap.length ? `Son 4 çeyrek kesintisiz değil (kaynakta eksik: ${recentGap.map(fmtP).join(', ')}); 12 aylık değer hesaplanmadı` : null;
    if (v != null && Number.isFinite(v) && !(['pe','pb','ev_ebitda','peg'].includes(k) && v < 0)) return null;
    const INS = ['combined_ratio_ttm','loss_ratio_ttm','expense_ratio_ttm','roe','gwp_growth','net_premium_margin_ttm','tech_margin_ttm'];
    if (INS.includes(k)) {
      if (s.kind !== 'sigorta') return 'Yalnızca sigorta şirketlerinde hesaplanır';
      if (s.ins_type === 'hayat' && ['combined_ratio_ttm','loss_ratio_ttm','expense_ratio_ttm'].includes(k)) return 'Hayat/emeklilik şirketinde uygulanmaz';
      return gapMsg || 'Veri yok';
    }
    if ((s.group === 'banka' || ['Banka','Sigorta'].includes(s.sector)) &&
        ['ev_ebitda','nd_ebitda','op','net','op_margin_ttm','net_margin_ttm','op_margin_q','net_margin_q'].includes(k))
      return 'Bu sektör için uygulanmaz';
    const equity = s.equity ?? s.quarters?.[0]?.equity;
    if (k === 'pe' && ((v != null && v < 0) || s.net_ttm < 0)) return 'Zarar nedeniyle anlamlı değil';
    if (['pe','pb','peg'].includes(k) && gapMsg && s.net_ttm == null) return gapMsg;
    if (['pe','peg','op','net','op_margin_ttm','net_margin_ttm'].includes(k) && susMsg && s.net_ttm == null) return susMsg;
    if (k === 'pe' && na.includes('pe')) return 'Kaynakta anlamlı değil (A/D)';
    if (k === 'pb' && ((v != null && v < 0) || equity < 0)) return 'Negatif özkaynak nedeniyle anlamlı değil';
    if (k === 'pb' && na.includes('pb')) return 'Kaynakta anlamlı değil (A/D)';
    if (['ev_ebitda','nd_ebitda'].includes(k) && na.includes('ev_ebitda'))
      return 'Kaynakta anlamlı değil (A/D)' + (s.operating_ttm < 0 ? '; şirket esas faaliyetten zararda' : '');
    if (['op','net','op_margin_ttm','net_margin_ttm'].includes(k)) {
      const r = s.revenue_ttm, o = k.startsWith('op') ? s.operating_ttm : s.net_ttm;
      if (r != null && r <= 0) return 'Satış sıfır veya negatif; marj hesaplanmaz';
      if (r != null && o != null && Math.abs(o / r) > 10) return 'Kâr/zarar satışın 10 katını aşıyor; marj anlamlı değil';
      if (r == null && gapMsg) return gapMsg;
    }
    if (['pe','pb','peg'].includes(k) && gapMsg && s.net_ttm == null) return gapMsg;
    if (['ev_ebitda','nd_ebitda'].includes(k) && s.ebitda_ttm != null && s.ebitda_ttm <= 0) return 'Sıfır veya negatif FAVÖK nedeniyle anlamlı değil';
    if (k === 'ev_ebitda' && v != null && v < 0) return 'Negatif çarpan; anlamlı kıyas yapılamaz';
    if (k === 'peg' && s.net_growth != null && s.net_growth <= 0) return 'Pozitif kâr büyümesi yok; PEG hesaplanmaz';
    if (k === 'peg' && s.net_ttm < 0) return 'Zarar nedeniyle anlamlı değil';
    if (k === 'peg' && s.net_ttm_prev != null && s.net_ttm_prev <= 0) return 'Geçen yıl zarar; büyüme ve PEG hesaplanamaz';
    return 'Veri yok';
  }
  function date(value) {
    if (!value) return 'Kaynakta belirtilmemiş';
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value.split('-').reverse().join('.');
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? 'Kaynakta belirtilmemiş' : d.toLocaleString('tr-TR', {timeZone:'Europe/Istanbul',dateStyle:'medium',timeStyle:'short'}) + ' (TSİ)';
  }
  function shiftBack(p, k) { const m = String(p).match(/(\d{4})Q(\d)/); if (!m) return p; let i = +m[1] * 4 + (+m[2] - 1) - k; return `${Math.floor(i / 4)}Q${i % 4 + 1}`; }
  /* Marj geçerlilik kuralı: veri üretimiyle (fetch_data.margin) aynı. Satış > 0 ve |oran| ≤ 10. */
  function validMargin(a, b) {
    if (a == null || b == null || !Number.isFinite(a) || !Number.isFinite(b) || b <= 0) return null;
    const m = a / b;
    return Math.abs(m) <= 10 ? m : null;
  }
  /* F/K, PD/DD'nin hangi temele dayandığını anlatan kısa not (tarih/tanım uydurmaz). */
  function ratioNote(s, k) {
    const basis = s[k + '_basis'], src = s[k + '_src'], mine = s[k];
    if (mine == null) return '';
    if (basis === 'src')
      return k === 'pe' ? 'Kaynak F/K (İş Yatırım); uygulamada son 12 ay net kârı hesaplanamadı'
                        : 'Kaynak PD/DD (İş Yatırım); uygulamada özkaynak bulunamadı';
    if (basis === 'calc' && src != null && src > 0 && Math.abs(src / mine - 1) > 0.05)
      return `Kaynak (İş Yatırım): ${String(src.toFixed(2)).replace('.', ',')}`;
    return '';
  }
  /* İlk ve son dönem arasındaki her çeyreği içeren eksen (eksik dönemler boş kalır). */
  function fillPeriods(items) {           // items: herhangi sırada {period,...}
    if (!items || !items.length) return [];
    const idx = p => { const m = String(p).match(/(\d{4})Q(\d)/); return +m[1] * 4 + (+m[2] - 1); };
    const by = Object.fromEntries(items.map(q => [q.period, q]));
    const ks = items.map(q => idx(q.period)); const lo = Math.min(...ks), hi = Math.max(...ks);
    const out = [];
    for (let i = hi; i >= lo; i--) { const p = `${Math.floor(i / 4)}Q${i % 4 + 1}`; out.push(by[p] || { period: p, missing: true }); }
    return out;                            // yeniden eskiye
  }
  const api = {reason, date, validMargin, ratioNote, fillPeriods};
  if (typeof module !== 'undefined') module.exports = api;
  else root.DataContext = api;
})(typeof window !== 'undefined' ? window : globalThis);
