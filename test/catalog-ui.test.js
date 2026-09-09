'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm');
const {games,ids}=require('../public/casino-rules'),game=require('../server/arcade/game');
function harness(id){
 const elements=new Map(),frames=new Map(),sent=[];let next=0;
 const element=()=>({innerHTML:'',textContent:'',value:'1,00',disabled:false,dataset:{},style:{},attributes:{},listeners:{},classList:{add(){},remove(){},toggle(){}},setAttribute(k,v){this.attributes[k]=v;},querySelector(){return element();},querySelectorAll(){return [];},addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);},dispatch(type,target){for(const fn of this.listeners[type]||[])fn({target});}});
 const $=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
 const state={connected:true,balance:100000,ag:{game:id,info:null,pending:null,animating:false,token:0,raf:null,options:{}}};
 const ctx=vm.createContext({state,$,document:{querySelectorAll:()=>[]},window:{matchMedia:()=>({matches:false})},performance:{now:()=>0},structuredClone,
 send:m=>sent.push(m),money:n=>'$'+((n||0)/100).toFixed(2),toCents:v=>Math.round(Number(v.replace(',','.'))*100),haptic(){},toast(){},
 requestAnimationFrame:f=>{const id=++next;frames.set(id,f);return id;},cancelAnimationFrame:id=>frames.delete(id)});
 for(const file of ['casino-rules','casino-art','casino-motion','casino-ui','arcade'])vm.runInContext(fs.readFileSync(`public/${file}.js`,'utf8'),ctx);
 vm.runInContext(`CasinoUI.prepare('${id}');`,ctx);ctx.bindArcade();
 const deliver=round=>ctx.onArcadeState({game:id,config:game.config(id),balance:100000,...game.publicState(id,round),requestId:state.ag.pending?.id});
 const advance=(now=10000)=>{const list=[...frames.values()];frames.clear();for(const f of list)f(now);};
 const click=(container,key,value)=>{const target={dataset:{[key]:value},disabled:false,closest:selector=>selector===`[data-${key.replace(/[A-Z]/g,c=>'-'+c.toLowerCase())}]`?target:null};$(container).dispatch('click',target);};
 return {ctx,state,$,sent,deliver,advance,frames,click};
}
for(const id of ids)test(`${id}: every board renders, actions send once, animations finish, reconnect state stays playable`,()=>{
 const h=harness(id);h.deliver(game.initial());
 assert.match(h.$('ag-stage').innerHTML,/class="cg-board cg-game-/,'board wrapper must not inherit scene grid/flex sizing');
 assert.ok(!h.$('ag-stage').innerHTML.includes('undefined'));assert.equal(h.$('ag-main').disabled,false);
 h.$('ag-main').dispatch('click',{});h.$('ag-main').dispatch('click',{});assert.equal(h.sent.length,1);assert.equal(h.sent[0].type,'ag_start');
 let r=game.start(id,game.initial(),100,structuredClone(games[id].defaults),0,n=>n-1);r.settled=r.phase==='done';h.deliver(r);h.advance();
 if(r.phase==='play'){
  if(id==='videopoker'){h.click('ag-stage','cgHold','0');h.click('ag-stage','cgHold','4');h.$('ag-main').dispatch('click',{});assert.equal(JSON.stringify(h.sent.at(-1).index),'[0,4]');r=game.actGame(id,r,'ag_pick',[0,4],r.revision);}
  else if(id==='scratch'){for(let i=0;i<9;i++){h.click('ag-stage','cgScratch',String(i));assert.equal(h.sent.at(-1).index,i);r=game.actGame(id,r,'ag_pick',i,r.revision);r.settled=r.phase==='done';h.deliver(r);} }
  else {h.$('ag-main').dispatch('click',{});assert.equal(h.sent.at(-1).type,'ag_cashout');r=game.actGame(id,r,'ag_cashout',null,r.revision);}
  r.settled=true;h.deliver(r);h.advance();
 }
 assert.equal(h.state.ag.animating,false);assert.equal(h.frames.size,0);assert.equal(h.$('ag-main').disabled,false);
 assert.equal(h.$('ag-payout').textContent,'$'+(r.payout/100).toFixed(2));assert.ok(!h.$('ag-stage').innerHTML.includes('undefined'));
 h.state.connected=false;h.ctx.renderArcade();assert.equal(h.$('ag-main').disabled,true);
});
test('series board buttons are usable while cashout and stake controls keep their own states',()=>{
 for(const id of ids.filter(id=>games[id].series)){
  const h=harness(id);h.deliver(game.initial());h.ctx.agRequest('start');const r=game.start(id,game.initial(),100,structuredClone(games[id].defaults),0,n=>n-1);h.deliver(r);
  assert.equal(h.$('ag-main').disabled,false);assert.equal(h.$('ag-amount').disabled,true);
  const before=h.sent.length;h.click('ag-stage','cgPick','0');assert.equal(h.sent.length,before+1,id);assert.equal(h.sent.at(-1).type,'ag_pick');
 }
});
test('game choices preserve native inputs and map numeric values to numbers',()=>{
 for(const id of ids.filter(id=>games[id].choices)){
  const h=harness(id);h.deliver(game.initial());const [label,value]=games[id].choices.at(-1),key=id==='chicken'||id==='balloon'?'level':'side';
  const target={dataset:{cgOption:String(value),cgKey:key},closest:selector=>selector==='[data-cg-option]'?target:null};h.$('ag-settings').dispatch('click',target);
  h.ctx.agRequest('start');assert.equal(h.sent.at(-1).options[key],value);
 }
 const h=harness('limbo');h.deliver(game.initial());h.$('ag-settings').dispatch('change',{id:'cg-target',value:'3,50'});h.ctx.agRequest('start');assert.equal(h.sent.at(-1).options.target,3.5);
});
test('catalog launchers contain all 16 distinct games and no baccarat duplicate',()=>{
 const h=harness('diamonds'),html=h.$('casino-catalog').innerHTML;
 const idsInHtml=[...html.matchAll(/data-arcade="([^"]+)"/g)].map(m=>m[1]);assert.deepEqual(idsInHtml,ids);assert.equal(new Set(idsInHtml).size,16);assert.ok(!html.includes('data-arcade="baccarat"'));
});

test('active animations lock clicks and stop permanently when leaving any game',()=>{
 for(const id of ids){
  const h=harness(id);h.deliver(game.initial());h.ctx.agRequest('start');
  let r=game.start(id,game.initial(),100,structuredClone(games[id].defaults),0,n=>n-1);r.settled=r.phase==='done';h.deliver(r);
  if(games[id].series){h.ctx.agRequest('pick',{index:0});r=game.actGame(id,r,'ag_pick',0,r.revision,n=>n-1);r.settled=r.phase==='done';h.deliver(r);}
  h.advance(100);assert.equal(h.state.ag.animating,true,id);assert.equal(h.$('ag-main').disabled,true,id);assert.equal(h.frames.size,1,id);
  const count=h.sent.length;h.$('ag-main').dispatch('click',{});h.click('ag-stage','cgPick','0');assert.equal(h.sent.length,count,id);
  h.ctx.stopArcade();h.advance(10000);assert.equal(h.state.ag.animating,false,id);assert.equal(h.frames.size,0,id);
 }
});
test('scene markup uses project textures and generated assets rather than placeholder drawings',()=>{
 const h=harness('diamonds');h.deliver(game.initial());
 assert.match(h.$('casino-catalog').innerHTML,/cg-sprite/);
 for(const id of ['cases','collection','scratch'])assert.ok(!h.$('casino-catalog').innerHTML.includes(`data-arcade="${id}"`));
 assert.match(fs.readFileSync('public/casino-ui.css','utf8'),/img\/catalog\/objects.webp/);
 for(const asset of ['objects','environments'])assert.ok(fs.statSync(`public/img/catalog/${asset}.webp`).size>10000);
});

test('Diamonds matches the approved table and highlights only the actual combination after revealing',()=>{
 const fixtures=[[[0,0,0,0,0],'Пять одинаковых',5],[[0,0,0,0,1],'Четыре одинаковых',4],[[0,0,0,1,1],'Фулл-хаус',5],[[0,0,0,1,2],'Три одинаковых',3],[[0,0,1,1,2],'Две пары',4],[[0,0,1,2,3],'Пара',2],[[0,1,2,3,4],'Нет совпадений',0]];
 for(const [gems,label,matches] of fixtures){
  const h=harness('diamonds');h.deliver(game.initial());h.ctx.agRequest('start');let i=0;
  const r=game.start('diamonds',game.initial(),100,{},0,()=>gems[i++]);r.settled=true;h.deliver(r);
  assert.ok(!h.$('ag-stage').innerHTML.includes('is-selected'),'no outcome highlight before reveal');
  h.advance();const html=h.$('ag-stage').innerHTML;
  assert.equal((html.match(/class="dm-tile is-match"/g)||[]).length,matches,label);
  assert.equal((html.match(/class="dm-pay-row is-selected"/g)||[]).length,1,label);
  assert.equal((html.match(/role="row"/g)||[]).length,7);
  assert.ok(html.includes(label));assert.ok(!html.includes('cg-jewel-tray'));assert.ok(!html.includes('cg-sprite'));
  assert.equal(h.$('ag-overlay').innerHTML,'','inline result should not be covered by an overlay');
 }
});
