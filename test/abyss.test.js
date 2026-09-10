'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const G=require('../server/arcade/game'),A=require('../server/arcade/abyss'),R=require('../public/abyss-rules');
const {createArcadeService}=require('../server/arcade/service'),{Accounts}=require('../server/accounts');
const sum=w=>w.reduce((a,b)=>a+b,0);
function gridRng(grid){let i=0;return max=>{const w=max===sum(R.bonusWeights)?R.bonusWeights:R.baseWeights;assert.equal(max,sum(w));const symbol=grid[i++%15];return sum(w.slice(0,symbol));};}
const all=n=>Array(15).fill(n);
function service(balance=10000,rng=()=>0){
 const account={id:'qa',name:'QA',balance},messages=[],saved=[],wins=[];
 const accounts={get:()=>account,flush(){saved.push(structuredClone(account));}};
 const client={user:{id:'qa'},send:m=>messages.push(m)};
 const engine=createArcadeService({accounts,noteWin:w=>wins.push(w),rng});
 return {account,accounts,messages,saved,wins,run:m=>engine.handle(client,{game:'abyss',...m})};
}
test('Abyss is separate from Croc Slots; discrete stakes and buy options are validated',()=>{
 assert.ok(G.GAMES.includes('abyss'));assert.ok(G.GAMES.includes('slots'));
 assert.equal(R.lines.length,20);assert.equal(new Set(R.lines.map(l=>l.join(','))).size,20);
 for(const stake of R.stakes){assert.equal(stake%20,0);const r=G.start('abyss',G.initial(),stake,{buyBonus:true},0,()=>0);assert.equal(r.bet,stake*100);assert.equal(r.unitBet,stake);assert.equal(r.detail.grid.filter(n=>n===R.scatter).length,3);assert.equal(r.bonus.played,0);assert.equal(r.detail.bought,true);assert.equal(A.evaluate(r.detail.grid,stake).payout,0);}
 for(const amount of [0,19,21,39,100001,'20',20.5,NaN])assert.throws(()=>G.start('abyss',G.initial(),amount,{},0));
 for(const options of [null,[],{buyBonus:1},{buyBonus:'true'}])assert.throws(()=>G.start('abyss',G.initial(),20,options,0));
});
test('Wild substitutes ordinary symbols but never Scatter; only the best left-to-right line pays',()=>{
 const grid=all(9);grid.splice(0,3,0,8,0);const result=A.evaluate(grid,20);
 assert.deepEqual(result.lines.map(l=>[l.line,l.count,l.payout]),[[0,3,R.symbols[0].pay[0]]]);
 grid.splice(0,5,0,9,0,0,0);assert.equal(A.evaluate(grid,20).payout,0);
 const wild=A.evaluate(all(8),20);assert.equal(wild.lines.length,20);assert.equal(wild.payout,20*1000);
 for(const amount of R.stakes)assert.ok(Number.isSafeInteger(A.evaluate(all(8),amount).payout));
});
test('Scatter starts saved free spins; every result exposes only the current grid',()=>{
 const before=G.initial(),round=G.start('abyss',before,20,{},0,gridRng(all(9)));
 assert.equal(round.phase,'play');assert.equal(round.bonus.remaining,8);assert.equal(round.payout,0);assert.equal(before.phase,'bet');
 const view=G.publicState('abyss',round);assert.equal(view.detail.scatterCount,15);view.bonus.remaining=999;assert.equal(round.bonus.remaining,8);
 for(const key of ['deck','queue','future','seed'])assert.equal(view[key],undefined);
 assert.throws(()=>G.start('abyss',round,40,{},round.revision));assert.throws(()=>G.actGame('abyss',round,'ag_cashout',0,round.revision));
});
test('bonus wins increase the next multiplier and the round maximum settles correctly',()=>{
 let r=G.start('abyss',G.initial(),20,{buyBonus:true},0,()=>0);const rev=r.revision;
 r=G.actGame('abyss',r,'ag_pick',0,r.revision,gridRng(all(8)));
 assert.equal(r.detail.usedMultiplier,1);assert.equal(r.bonus.multiplier,2);assert.equal(r.bonus.remaining,7);assert.equal(r.payout,20000);assert.equal(r.bet,2000);
 assert.throws(()=>G.actGame('abyss',r,'ag_pick',0,rev));
 r=G.actGame('abyss',r,'ag_pick',0,r.revision,gridRng(all(8)));
 assert.equal(r.phase,'done');assert.equal(r.payout,20*R.maxWin);assert.equal(r.detail.win,30000);assert.equal(r.detail.capped,true);assert.equal(r.multiplier,25);
 assert.throws(()=>G.start('abyss',r,20,{},r.revision),'uncredited winnings cannot be overwritten');
});
test('retriggering is finite even with fifteen scatters on every free spin',()=>{
 let r=G.start('abyss',G.initial(),20,{buyBonus:true},0,()=>0),count=0;
 while(r.phase==='play'){r=G.actGame('abyss',r,'ag_pick',0,r.revision,gridRng(all(9)));assert.ok(++count<=40);assert.ok(r.bonus.awarded<=40);}
 assert.equal(count,40);assert.equal(r.bonus.remaining,0);assert.equal(r.payout,0);
});
test('Bonus Buy debits exactly 100 stakes once; insufficient balance and duplicate messages do not debit',()=>{
 const h=service(10000),buy={type:'ag_start',amount:20,options:{buyBonus:true},revision:0};h.run(buy);
 assert.equal(h.account.balance,8000);assert.equal(h.saved.length,1);assert.equal(h.messages.at(-1).bonus.remaining,8);
 assert.throws(()=>h.run(buy));assert.equal(h.account.balance,8000);assert.equal(h.saved.length,1);
 const low=service(1999);assert.throws(()=>low.run(buy));assert.equal(low.account.balance,1999);assert.equal(low.saved.length,0);assert.equal(low.messages.at(-1).accepted,false);
});
test('save failure rolls back purchase, free-spin progression, and settlement together',()=>{
 const h=service();h.accounts.flush=()=>{throw Error('disk full');};
 assert.throws(()=>h.run({type:'ag_start',amount:20,options:{buyBonus:true},revision:0}),/сохранить/);assert.equal(h.account.balance,10000);assert.equal(h.account.arcadeRounds,undefined);
 h.accounts.flush=()=>{};h.run({type:'ag_start',amount:20,options:{buyBonus:true},revision:0});const before=structuredClone(h.account);
 h.accounts.flush=()=>{throw Error('disk full');};assert.throws(()=>h.run({type:'ag_pick',index:0,revision:h.messages.at(-1).revision}),/сохранить/);assert.deepEqual(h.account,before);
});
test('a purchased bonus survives account reload and its total is credited only once',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'abyss-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));const file=path.join(dir,'accounts.json');
 let accounts=new Accounts({file});accounts.ensure({id:'qa'});const before=accounts.balanceOf('qa'),messages=[];const client={user:{id:'qa'},send:m=>messages.push(m)};
 let engine=createArcadeService({accounts,noteWin(){},rng:()=>0});engine.handle(client,{type:'ag_start',game:'abyss',amount:20,options:{buyBonus:true},revision:0});
 accounts=new Accounts({file});engine=createArcadeService({accounts,noteWin(){},rng:gridRng(all(8))});engine.handle(client,{type:'ag_open',game:'abyss'});assert.equal(messages.at(-1).bonus.remaining,8);assert.equal(accounts.balanceOf('qa'),before-2000);
 engine.handle(client,{type:'ag_pick',game:'abyss',index:0,revision:messages.at(-1).revision});assert.equal(accounts.balanceOf('qa'),before-2000);
 engine.handle(client,{type:'ag_pick',game:'abyss',index:0,revision:messages.at(-1).revision});assert.equal(accounts.balanceOf('qa'),before-2000+50000);
 accounts=new Accounts({file});engine=createArcadeService({accounts,noteWin(){}});for(let i=0;i<4;i++)engine.handle(client,{type:'ag_open',game:'abyss'});assert.equal(accounts.balanceOf('qa'),before-2000+50000);assert.equal(messages.at(-1).settled,true);
});
