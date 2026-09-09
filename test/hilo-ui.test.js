'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
// Exercise the real renderer with a minimal DOM, including rejected Web Animations.
function harness(rejectAnimation = false) {
  const elements = new Map(); const floating = new Set(); let calls = 0;
  const element = () => ({ innerHTML: '', textContent: '', disabled: false, dataset: {}, scrollWidth: 100,
    classList: { toggle() {}, add() {}, remove() {} },
    querySelector: () => element(), append: next => floating.add(next), remove() { floating.delete(this); },
    animate() { calls++; if (rejectAnimation) throw Error('animation unavailable'); return { finished: Promise.resolve(), cancel() {} }; },
  });
  const $ = id => { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); };
  const state = { connected:true, balance:12500, hl:{open:true,info:null,token:0} };
  const context = vm.createContext({ $, state, SUITS:{s:{symbol:'♠'}}, document:{createElement:element,querySelectorAll:()=>[]},
    matchMedia:()=>({matches:false}), haptic(){}, money:n=>'$'+(n/100).toFixed(2) });
  vm.runInContext(fs.readFileSync('public/hilo.js','utf8'), context);
  return { context, state, floating, $, calls:()=>calls };
}
const snap = (revision, phase = 'play') => ({ revision, phase, card:{rank:8,suit:'s'}, history:[],
  multiplier:2, payout:phase==='done'?200:0, bet:100, available:200, high:6/13, low:8/13, balance:12500,result:phase==='done'?'win':null });
test('24 same-card swaps leave no extra card layer and release the controls', async () => {
  const h = harness(); await h.context.onHiloState(snap(0));
  for(let i=1;i<=24;i++) {
    h.state.hl.pendingAction='pick'; await h.context.onHiloState(snap(i));
    assert.equal(h.floating.size,0); assert.equal(h.state.hl.animating,false); assert.equal(h.$('hl-main').disabled,false);
  }
  assert.equal(h.calls(),48);
});
test('unsupported animations still apply the next card and unlock input', async () => {
  const h=harness(true); await h.context.onHiloState(snap(0)); h.state.hl.pendingAction='skip';
  await h.context.onHiloState(snap(1)); assert.equal(h.floating.size,0); assert.equal(h.state.hl.info.revision,1); assert.equal(h.$('hl-main').disabled,false);
});
test('cashout shows Mines-style winnings, new round clears it, unchanged render does not restart it', async () => {
  const h=harness(); await h.context.onHiloState(snap(0)); await h.context.onHiloState(snap(1,'done'));
  assert.match(h.$('hl-overlay').innerHTML,/×2.00/); assert.match(h.$('hl-overlay').innerHTML,/2.00/);
  const markup=h.$('hl-overlay').innerHTML; h.context.renderHilo(); assert.equal(h.$('hl-overlay').innerHTML,markup);
  await h.context.onHiloState(snap(2)); assert.equal(h.$('hl-overlay').innerHTML,'');
});
