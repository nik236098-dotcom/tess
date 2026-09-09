'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {config,initial,start,publicState}=require('../server/arcade/game');
// Renderer/lifecycle tests only. This minimal DOM does not claim browser layout coverage.
function harness(game,reduced=false) {
  const elements=new Map(), frames=new Map(), sent=[];let next=0;
  const element=()=>({innerHTML:'',textContent:'',dataset:{},value:'1,00',disabled:false,offsetTop:0,clientHeight:318,scrollTop:0,
    classList:{add(){},remove(){},toggle(){}},setAttribute(){},querySelector(){return element();},querySelectorAll(){return [];},scrollTo(){},addEventListener(){}});
  const $=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
  const options={plinko:{risk:'medium'},tower:{level:'easy'},keno:{picks:[1,2,3]},dragon:{side:'dragon'}};
  const state={connected:true,balance:10000,ag:{game,info:null,pending:null,animating:false,token:0,raf:null,options}};
  const ctx=vm.createContext({state,$,document:{querySelectorAll:()=>[]},window:{matchMedia:()=>({matches:reduced})},performance:{now:()=>0},
    structuredClone,send:m=>sent.push(m),money:n=>'$'+((n||0)/100).toFixed(2),toCents:v=>Math.round(Number(v.replace(',','.'))*100),
    requestAnimationFrame:f=>{const id=++next;frames.set(id,f);return id;},cancelAnimationFrame:id=>frames.delete(id),
    haptic(){},toast(){},hlCard:card=>`<div>${card.rank}</div>`});
  vm.runInContext(fs.readFileSync('public/arcade.js','utf8'),ctx);
  const deliver=round=>ctx.onArcadeState({type:'ag',game,config:config(game),balance:10000,...publicState(game,round),requestId:state.ag.pending?.id});
  const advance=now=>{const pending=[...frames.values()];frames.clear();for(const f of pending)f(now);};
  return {ctx,state,$,frames,sent,deliver,advance};
}
for(const game of ['plinko','keno','dragon'])test(`${game}: result animation locks repeat stakes, ends, and releases controls`,()=>{
  const h=harness(game);h.deliver(initial());
  h.ctx.agRequest('start');h.ctx.agRequest('start');assert.equal(h.sent.length,1);
  const result=start(game,initial(),100,h.state.ag.options[game],0,()=>0);result.settled=true;
  h.deliver(result);assert.equal(h.state.ag.animating,true);assert.equal(h.$('ag-main').disabled,true);
  h.ctx.agRequest('start');assert.equal(h.sent.length,1);
  h.advance(3000);assert.equal(h.frames.size,0);assert.equal(h.state.ag.animating,false);assert.equal(h.$('ag-main').disabled,false);
  assert.equal(h.$('ag-payout').textContent,'$'+(result.payout/100).toFixed(2));
});
test('leaving during animation cancels its frame and cannot repaint another game',()=>{
  const h=harness('plinko');h.deliver(initial());h.ctx.agRequest('start');
  h.deliver(start('plinko',initial(),100,{risk:'medium'},0,()=>0));assert.equal(h.frames.size,1);
  h.ctx.stopArcade();assert.equal(h.frames.size,0);h.advance(3000);assert.equal(h.state.ag.game,null);
});
test('reduced motion completes immediately and disconnect disables stakes',()=>{
  const h=harness('keno',true);h.deliver(initial());h.ctx.agRequest('start');
  h.deliver(start('keno',initial(),100,{picks:[1,2,3]},0,()=>0));h.advance(0);assert.equal(h.state.ag.animating,false);
  h.state.connected=false;h.ctx.renderArcade();assert.equal(h.$('ag-main').disabled,true);
});
test('all five Tower settings render before and during a round; future tiles remain disabled',()=>{
  const h=harness('tower');h.deliver(initial());
  for(const level of ['easy','medium','hard','expert','master']) {
    h.state.ag.options.tower.level=level;h.ctx.renderArcade();
    const round=start('tower',initial(),100,{level},0,()=>0);h.state.ag.info=null;h.deliver(round);
    assert.match(h.$('ag-stage').innerHTML,/data-floor="8"/);
    assert.equal(h.$('ag-main').disabled,true);
    assert.match(h.$('ag-stage').innerHTML,/data-locked="true" disabled/);
  }
});
