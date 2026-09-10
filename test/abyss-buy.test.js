'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const rules=require('../public/abyss-rules');
async function harness(balance=10000){
 const elements=new Map(),events=new Map(),requests=[],prefs=new Map();
 const element=()=>({innerHTML:'',textContent:'',style:{},classList:{toggle(){}},focus(){},querySelector(){return {focus(){}};},querySelectorAll(){return [];},appendChild(n){elements.set(n.id,n);},remove(){elements.delete(this.id);}});
 const $=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
 const state={balance,isAdmin:false,ag:{game:'abyss',pending:null,animating:false,options:{},info:{phase:'done',settled:true,detail:{grid:Array(15).fill(0),lines:[],win:0},bonus:{remaining:0,multiplier:1}}}};
 const c=vm.createContext({state,$,AbyssRules:rules,AbyssAudio:{unlock(){},stop(){},settings:()=>({muted:true}),setMode(){}},AbyssFX:{clear(){}},GameResult:{hide(){}},money:n=>'$'+(n/100).toFixed(2),agLocked:()=>!!state.ag.pending||state.ag.animating,
  localStorage:{getItem:k=>prefs.get(k),setItem:(k,v)=>prefs.set(k,v)},Image:class{set src(v){this.onload();}},clearTimeout,setTimeout,
  document:{activeElement:element(),hidden:false,addEventListener:(k,f)=>events.set(k,f),createElement:element,getElementById:id=>elements.get(id)},
  agRequest:action=>requests.push({action,amount:$('ag-amount').value,options:{...state.ag.options.abyss}})});
 vm.runInContext(fs.readFileSync('public/abyss-ui.js','utf8')+'\nglobalThis.ui=AbyssUI;',c);c.ui.prepare();await Promise.resolve();await Promise.resolve();
 return {state,requests,prefs,$,html:()=>elements.get('ax-dialog')?.innerHTML,
 click(action){events.get('click')({target:{closest:()=>({dataset:{ax:action},disabled:false})}});},select(value){events.get('change')({target:{id:'ax-buy-unit',value:String(value)}});}};
}
test('bonus purchase stays open while its stake and actual request amount change together',async()=>{
 const h=await harness();h.click('buy');assert.match(h.html(),/Купить за \$20\.00/);
 h.click('buy-plus');assert.match(h.html(),/Купить за \$40\.00/);assert.equal(h.$('ag-amount').value,'0.40');
 h.select(100);assert.match(h.html(),/Купить за \$100\.00/);assert.equal(h.$('ag-amount').value,'1.00');
 h.click('buy-minus');assert.match(h.html(),/Купить за \$80\.00/);assert.equal(h.$('ag-amount').value,'0.80');
 assert.equal(h.requests.length,0);h.click('confirm-buy');assert.deepEqual(h.requests,[{action:'start',amount:'0.80',options:{buyBonus:true}}]);
});
test('lowering stake makes an unaffordable bonus purchasable without charging on selection',async()=>{
 const h=await harness(3000);h.click('buy');h.select(100);assert.match(h.html(),/Недостаточно средств/);h.click('confirm-buy');assert.equal(h.requests.length,0);
 h.select(20);assert.match(h.html(),/Купить за \$20\.00/);h.click('confirm-buy');assert.equal(h.requests[0].amount,'0.20');
});
test('buy controls reject out-of-range stakes and changes during an active or pending round',async()=>{
 const h=await harness();h.click('buy');h.click('buy-minus');assert.equal(h.$('ag-amount').value,'0.20');
 for(const v of [0,19,NaN,100001])h.select(v);assert.equal(h.$('ag-amount').value,'0.20');
 h.select(rules.stakes.at(-1));h.click('buy-plus');assert.equal(h.$('ag-amount').value,'1000.00');
 for(const [key,value] of [['phase','play'],['settled',false]]){const previous=h.state.ag.info[key];h.state.ag.info[key]=value;h.select(20);assert.equal(h.$('ag-amount').value,'1000.00');h.state.ag.info[key]=previous;}
 h.state.ag.pending={id:'pending'};h.select(20);assert.equal(h.$('ag-amount').value,'1000.00');
});
