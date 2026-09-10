'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const rules=require('../public/feature-slots-rules');
function harness(grid,reduced=false){
 const nodes=new Map(),reels=Array.from({length:5},(_,col)=>{const flags=new Set();return {dataset:{axReel:String(col),length:'36'},style:{},classList:{toggle(){}},parentElement:{classList:{toggle(k,v){v?flags.add(k):flags.delete(k);}}},flags};});
 const $=id=>{if(!nodes.has(id))nodes.set(id,{style:{},classList:{},querySelectorAll:()=>id==='ag-stage'?reels:[],innerHTML:'',textContent:''});return nodes.get(id);};
 let frame=null,resultCalls=0,hidden=0;const celebrations=[],sounds=[];
 const info={phase:'done',revision:2,settled:true,payout:0,detail:{grid,lines:[],win:0},bonus:{remaining:0,multiplier:1}};
 const state={connected:true,balance:10000,ag:{game:'cryo',info:null,pending:{id:'a',action:'start'},token:0}};
 const ctx=vm.createContext({FeatureSlotAudio:{unlock(){},stop(){},settings:()=>({muted:false}),spinning(){},anticipation(){},play(k,v){sounds.push([k,v]);}},FeatureSlotRules:rules,AbyssFX:{clear(){},spinWin(){},feature(){},celebrate(info,kind){celebrations.push(kind);}},state,$,money:n=>'$'+(n/100).toFixed(2),agLocked:()=>!!state.ag.pending||state.ag.animating,GameResult:{hide(){hidden++;}},agResult(){resultCalls++;},performance:{now:()=>0},window:{matchMedia:()=>({matches:reduced})},document:{addEventListener(){},getElementById:()=>null,hidden:false},requestAnimationFrame:f=>{frame=f;return 1;},setTimeout,clearTimeout});
 vm.runInContext(fs.readFileSync('public/feature-slots-ui.js','utf8')+'\nglobalThis.ui=FeatureSlotsUI;',ctx);
 return {ctx,state,info,reels,$,celebrations,sounds,deliver(){ctx.ui.receive({...info,requestId:'a',accepted:true});},advance(n){const f=frame;frame=null;f(n);},get resultCalls(){return resultCalls;},get hidden(){return hidden;}};
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
test('base console groups stake, centered spin and bonus purchase; secondary buttons live in the menu',()=>{
 const h=harness(Array(15).fill(0));h.deliver();h.advance(3000);const html=h.$('ag-settings').innerHTML;
 assert.ok(html.indexOf('data-ax="stake"')<html.indexOf('data-ax="spin"'));assert.ok(html.indexOf('data-ax="spin"')<html.indexOf('data-ax="buy"'));assert.ok(html.includes('data-ax="menu"'));assert.ok(html.includes('data-ax="turbo"'));for(const id of ['sound','rules'])assert.ok(!html.includes('data-ax="'+id+'"'));assert.equal(h.$('ag-amount').value,'0.20');
});

test('a capped bonus payout shows the limit instead of an incorrect uncapped equation',()=>{
 const h=harness(Array(15).fill(0));
 Object.assign(h.info,{unitBet:20,payout:50000,bonus:{remaining:0,played:8,multiplier:10}});
 Object.assign(h.info.detail,{bonusSpin:true,usedMultiplier:9,rawWin:900,win:100,capped:true});
 h.state.ag.pending=null;h.state.ag.info=h.info;h.ctx.ui.render();
 const html=h.$('ag-stage').innerHTML;
 assert.ok(html.includes('Достигнут максимум 2500×'));assert.ok(!html.includes('$1.00 × 9 = $1.00'));
});



test('a single stopped Scatter sounds once even when no bonus is triggered',()=>{
 const grid=Array(15).fill(0);grid[0]=9;const h=harness(grid);h.deliver();h.advance(1900);h.advance(2000);h.advance(5000);
 assert.deepEqual(h.sounds.filter(([k])=>k==='scatter'),[['scatter',1]]);
});

test('sticky Wilds stay in fixed overlays with old multipliers throughout the spin',()=>{const h=harness(Array(15).fill(8));h.state.ag.pending=null;h.state.ag.info=h.info;h.info.bonus.locked={1:3};h.info.detail.bonusSpin=true;h.ctx.ui.render();assert.ok(h.$('ag-stage').innerHTML.includes('fs-frozen'));assert.ok(h.$('ag-stage').innerHTML.includes('×3'));h.state.ag.cgPrevious={bonus:{locked:{1:2}}};h.state.ag.animating=true;h.ctx.ui.render();assert.ok(h.$('ag-stage').innerHTML.includes('×2'));assert.ok(!h.$('ag-stage').innerHTML.includes('×3'));});
 test('all five reel stops sound once, including reduced-motion completion',()=>{const h=harness(Array(15).fill(0),true);h.deliver();h.advance(0);assert.equal(h.sounds.filter(([k])=>k==='stop').length,5);});

test('reference scene uses the raster atlas for all 15 live symbols',()=>{const h=harness(Array.from({length:15},(_,i)=>i%10));h.state.ag.pending=null;h.state.ag.info=h.info;h.ctx.ui.render();const html=h.$('ag-stage').innerHTML;assert.equal((html.match(/class="fs-symbol"/g)||[]).length,15);assert.ok(!html.includes('.svg'));assert.ok(html.includes('DEEP FREEZE'));assert.ok(html.includes('WILDS STAY FROZEN'));});
