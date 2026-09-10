'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function harness(reduced=false){
 let next=1,current=null,callbackCount=0;const frames=new Map();
 const node=()=>({textContent:'',hidden:false,isConnected:true,focus(){},remove(){this.isConnected=false;},dataset:{}});
 const document={querySelectorAll:()=>current?[current]:[],getElementById:()=>({appendChild(n){current=n;}}),createElement(){const n=node(),parts={'.ax-total-count':node(),'.ax-total-x':node(),'button':node()};parts['.ax-total-x'].hidden=true;n.querySelector=k=>parts[k];return n;}};
 const context=vm.createContext({document,window:{matchMedia:()=>({matches:reduced})},performance:{now:()=>0},money:n=>'$'+(n/100).toFixed(2),requestAnimationFrame:f=>{const id=next++;frames.set(id,f);return id;},cancelAnimationFrame:id=>frames.delete(id),setTimeout,clearTimeout});
 vm.runInContext(fs.readFileSync('public/abyss-fx.js','utf8')+'\nglobalThis.fx=AbyssFX;',context);
 const info={payout:12840,unitBet:100,detail:{win:12840,capped:false},bonus:{played:12}};
 return {fx:context.fx,start(kind='big'){context.fx.celebrate(info,kind,()=>callbackCount++);},advance(time){const pending=[...frames.values()];frames.clear();pending.forEach(f=>f(time));},get amount(){return current.querySelector('.ax-total-count').textContent;},get hidden(){return current.querySelector('.ax-total-x').hidden;},get callbacks(){return callbackCount;},get connected(){return current.isConnected;}};
}
test('first tap completes the slow counter and reveals multiplier; only the second tap continues',()=>{
 const h=harness();h.start();h.advance(4500);assert.equal(h.amount,'$64.20');assert.equal(h.hidden,true);
 assert.equal(h.fx.finish(),false);assert.equal(h.amount,'$128.40');assert.equal(h.hidden,false);assert.equal(h.callbacks,0);assert.equal(h.connected,true);
 h.advance(9000);assert.equal(h.callbacks,0);assert.equal(h.fx.finish(),true);assert.equal(h.callbacks,1);assert.equal(h.connected,false);
 h.fx.finish();assert.equal(h.callbacks,1);
});
test('natural completion reveals multiplier only at the end, including bonus totals',()=>{
 for(const [kind,duration] of [['big',9000],['summary',12000]]){const h=harness();h.start(kind);h.advance(duration-1);assert.equal(h.hidden,true);h.advance(duration);assert.equal(h.hidden,false);assert.equal(h.amount,'$128.40');assert.equal(h.callbacks,0);h.fx.finish();assert.equal(h.callbacks,1);}
});
test('reduced motion shows the complete result immediately; clearing cancels stale completion',()=>{
 const h=harness(true);h.start();h.advance(0);assert.equal(h.amount,'$128.40');assert.equal(h.hidden,false);h.fx.finish();assert.equal(h.callbacks,1);
 const normal=harness();normal.start();normal.fx.clear();normal.advance(20000);normal.fx.finish();assert.equal(normal.callbacks,0);
});
