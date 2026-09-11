'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {config,initial,start,publicState}=require('../server/arcade/game');
// Renderer/lifecycle tests only. This minimal DOM does not claim browser layout coverage.
function harness(game,reduced=false) {
  const elements=new Map(), frames=new Map(), sent=[];let next=0;
  const element=()=>({html:'',writes:0,get innerHTML(){return this.html;},set innerHTML(value){this.html=value;this.writes++;},textContent:'',dataset:{},value:'1,00',disabled:false,offsetTop:0,clientHeight:318,scrollTop:0,listeners:{},attributes:{},
    classList:{add(){},remove(){},toggle(){}},setAttribute(key,value){this.attributes[key]=value;},querySelector(){return element();},querySelectorAll(){return [];},scrollTo(){},addEventListener(type,handler){this.listeners[type]=handler;}});
  const $=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
  const options={plinko:{risk:'medium'},tower:{level:'easy'},keno:{picks:[1,2,3]},dragon:{side:'dragon'}};
  const state={connected:true,balance:10000,ag:{game,info:null,pending:null,animating:false,token:0,raf:null,options}};
  const maxButton=element();maxButton.dataset.agAmount='max';
  const ctx=vm.createContext({state,$,document:{querySelectorAll:selector=>selector==='[data-ag-amount]'?[maxButton]:[]},window:{matchMedia:()=>({matches:reduced})},performance:{now:()=>0},
    structuredClone,send:m=>sent.push(m),money:n=>'$'+((n||0)/100).toFixed(2),toCents:v=>Math.round(Number(v.replace(',','.'))*100),
    requestAnimationFrame:f=>{const id=++next;frames.set(id,f);return id;},cancelAnimationFrame:id=>frames.delete(id),
    haptic(){},toast(){},hlCard:card=>`<div>${card.rank}</div>`});
  vm.runInContext(fs.readFileSync('public/game-result.js','utf8'),ctx);
  vm.runInContext(fs.readFileSync('public/plinko-motion.js','utf8'),ctx);
  vm.runInContext(fs.readFileSync('public/arcade.js','utf8'),ctx);
  const deliver=round=>ctx.onArcadeState({type:'ag',game,config:config(game),balance:10000,...publicState(game,round),requestId:state.ag.pending?.id});
  const advance=now=>{const pending=[...frames.values()];frames.clear();for(const f of pending)f(now);};
  return {ctx,state,$,frames,sent,deliver,advance,maxButton};
}
for(const game of ['plinko','keno','dragon'])test(`${game}: result animation locks repeat stakes, ends, and releases controls`,()=>{
  const h=harness(game);h.deliver(initial());
  h.ctx.agRequest('start');h.ctx.agRequest('start');assert.equal(h.sent.length,1);
  const result=start(game,initial(),100,h.state.ag.options[game],0,()=>0);result.settled=true;
  h.deliver(result);assert.equal(h.state.ag.animating,true);assert.equal(h.$('ag-main').disabled,true);
  h.ctx.agRequest('start');assert.equal(h.sent.length,1);
  h.advance(6000);assert.equal(h.frames.size,0);assert.equal(h.state.ag.animating,false);assert.equal(h.$('ag-main').disabled,false);
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
test('opening the Tower select does not destroy it; a change updates tiles, payout table and stake limit',()=>{
  const h=harness('tower');h.deliver(initial());h.ctx.bindArcade();
  const settings=h.$('ag-settings'), target={id:'ag-difficulty',value:'medium',closest:()=>null};
  const writes=settings.writes;
  settings.listeners.click({target});assert.equal(settings.writes,writes,'opening click must leave native picker mounted');
  settings.listeners.change({target});
  assert.equal(h.state.ag.options.tower.level,'medium');
  assert.match(h.$('ag-stage').innerHTML,/--ag-columns:3/);
  assert.match(settings.innerHTML,/value="medium" selected/);
  assert.equal(h.$('ag-paytable').innerHTML,'');
  assert.match(h.$('ag-stage').innerHTML,/class="ag-floor-pay">1.47×/);
  assert.match(h.$('ag-limit').textContent,/\$1000.00/);
  h.state.balance=200000;
  h.maxButton.listeners.click();assert.equal(h.$('ag-amount').value,'1000,00');
  h.ctx.agRequest('start');assert.equal(h.sent.at(-1).amount,100000);assert.equal(h.sent.at(-1).options.level,'medium');
  settings.listeners.change({target:{...target,value:'master'}});
  assert.equal(h.state.ag.options.tower.level,'medium','pending stake locks difficulty');
  const round=start('tower',initial(),100000,{level:'medium'},0,()=>0);h.deliver(round);
  settings.listeners.change({target:{...target,value:'master'}});
  assert.equal(h.state.ag.options.tower.level,'medium','live round locks difficulty');
});
test('Tower limit, MAX and manual validation agree for every selected difficulty',()=>{
  const h=harness('tower');h.deliver(initial());h.ctx.bindArcade();h.state.balance=200000;
  for(const [level,limit] of Object.entries(config('tower').maxBets)){
    h.$('ag-settings').listeners.change({target:{id:'ag-difficulty',value:level}});
    assert.equal(h.ctx.agMaxBet(),limit);assert.equal(h.$('ag-amount').max,(limit/100).toFixed(2));
    h.maxButton.listeners.click();assert.equal(h.$('ag-amount').value,(limit/100).toFixed(2).replace('.',','));
    h.$('ag-amount').value=((limit+1)/100).toFixed(2);h.ctx.agRequest('start');assert.equal(h.sent.length,0);
  }
});
test('Plinko shows each contact and leaves the ball inside its actual winning pocket',()=>{
  const h=harness('plinko');h.deliver(initial());h.ctx.agRequest('start');
  const result=start('plinko',initial(),100,{risk:'medium'},0,()=>1);result.settled=true;h.deliver(result);
  h.advance(400);assert.ok(h.$('ag-pin-impact').attributes.opacity>0);
  h.advance(3000);assert.equal(h.state.ag.animating,true,'fall should not race through the board');
  h.advance(6000);assert.equal(h.state.ag.animating,false);
  assert.match(h.$('ag-stage').innerHTML,/data-ag-slot="10"/);
  assert.match(h.$('ag-stage').innerHTML,/id="ag-ball" cx="320" cy="284.5"/);
});
test('Plinko launches a chosen batch, shows running totals, then one combined result',()=>{
  const h=harness('plinko');h.deliver(initial());h.ctx.bindArcade();
  const count={dataset:{agCount:'5'}};
  h.$('ag-settings').listeners.click({target:{closest:selector=>selector==='[data-ag-count]'?count:null}});
  assert.equal(h.state.ag.options.plinko.count,5);assert.match(h.$('ag-note').textContent,/5 × \$1.00 = \$5.00/);
  h.ctx.agRequest('start');assert.equal(h.sent.at(-1).options.count,5);
  const round=start('plinko',initial(),100,{risk:'medium',count:5},0,()=>0);round.settled=true;h.deliver(round);
  assert.equal((h.$('ag-stage').innerHTML.match(/id="ag-ball(?:-\d+)?"/g)||[]).length,5);
  h.advance(4400);assert.equal(h.state.ag.animating,true);assert.match(h.$('ag-note').textContent,/1\/5/);
  h.advance(6000);assert.equal(h.state.ag.animating,false);
  assert.equal(h.$('ag-payout').textContent,'$110.00');assert.match(h.$('ag-note').textContent,/5 × \$1.00 = \$5.00/);
  assert.doesNotMatch(h.$('ag-note').textContent,/Выплата|Итог/);
  assert.match(h.$('ag-overlay').innerHTML,/\$110.00/);
});
test('Plinko MAX divides the balance across all balls and manual oversized batches are blocked',()=>{
  const h=harness('plinko');h.deliver(initial());h.ctx.bindArcade();h.state.ag.options.plinko.count=25;
  h.maxButton.listeners.click();assert.equal(h.$('ag-amount').value,'4,00');
  h.$('ag-amount').value='5,00';h.ctx.agRequest('start');assert.equal(h.sent.length,0);
});

test('keno clears drawn and hit highlights after animation without clearing user picks or result',()=>{
 const h=harness('keno');h.deliver(initial());h.ctx.agRequest('start');
 const r=start('keno',initial(),100,h.state.ag.options.keno,0,()=>0);r.settled=true;h.deliver(r);h.advance(6000);
 assert.doesNotMatch(h.$('ag-stage').innerHTML,/class="[^"]*is-drawn|class="[^"]*is-hit/);
 assert.deepEqual(h.state.ag.options.keno.picks,[1,2,3]);assert.equal(h.state.ag.info.drawn.length,10);
 h.ctx.renderArcade();assert.doesNotMatch(h.$('ag-stage').innerHTML,/class="[^"]*is-drawn|class="[^"]*is-hit/);
 h.ctx.agRequest('start');assert.equal(h.sent.length,2);
});
