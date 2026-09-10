'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const R=require('../public/abyss-rules');
function harness(grid,reduced=false){
 const nodes=new Map(),reels=Array.from({length:5},(_,col)=>{const flags=new Set();return {dataset:{axReel:String(col),length:'36'},style:{},classList:{toggle(){}},parentElement:{classList:{toggle(k,v){v?flags.add(k):flags.delete(k);}}},flags};});
 const $=id=>{if(!nodes.has(id))nodes.set(id,{style:{},classList:{},querySelectorAll:()=>id==='ag-stage'?reels:[],innerHTML:'',textContent:''});return nodes.get(id);};
 let frame=null,resultCalls=0,hidden=0;const celebrations=[];
 const info={phase:'done',revision:2,settled:true,payout:0,detail:{grid,lines:[],win:0},bonus:{remaining:0,multiplier:1}};
 const state={connected:true,balance:10000,ag:{game:'abyss',info:null,pending:{id:'a',action:'start'},token:0}};
 const ctx=vm.createContext({AbyssRules:R,AbyssFX:{clear(){},spinWin(){},feature(){},celebrate(info,kind){celebrations.push(kind);}},state,$,money:n=>'$'+(n/100).toFixed(2),agLocked:()=>!!state.ag.pending||state.ag.animating,GameResult:{hide(){hidden++;}},agResult(){resultCalls++;},performance:{now:()=>0},window:{matchMedia:()=>({matches:reduced})},document:{addEventListener(){},getElementById:()=>null,hidden:false},requestAnimationFrame:f=>{frame=f;return 1;},setTimeout,clearTimeout});
 vm.runInContext(fs.readFileSync('public/abyss-ui.js','utf8')+'\nglobalThis.ui=AbyssUI;',ctx);
 return {ctx,state,info,reels,$,celebrations,deliver(){ctx.ui.receive({...info,requestId:'a',accepted:true});},advance(n){const f=frame;frame=null;f(n);},get resultCalls(){return resultCalls;},get hidden(){return hidden;}};
}
test('ordinary slot results never open the shared win, loss or refund overlay',()=>{
 for(const result of ['win','lose','push']){const h=harness(Array(15).fill(0));h.info.result=result;h.deliver();h.advance(3000);assert.equal(h.state.ag.animating,false);assert.equal(h.resultCalls,0);assert.ok(h.hidden>0);}
});
test('two stopped Scatter slow the following reel whether or not a third Scatter lands',()=>{
 for(const third of [false,true]){const grid=Array(15).fill(0);grid[0]=9;grid[6]=9;if(third)grid[12]=9;const h=harness(grid);h.state.ag.info=h.info;h.ctx.ui.paint(.8);assert.ok(h.reels[2].flags.has('is-anticipating'));assert.ok(h.reels[0].flags.has('is-settled'));assert.ok(h.reels[1].flags.has('is-settled'));h.ctx.ui.paint(5);for(const reel of h.reels){assert.ok(reel.flags.has('is-settled'));assert.ok(!reel.flags.has('is-anticipating'));assert.ok(Math.abs(Number(reel.style.transform.slice(11,-2)))<1e-9);}}
});
test('one Scatter never activates anticipation; reduced motion completes without waiting',()=>{
 const grid=Array(15).fill(0);grid[0]=9;const h=harness(grid);h.state.ag.info=h.info;h.ctx.ui.paint(.8);assert.ok(h.reels.every(r=>!r.flags.has('is-anticipating')));
 grid[6]=9;const reduced=harness(grid,true);reduced.deliver();reduced.advance(0);assert.equal(reduced.state.ag.animating,false);assert.equal(reduced.resultCalls,0);
});

test('Big Win starts at 50 times the spin stake, not the 100-stake purchase price',()=>{
 for(const [win,expected] of [[999,[]],[1000,['big']],[10000,['big']]]){const h=harness(Array(15).fill(0));Object.assign(h.info,{unitBet:20,bet:2000,payout:win});h.info.detail.win=win;h.deliver();h.advance(3000);assert.deepEqual(h.celebrations,expected);}
});
test('the final feature shows one cumulative summary, including a zero payout',()=>{
 for(const win of [0,50000]){const h=harness(Array(15).fill(0));Object.assign(h.info,{unitBet:20,payout:win});h.info.bonus.played=8;h.info.detail.win=win;h.deliver();h.advance(3000);assert.deepEqual(h.celebrations,['summary']);}
});
