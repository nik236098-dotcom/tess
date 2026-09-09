'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { GAMES, config, initial, start, actTower, publicState, PLINKO, KENO, TOWER, LEVELS, choose, moneyAt } = require('../server/arcade/game');
const { createArcadeService } = require('../server/arcade/service');
const { Accounts, MAX_BALANCE } = require('../server/accounts');
const OPTIONS = {plinko:{risk:'medium'},tower:{level:'easy'},keno:{picks:[1,2,3,4,5]},dragon:{side:'dragon'}};
const sequence = numbers => {let i=0;return max=>{const n=numbers[i++];assert.ok(Number.isInteger(n)&&n>=0&&n<max);return n;};};
test('invalid amounts/options and stale revisions leave every game untouched',()=>{
  for(const game of GAMES){
    const old=initial();const before=JSON.stringify(old);
    const limit=game==='tower'?config(game).maxBets.easy:config(game).maxBet;
    for(const amount of [-1,0,9,10.5,'100',NaN,Infinity,limit+1])assert.throws(()=>start(game,old,amount,OPTIONS[game],0));
    assert.throws(()=>start(game,old,100,OPTIONS[game],999));
    assert.equal(JSON.stringify(old),before);
  }
  for(const picks of [[],[1,1],[0],[41],['1'],[1.1],Array.from({length:11},(_,i)=>i+1)])assert.throws(()=>start('keno',initial(),100,{picks},0));
  for(const risk of ['__proto__','constructor','wrong',null])assert.throws(()=>start('plinko',initial(),100,{risk},0));
});
test('all Plinko paths match their destination and advertised payout',()=>{
  for(const risk of Object.keys(PLINKO))for(let bits=0;bits<1024;bits++){
    const turns=Array.from({length:10},(_,i)=>(bits>>i)&1);
    const round=start('plinko',initial(),100,{risk},0,sequence(turns));
    assert.equal(round.slot,turns.reduce((a,b)=>a+b,0));
    assert.equal(round.payout,moneyAt(100,PLINKO[risk][round.slot]));
  }
});
test('Keno draws without replacement and pays exactly the table for every hit count',()=>{
  for(let count=1;count<=10;count++)for(let hits=0;hits<=count;hits++){
    const picks=Array.from({length:count},(_,i)=>i+1);
    const wanted=[...picks.slice(0,hits),...Array.from({length:10-hits},(_,i)=>count+i+1)];
    const pool=Array.from({length:40},(_,i)=>i+1);let cursor=0;
    const rng=max=>{const j=pool.indexOf(wanted[cursor],cursor);const n=j-cursor;[pool[cursor],pool[j]]=[pool[j],pool[cursor]];cursor++;return n;};
    const round=start('keno',initial(),100,{picks},0,rng);
    assert.equal(new Set(round.drawn).size,10);assert.equal(round.hits.length,hits);
    assert.equal(round.payout,moneyAt(100,KENO[count][hits]));
  }
});
test('nine Tower floors: each difficulty has the right safe ratio, hidden future and automatic final payout',()=>{
  for(const [level,{safe,columns}] of Object.entries(LEVELS)){
    let round=start('tower',initial(),100,{level},0,()=>0);
    assert.equal(round.traps.length,9);
    assert.equal(round.traps[0].length,columns-safe);
    assert.equal(publicState('tower',round).traps,undefined);
    assert.deepEqual(publicState('tower',round).revealed,[]);
    assert.throws(()=>actTower(round,'ag_cashout',null,round.revision));
    for(let floor=0;floor<9;floor++){
      const oldRevision=round.revision;
      round=actTower(round,'ag_pick',columns-1,oldRevision);
      assert.equal(round.floor,floor+1);
      assert.equal(publicState('tower',round).revealed.length,floor+1);
      assert.throws(()=>actTower(round,'ag_pick',columns-1,oldRevision));
    }
    assert.equal(round.phase,'done');assert.equal(round.payout,moneyAt(100,TOWER[level][8]));
  }
});
test('Tower trap loses, early cashout succeeds and cannot pay twice',()=>{
  const live=start('tower',initial(),101,{level:'easy'},0,()=>0);
  const loss=actTower(live,'ag_pick',0,live.revision);assert.equal(loss.payout,0);assert.equal(loss.phase,'done');
  const step=actTower(live,'ag_pick',3,live.revision);const win=actTower(step,'ag_cashout',null,step.revision);
  assert.equal(win.payout,moneyAt(101,TOWER.easy[0]));assert.throws(()=>actTower(win,'ag_cashout',null,win.revision));
});
test('Tower accepts larger stakes by difficulty and every maximum can pay the final floor in full',()=>{
  const cfg=config('tower');
  for(const level of ['easy','medium','hard'])assert.equal(cfg.maxBets[level],100000);
  assert.ok(cfg.maxBets.expert>cfg.maxBets.master);
  for(const [level,limit] of Object.entries(cfg.maxBets)){
    let round=start('tower',initial(),limit,{level},0,()=>0);
    assert.throws(()=>start('tower',initial(),limit+1,{level},0));
    for(let i=0;i<9;i++)round=actTower(round,'ag_pick',LEVELS[level].columns-1,round.revision);
    assert.equal(round.payout,moneyAt(limit,TOWER[level][8]));
    assert.ok(Number.isSafeInteger(round.payout)&&round.payout<=MAX_BALANCE);
  }
});
test('Dragon Tiger uses eight decks, Ace low, side 2x, tie 12x and half-return on tied side',()=>{
  assert.equal(start('dragon',initial(),100,{side:'tiger'},0,sequence([0,11])).payout,200); // A versus K
  assert.equal(start('dragon',initial(),100,{side:'dragon'},0,sequence([12,0])).payout,200); // K versus 2
  for(const side of ['dragon','tiger','tie']){
    const tied=start('dragon',initial(),101,{side},0,sequence([0,51])); // same A/s from another deck
    assert.equal(tied.winner,'tie');assert.deepEqual(tied.cards[0],tied.cards[1]);
    assert.equal(tied.payout,side==='tie'?1212:50);
  }
});
test('fixed payout tables have bounded expected return; limits keep payouts safe integers',()=>{
  for(let count=1;count<=10;count++){
    const expected=KENO[count].reduce((sum,m,k)=>sum+m*choose(count,k)*choose(40-count,10-k)/choose(40,10),0);
    assert.ok(expected>.985&&expected<.995,`${count}: ${expected}`);
  }
  for(const game of GAMES)assert.ok(Number.isSafeInteger(config(game).maxBet)&&config(game).maxBet>=10);
});
test('account save/reload preserves live Tower, settled results and exactly one wallet credit',t=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'arcade-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  const file=path.join(dir,'accounts.json');let accounts=new Accounts({file});accounts.ensure({id:'a',name:'QA'});
  const messages=[];const client={user:{id:'a'},send:m=>messages.push(m)};
  let service=createArcadeService({accounts,noteWin(){},rng:()=>0});
  service.handle(client,{type:'ag_start',game:'tower',amount:100,options:{level:'easy'},revision:0});
  accounts=new Accounts({file});service=createArcadeService({accounts,noteWin(){},rng:()=>0});
  service.handle(client,{type:'ag_open',game:'tower'});assert.equal(messages.at(-1).balance,9900);
  service.handle(client,{type:'ag_pick',game:'tower',index:3,revision:1});
  service.handle(client,{type:'ag_cashout',game:'tower',revision:2});
  const done=messages.at(-1);assert.equal(done.balance,10031);
  assert.throws(()=>service.handle(client,{type:'ag_cashout',game:'tower',revision:2}));
  const again=new Accounts({file});assert.equal(again.balanceOf('a'),10031);assert.equal(again.get('a').arcadeRounds.tower.settled,true);
  assert.equal(JSON.stringify(again.list()).includes('traps'),false);
});
test('failed persistence rolls back the wallet and round before any acknowledgement',()=>{
  const accounts=new Accounts();const account=accounts.ensure({id:'a'});let notices=0;accounts.onChange=()=>notices++;
  accounts.flush=()=>{throw Error('disk full');};
  const service=createArcadeService({accounts,noteWin(){},rng:()=>0});const client={user:{id:'a'},send(){}};
  assert.throws(()=>service.handle(client,{type:'ag_start',game:'plinko',amount:100,options:{risk:'medium'},revision:0}));
  assert.equal(account.balance,10000);assert.equal(account.arcadeRounds,undefined);assert.equal(notices,0);
});
test('wallet cap keeps the complete payout pending; reopen pays exactly once after space is freed',()=>{
  const accounts=new Accounts();accounts.ensure({id:'a'});accounts.grant('a',MAX_BALANCE,'set');
  const messages=[];const client={user:{id:'a'},send:m=>messages.push(m)};
  const service=createArcadeService({accounts,noteWin(){},rng:()=>0});
  service.handle(client,{type:'ag_start',game:'plinko',amount:100,options:{risk:'high'},revision:0});
  assert.equal(messages.at(-1).settled,false);assert.equal(accounts.balanceOf('a'),MAX_BALANCE-100);
  accounts.grant('a',10000,'set');service.handle(client,{type:'ag_open',game:'plinko'});
  const paid=accounts.balanceOf('a');assert.equal(paid,10000+messages.at(-1).payout);
  service.handle(client,{type:'ag_open',game:'plinko'});assert.equal(accounts.balanceOf('a'),paid);
});
