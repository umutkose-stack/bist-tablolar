const {test} = require('node:test');
const assert = require('node:assert/strict');
const {reason,date} = require('../assets/data-context.js');
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
 assert.equal(reason({ev_ebitda:null,source_na:['ev_ebitda'],operating_ttm:-5},'ev_ebitda'),'Negatif FAVÖK nedeniyle anlamlı değil');
 assert.equal(reason({nd_ebitda:null,source_na:['ev_ebitda'],operating_ttm:5},'nd_ebitda'),'Kaynakta anlamlı değil (A/D)');
 assert.equal(reason({pb:null,equity:-3},'pb'),'Negatif özkaynak nedeniyle anlamlı değil');
 assert.equal(reason({op_margin_ttm:null,revenue_ttm:1,operating_ttm:-50},'op_margin_ttm'),'Satış çok düşük; marj anlamlı değil');
 assert.equal(reason({op_margin_ttm:null},'op_margin_ttm'),'Veri yok');
 assert.equal(reason({peg:null,pe:8,net_ttm:10,net_ttm_prev:-2},'peg'),'Geçen yıl zarar; büyüme ve PEG hesaplanamaz');
});
