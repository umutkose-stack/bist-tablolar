const {test} = require('node:test');
const assert = require('node:assert/strict');
const {reason,date,validMargin,ratioNote,fillPeriods} = require('../assets/data-context.js');
test('unknown data is not diagnosed as a loss',()=>{
 assert.equal(reason({pe:null},'pe'),'Veri yok');
 assert.equal(reason({pe:null,net_ttm:-10},'pe'),'Zarar nedeniyle anlamlı değil');
 assert.equal(reason({pe:3,net_ttm:-10},'pe'),null);
});
test('sector applicability and negative denominators are distinguished',()=>{
 assert.equal(reason({group:'banka',op_margin_ttm:null},'op_margin_ttm'),'Bu sektör için uygulanmaz');
 assert.equal(reason({sector:'Sigorta',nd_ebitda:null},'nd_ebitda'),'Bu sektör için uygulanmaz');
 assert.equal(reason({pb:-1},'pb'),'Negatif özkaynak nedeniyle anlamlı değil');
 assert.equal(reason({nd_ebitda:null,ebitda_ttm:-1},'nd_ebitda'),'Sıfır veya negatif FAVÖK nedeniyle anlamlı değil');
});
test('negative net cash, negative margins and zero values remain numeric',()=>{
 for(const [k,v] of [['nd_ebitda',-1],['op',-.1],['net',0],['pb',0]]) assert.equal(reason({[k]:v},k),null);
});
test('PEG explains missing growth; absent growth is not assumed',()=>{
 assert.equal(reason({peg:null,net_growth:0},'peg'),'Pozitif kâr büyümesi yok; PEG hesaplanmaz');
 assert.equal(reason({peg:null},'peg'),'Veri yok');
});
test('timestamps are explicit and unknown dates are never invented',()=>{
 assert.equal(date(null),'Kaynakta belirtilmemiş');
 assert.equal(date('bad'),'Kaynakta belirtilmemiş');
 assert.equal(date('2026-11-05'),'05.11.2026');
 assert.match(date('2026-11-05T22:22:00Z'),/01:22.*TSİ/);
});
test('source A/D markers, negative equity in summary, tiny revenue and prior-year loss',()=>{
 assert.equal(reason({ev_ebitda:null,source_na:['ev_ebitda'],operating_ttm:-5},'ev_ebitda'),'Kaynakta anlamlı değil (A/D); şirket esas faaliyetten zararda');
 assert.equal(reason({nd_ebitda:null,source_na:['ev_ebitda'],operating_ttm:5},'nd_ebitda'),'Kaynakta anlamlı değil (A/D)');
 assert.equal(reason({pb:null,equity:-3},'pb'),'Negatif özkaynak nedeniyle anlamlı değil');
 assert.equal(reason({op_margin_ttm:null,revenue_ttm:1,operating_ttm:-50},'op_margin_ttm'),'Kâr/zarar satışın 10 katını aşıyor; marj anlamlı değil');
 assert.equal(reason({op_margin_ttm:null,revenue_ttm:100,operating_ttm:5},'op_margin_ttm'),'Veri yok');
 assert.equal(reason({op_margin_ttm:null,revenue_ttm:-3},'op_margin_ttm'),'Satış sıfır veya negatif; marj hesaplanmaz');
 assert.equal(reason({op_margin_ttm:null},'op_margin_ttm'),'Veri yok');
 assert.equal(reason({peg:null,pe:8,net_ttm:10,net_ttm_prev:-2},'peg'),'Geçen yıl zarar; büyüme ve PEG hesaplanamaz');
});
test('gaps in the last four quarters are named, not hidden', ()=>{
 assert.equal(reason({net_ttm:null,pe:null,last_period:'2026Q3',missing_periods:['2025Q4']},'pe'),'Son 4 çeyrek kesintisiz değil (kaynakta eksik: 2025/12); 12 aylık değer hesaplanmadı');
 assert.equal(reason({kind:'sigorta',ins_type:'hayat_disi',roe:null,last_period:'2026Q3',missing_periods:['2026Q2','2025Q4']},'roe'),'Son 4 çeyrek kesintisiz değil (kaynakta eksik: 2026/6, 2025/12); 12 aylık değer hesaplanmadı');
});
test('margin validity rule is shared by cards and charts', ()=>{
 assert.equal(validMargin(5, 100), 0.05);
 assert.equal(validMargin(-50, 100), -0.5);
 assert.equal(validMargin(1725, 10), null);      // ZGYO benzeri: |oran| > 10
 assert.equal(validMargin(5, 0), null);
 assert.equal(validMargin(5, -3), null);
 assert.equal(validMargin(null, 3), null);
});
test('source-based ratios are labelled as such; no definitions invented', ()=>{
 assert.equal(ratioNote({pe:2, pe_basis:'src', net_ttm:null}, 'pe'), 'Kaynak F/K (İş Yatırım); uygulamada son 12 ay net kârı hesaplanamadı');
 assert.equal(ratioNote({pb:1.1, pb_basis:'src'}, 'pb'), 'Kaynak PD/DD (İş Yatırım); uygulamada özkaynak bulunamadı');
 assert.equal(ratioNote({pe:3.49, pe_basis:'calc', pe_src:2.8}, 'pe'), 'Kaynak (İş Yatırım): 2,80');
 assert.equal(ratioNote({pe:3.49, pe_basis:'calc', pe_src:3.5}, 'pe'), '');
 assert.equal(ratioNote({pe:null, pe_basis:null}, 'pe'), '');
});
test('chart axis keeps missing quarters (so lines break instead of bridging)', ()=>{
 const f = fillPeriods([{period:'2026Q1',v:1},{period:'2025Q3',v:2}]);
 assert.deepEqual(f.map(q=>q.period), ['2026Q1','2025Q4','2025Q3']);
 assert.equal(f[1].missing, true);
});
test('suspect quarters in the last four are named in the reason', ()=>{
 assert.match(reason({pe:null, net_ttm:null, last_period:'2026Q3', suspect_periods:['2025Q4']}, 'pe'), /2025\/12: çeyreklik satış negatif hesaplandı/);
});
