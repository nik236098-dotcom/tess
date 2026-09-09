'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const { CrashGame, CrashError, MAX }=require('../server/crash/game');
const game=point=>new CrashGame({draw:()=>point});
test('invalid bets and auto-stop coefficients do not start a round',()=>{
  const g=game(2);
  for(const amount of [0,-10,9,10.5,'100',NaN,Infinity,10000001]) assert.throws(()=>g.start(amount,2,0,0),CrashError);
  for(const target of [undefined,0,1,1.001,2.001,'2',NaN,Infinity,1000001]) assert.throws(()=>g.start(100,target,0,0),CrashError);
  assert.equal(g.phase,'bet');
});
test('live payload never exposes crash point, deadline, or future history',()=>{
  const g=game(25);g.start(100,2,0,1000);
  const s=g.state(1100);assert.equal(s.point,undefined);assert.equal(s.crashAt,undefined);assert.deepEqual(s.history,[]);
  assert.equal(g.snapshot().point,25);
});
test('manual cashout uses server time and pays once',()=>{
  const g=game(3);g.start(100,null,0,0);g.cashout(1,g.at(1.5));
  assert.equal(g.result,'win');assert.equal(g.payout,150);assert.throws(()=>g.cashout(1,g.at(2)),CrashError);
});
test('a late cashout cannot win after the crash, including the exact boundary',()=>{
  for(const extra of [0,1000]) {
    const g=game(1.5);g.start(100,null,0,0);assert.throws(()=>g.cashout(1,g.at(1.5)+extra),CrashError);
    assert.equal(g.result,'lose');assert.equal(g.payout,0);
  }
});
test('auto-stop runs before a later crash despite a delayed callback; equality wins',()=>{
  for(const point of [2,3]) {
    const g=game(point);g.start(100,2,0,0);g.advance(g.at(5));
    assert.equal(g.result,'win');assert.equal(g.payout,200);assert.equal(g.multiplier,2);
  }
});
test('crash before target loses and immediate 1.00 crashes lose',()=>{
  for(const point of [1,1.5]) {
    const g=game(point);g.start(100,2,0,0);g.advance(g.at(3));assert.equal(g.result,'lose');assert.equal(g.payout,0);
  }
});
test('recovery honours the original crash and auto-stop times',()=>{
  const original=game(3);original.start(100,2,0,0);
  const restored=game(1);restored.restore(JSON.parse(JSON.stringify(original.snapshot())));restored.advance(restored.at(4));
  assert.equal(restored.result,'win');assert.equal(restored.payout,200);
});
test('a second start cannot overwrite an unsettled payout, and the maximum pays automatically',()=>{
  const g=game(MAX);g.start(100,null,0,0);assert.throws(()=>g.start(100,2,1,0),CrashError);
  g.advance(g.at(MAX));assert.equal(g.result,'win');assert.equal(g.payout,100*MAX);
  assert.throws(()=>g.start(100,2,g.revision,0),CrashError);
});
const {Accounts}=require('../server/accounts');
const {createCrashService}=require('../server/crash/service');
test('offline auto-stop restores and credits one persisted account exactly once',()=>{
  const accounts=new Accounts();const a=accounts.ensure({id:'qa',name:'QA'});
  const g=game(3);g.start(100,2,0,Date.now()-20000);accounts.withdraw('qa',100);a.crashRound=g.snapshot();
  const messages=[];const client={user:{id:'qa'},send:s=>messages.push(s)};
  const service=createCrashService({accounts,clients:new Map(),noteWin:()=>{}});
  service.handle(client,{type:'cr_open'});service.handle(client,{type:'cr_open'});service.stop();
  assert.equal(a.balance,10100);assert.equal(a.crashRound.settled,true);
  assert.equal(messages.at(-1).payout,200);assert.equal(messages.at(-1).point,undefined);
  const again=createCrashService({accounts,clients:new Map(),noteWin:()=>{}});again.handle(client,{type:'cr_open'});again.stop();
  assert.equal(a.balance,10100);
});
test('stale start and unaffordable bet never debit the ledger',()=>{
  const accounts=new Accounts();const a=accounts.ensure({id:'qa',name:'QA'});
  const service=createCrashService({accounts,clients:new Map(),noteWin:()=>{}});
  const client={user:{id:'qa'},send(){}};
  assert.throws(()=>service.handle(client,{type:'cr_start',amount:100,autoStop:2,revision:999}),CrashError);
  assert.throws(()=>service.handle(client,{type:'cr_start',amount:100000,autoStop:2,revision:0}),CrashError);
  assert.equal(a.balance,10000);service.stop();
});
