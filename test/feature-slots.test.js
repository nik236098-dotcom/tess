'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const F=require('../server/arcade/feature-slots'),R=require('../public/feature-slots-rules');
const G=require('../server/arcade/game');
const {createArcadeService}=require('../server/arcade/service');
function gridRng(id,grid,bonus=true){const weights=bonus?R[id].bonusWeights:R[id].baseWeights;let i=0;return size=>{const symbol=grid[i++%15],n=weights.slice(0,symbol).reduce((a,b)=>a+b,0);assert.ok(n<size);return n;};}
const plain=()=>Array.from({length:15},(_,i)=>(i%5+Math.floor(i/5)*3)%8);
const buy=id=>F.start(id,G.initial(),20,{buyBonus:true},0,n=>n-1);
for(const id of F.ids){
 test(id+': catalog, purchase, random scatter positions and valid integer payouts',()=>{
  assert.ok(G.GAMES.includes(id));assert.equal(G.config(id).buyCost,100);
  const b=buy(id);assert.equal(b.bet,2000);assert.equal(b.bonus.remaining,8);assert.equal(b.detail.grid.filter(n=>n===9).length,3);assert.equal(b.detail.win,0);assert.equal(F.evaluate(id,b.detail.grid,20).payout,0);
  const other=F.start(id,G.initial(),20,{buyBonus:true},0,()=>0);assert.notDeepEqual(other.detail.grid,b.detail.grid);
  let r=b;for(let i=0;r.phase==='play';i++){assert.ok(i<32);r=F.act(id,r,'ag_pick',0,r.revision,gridRng(id,plain()));assert.ok(Number.isSafeInteger(r.payout));}
  assert.equal(r.bonus.played,8);assert.equal(r.phase,'done');assert.throws(()=>F.act(id,r,'ag_pick',0,r.revision));
 });
 test(id+': retriggers retain feature progress and are bounded',()=>{
  let r=buy(id);const grid=plain();grid[0]=grid[1]=grid[2]=9;
  for(let i=0;i<32;i++)r=F.act(id,r,'ag_pick',0,r.revision,gridRng(id,grid));
  assert.equal(r.bonus.awarded,32);assert.equal(r.bonus.played,32);assert.equal(r.phase,'done');assert.equal(r.bonus.remaining,0);
 });
 test(id+': invalid requests, stale revisions and cross-game actions are rejected',()=>{
  const b=buy(id);assert.throws(()=>F.act(id,b,'ag_pick',0,0));assert.throws(()=>F.act(id,b,'ag_cashout',0,b.revision));assert.throws(()=>F.act(id,b,'ag_pick',1,b.revision));assert.throws(()=>F.act(id,{...b,game:'abyss'},'ag_pick',0,b.revision));
  for(const opt of [{testMax:true},{buyBonus:'yes'},null,[]])assert.throws(()=>F.start(id,G.initial(),20,opt,0));
  assert.throws(()=>F.start(id,G.initial(),21,{},0));assert.throws(()=>F.start(id,b,20,{},b.revision));
 });
 test(id+': cap, persistence, no duplicate debit or settlement, rollback on storage failure',()=>{
  const account={id:1,name:'Test',balance:10000},sent=[];
  let flushFail=false;const service=createArcadeService({accounts:{get:()=>account,flush:()=>{if(flushFail)throw Error('disk');}},noteWin(){},rng:n=>n-1});
  const client={user:{id:1},send:x=>sent.push(x)};
  service.handle(client,{type:'ag_start',game:id,amount:20,options:{buyBonus:true},revision:0});assert.equal(account.balance,8000);
  assert.throws(()=>service.handle(client,{type:'ag_start',game:id,amount:20,options:{buyBonus:true},revision:0}));assert.equal(account.balance,8000);
  const before=JSON.stringify(account);flushFail=true;assert.throws(()=>service.handle(client,{type:'ag_pick',game:id,index:0,revision:account.arcadeRounds[id].revision}));assert.equal(JSON.stringify(account),before);flushFail=false;
  // Simulate the final persisted spin at the payout limit; reconnect settles once.
  let r=account.arcadeRounds[id];r.payout=20*2500-1;r.bonus.remaining=1;
  r=F.act(id,r,'ag_pick',0,r.revision,gridRng(id,Array(15).fill(8)));assert.equal(r.payout,50000);assert.equal(r.phase,'done');account.arcadeRounds[id]=r;
  service.handle(client,{type:'ag_open',game:id});assert.equal(account.balance,58000);service.handle(client,{type:'ag_open',game:id});assert.equal(account.balance,58000);
 });
}
test('Cryo locks persist across serialization, upgrade only on Wild, cap at five and survive retriggers',()=>{
 let r=buy('cryo'),grid=plain();grid[7]=8;
 for(const factor of [1,2,3,5,5]){const old=JSON.stringify(r);const next=F.act('cryo',r,'ag_pick',0,r.revision,gridRng('cryo',grid));assert.equal(JSON.stringify(r),old);r=JSON.parse(JSON.stringify(next));assert.equal(r.bonus.locked[7],factor);}
 grid=plain();grid[0]=grid[1]=grid[2]=9;grid[7]=9;r=F.act('cryo',r,'ag_pick',0,r.revision,gridRng('cryo',grid));assert.equal(r.detail.grid[7],8);assert.equal(r.bonus.locked[7],5);assert.equal(r.detail.scatterCount,3);assert.equal(r.detail.triggered,3);
});
test('Cryo adds only participating Wild multipliers, never multiplies them together',()=>{
 const grid=plain();grid[0]=8;grid[1]=8;grid[2]=grid[3]=grid[4]=0;
 const v=F.evaluate('cryo',grid,100,{0:2,1:3,12:5});const line=v.lines.find(l=>l.line===0);assert.equal(line.factor,5);assert.equal(line.payout,100*90/20*5);
 const base=F.evaluate('cryo',grid,100);assert.equal(base.lines.find(l=>l.line===0).factor,1);
});
test('Midnight collects keys, upgrades at 3/6/9, and does not freeze Wilds',()=>{
 let r=buy('midnight');const grid=plain();grid[7]=grid[8]=grid[9]=8;
 for(const [keys,m] of [[3,2],[6,3],[9,5],[9,5]]){r=F.act('midnight',r,'ag_pick',0,r.revision,gridRng('midnight',grid));assert.equal(r.bonus.keys,keys);assert.equal(r.detail.usedMultiplier,m);assert.deepEqual(r.bonus.locked,{});}
 r=F.act('midnight',r,'ag_pick',0,r.revision,gridRng('midnight',plain()));assert.equal(r.detail.grid[7],plain()[7]);assert.equal(r.bonus.keys,9);
});
