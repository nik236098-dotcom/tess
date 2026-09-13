'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(require.resolve('../public/app.js'),'utf8');
function load(name,ctx){const start=source.indexOf('function '+name+'('),end=source.indexOf('\n}\n',start)+2;vm.runInNewContext(source.slice(start,end),ctx);return ctx[name];}
test('avatar initials preserve emoji and combining characters; blank names are safe',()=>{
 const initial=load('playerInitial',{Intl});
 assert.equal(initial(' 🐊 Croco'),'🐊');assert.equal(initial('👩‍💻 Test'),'👩‍💻');assert.equal(initial('  '),'?');assert.equal(initial('никита'),'Н');assert.equal(initial('и\u0306ван'),'И\u0306');
});
test('late Baccarat reply updates the account but never starts hidden animations',()=>{
 let renders=0,deals=0;const ctx={state:{bc:{open:false}},renderAccount(){renders++;},startBaccaratDeal(){deals++;},bcRenderHistory(){throw Error('hidden history');},bcShowBalance(){throw Error('hidden balance');},renderBaccarat(){throw Error('hidden render');}};
 load('onBaccaratState',ctx)({balance:321,round:{}});assert.equal(ctx.state.balance,321);assert.equal(renders,1);assert.equal(deals,0);
});
test('clearing the Baccarat table permits identical consecutive results after dismissal',()=>{
 const GameResult=require('../public/game-result');
 const node=()=>({dataset:{},innerHTML:'',textContent:'',classList:{add(){},remove(){}},setAttribute(){}});
 const nodes=new Map();const $=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);};
 const result=$('bc-result'),round={bet:100,payout:200};
 GameResult.show(result,round,'same');result.onclick();assert.equal(GameResult.show(result,round,'same'),false);
 load('bcClearTable',{$,GameResult})();assert.equal(GameResult.show(result,round,'same'),true);assert.match(result.innerHTML,/2.00×/);
});
