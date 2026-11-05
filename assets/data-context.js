/* Presentation-only metadata and availability. No inferred quote timestamps. */
(function(root) {
  function reason(s, k, value) {
    const v = value === undefined ? s[k] : value;
    if (v != null && Number.isFinite(v) && !(['pe','pb','ev_ebitda','peg'].includes(k) && v < 0)) return null;
    if ((s.group === 'banka' || ['Banka','Sigorta'].includes(s.sector)) &&
        ['ev_ebitda','nd_ebitda','op','net','op_margin_ttm','net_margin_ttm','op_margin_q','net_margin_q'].includes(k))
      return 'Bu sektör için uygulanmaz';
    if (k === 'pe' && ((v != null && v < 0) || s.net_ttm < 0)) return 'Zarar nedeniyle anlamlı değil';
    if (k === 'pb' && ((v != null && v < 0) || s.quarters?.[0]?.equity < 0)) return 'Negatif özkaynak nedeniyle anlamlı değil';
    if (['ev_ebitda','nd_ebitda'].includes(k) && s.ebitda_ttm != null && s.ebitda_ttm <= 0) return 'Sıfır veya negatif FAVÖK nedeniyle anlamlı değil';
    if (k === 'ev_ebitda' && v != null && v < 0) return 'Negatif çarpan; anlamlı kıyas yapılamaz';
    if (k === 'peg' && s.net_growth != null && s.net_growth <= 0) return 'Pozitif kâr büyümesi yok; PEG hesaplanmaz';
    if (k === 'peg' && s.net_ttm < 0) return 'Zarar nedeniyle anlamlı değil';
    return 'Veri yok';
  }
  function date(value) {
    if (!value) return 'Kaynakta belirtilmemiş';
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value.split('-').reverse().join('.');
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? 'Kaynakta belirtilmemiş' : d.toLocaleString('tr-TR', {timeZone:'Europe/Istanbul',dateStyle:'medium',timeStyle:'short'}) + ' (TSİ)';
  }
  const api = {reason, date};
  if (typeof module !== 'undefined') module.exports = api;
  else root.DataContext = api;
})(typeof window !== 'undefined' ? window : globalThis);
