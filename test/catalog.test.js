'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),os=require('os'),path=require('path');
const catalog=require('../server/arcade/catalog'),game=require('../server/arcade/game');
const {games,ids}=require('../public/casino-rules');const {Accounts}=require('../server/accounts');const {createArcadeService}=require('../server/arcade/service');
const opts=id=>structuredClone(games[id].defaults);
function rng(seed=47){return n=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed%n;};}
function complete(id,r,random){
 if(r.phase==='done')return r;
 if(id==='videopoker')return game.actGame(id,r,'ag_pick',[],r.revision,random);
 if(id==='scratch'){for(let i=0;i<9;i++)r=game.actGame(id,r,'ag_pick',i,r.revision,random);return r;}
 return game.actGame(id,r,'ag_cashout',null,r.revision,random);
}
test('catalog includes exactly the 16 retained additions and excludes baccarat',()=>{assert.equal(ids.length,16);assert.ok(!ids.includes('baccarat'));});
for(const id of ids)test(`${id}: validates stake/options, preserves hidden state, completes and blocks replay`,()=>{
 const random=rng(),old=game.initial();
 for(const amount of [-1,0,99,100001,1.5,NaN,'100'])assert.throws(()=>game.start(id,old,amount,opts(id),0,random));
 assert.throws(()=>game.start(id,old,100,opts(id),-1,random));assert.throws(()=>game.start(id,old,100,null,0,random));
 const round=game.start(id,old,100,opts(id),0,random),view=game.publicState(id,round);
 for(const secret of ['deck','order','prize'])if(round.phase==='play')assert.equal(view[secret],undefined);
 assert.equal(JSON.stringify(old),JSON.stringify(game.initial()));
 const done=complete(id,round,random);assert.equal(done.phase,'done');assert.ok(Number.isSafeInteger(done.payout));assert.ok(done.payout>=0);
 assert.throws(()=>game.start(id,done,100,opts(id),done.revision,random),'unpaid round cannot be replaced');
 assert.throws(()=>game.actGame(id,done,'ag_cashout',null,done.revision,random));
});
test('all invalid game-specific choices are rejected before a stake is applied',()=>{
 for(const id of ids){if(games[id].choices)assert.throws(()=>game.start(id,game.initial(),100,{side:'__proto__',level:'__proto__'},0));}
 for(const target of [1,10000.01,1.001,Infinity,NaN,'2'])assert.throws(()=>game.start('limbo',game.initial(),100,{target},0));
});
test('Diamonds exhaustively matches its seven combination payouts and expected return',()=>{
 let total=0;const counts={};for(let code=0;code<7**5;code++){let n=code;const random=max=>{assert.equal(max,7);const v=n%7;n=Math.floor(n/7);return v;};const r=game.start('diamonds',game.initial(),100,{},0,random);total+=r.payout;counts[r.multiplier]=(counts[r.multiplier]||0)+1;}
 assert.equal(counts[50],7);assert.equal(counts[5],210);assert.ok(Math.abs(total/(7**5*100)-.9829)<.0001);
});
test('Sic Bo enumerates all 216 rolls; triples never win small or big',()=>{
 const wins={small:0,big:0,triple:0};for(const side of Object.keys(wins))for(let a=0;a<6;a++)for(let b=0;b<6;b++)for(let c=0;c<6;c++){let i=0;const r=game.start('sicbo',game.initial(),100,{side},0,()=>[a,b,c][i++]);if(r.payout)wins[side]++;if(a===b&&b===c&&side!=='triple')assert.equal(r.payout,0);}
 assert.deepEqual(wins,{small:105,big:105,triple:6});
});
test('video poker recognises every payout class, including wheel and low-pair loss',()=>{
 const make=(ranks,suits='schds')=>ranks.map((rank,i)=>({rank,suit:suits[i]}));
 const fixtures=[[[10,11,12,13,14],'sssss',800],[[2,3,4,5,14],'hhhhh',60],[[9,9,9,9,3],'schds',22],[[8,8,8,2,2],'schds',9],[[2,4,6,8,10],'sssss',6],[[2,3,4,5,14],'schds',4],[[2,2,2,4,9],'schds',3],[[2,2,3,3,9],'schds',2],[[11,11,2,5,9],'schds',1],[[10,10,2,5,9],'schds',0]];
 for(const [ranks,suits,m] of fixtures)assert.equal(catalog.evaluate(make(ranks,suits))[1],m);
 for(let mask=0;mask<32;mask++){const old=game.start('videopoker',game.initial(),100,{},0,rng()),held=Array.from({length:5},(_,i)=>i).filter(i=>(mask>>i)&1);const done=game.actGame('videopoker',old,'ag_pick',held,old.revision);assert.equal(new Set(done.cards.map(c=>c.id)).size,5);for(const i of held)assert.deepEqual(done.cards[i],old.cards[i]);for(const i of [0,1,2,3,4].filter(i=>!held.includes(i)))assert.ok(!old.cards.some(c=>c.id===done.cards[i].id));}
});
test('weighted prize tables total 100% and return 98% before cent rounding',()=>{
 for(const id of ['fishing']){const table=catalog.distribution(id);assert.equal(table.reduce((s,[w])=>s+w,0),10000);assert.ok(Math.abs(table.reduce((s,[w,m])=>s+w*m,0)/10000-.98)<1e-12);}
});
test('series: every game can advance, cash out once or lose, with no future outcome disclosure',()=>{
 for(const id of ids.filter(id=>games[id].series)){
  let r=game.start(id,game.initial(),100,opts(id),0,rng());
  if(r.order)r.order[0]=1;
  const index=id==='rps'?1:id==='penalty'?1:0;
  const random=id==='pinball'?()=>1:()=>0;
  const step=game.actGame(id,r,'ag_pick',index,r.revision,random);assert.equal(step.step,1,id);
  const done=game.actGame(id,step,'ag_cashout',null,step.revision,random);assert.ok(done.payout>=100);assert.throws(()=>game.actGame(id,done,'ag_cashout',null,done.revision));
 }
 let r=game.start('rps',game.initial(),100,opts('rps'),0,()=>0);r=game.actGame('rps',r,'ag_pick',0,r.revision,()=>0);assert.equal(r.step,0);assert.equal(r.last.tie,true);assert.equal(game.actGame('rps',r,'ag_cashout',null,r.revision).payout,100);
});
test('all 16 games persist to disk and reopening never recredits their result',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'catalog-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));const file=path.join(dir,'accounts.json');
 let accounts=new Accounts({file});accounts.ensure({id:'qa'});let messages=[];const client={user:{id:'qa'},send:m=>messages.push(m)};
 for(const id of ids){let service=createArcadeService({accounts,noteWin(){},rng:rng()});const before=accounts.balanceOf('qa');service.handle(client,{type:'ag_start',game:id,amount:100,options:opts(id),revision:0});let info=messages.at(-1);
  accounts=new Accounts({file});service=createArcadeService({accounts,noteWin(){},rng:rng()});service.handle(client,{type:'ag_open',game:id});assert.equal(messages.at(-1).revision,info.revision);
  if(info.phase==='play'){if(id==='scratch'){for(let i=0;i<9;i++)service.handle(client,{type:'ag_pick',game:id,index:i,revision:messages.at(-1).revision});}else service.handle(client,{type:id==='videopoker'?'ag_pick':'ag_cashout',game:id,index:[],revision:info.revision});}
  info=messages.at(-1);assert.equal(info.phase,'done');assert.equal(info.settled,true);assert.equal(accounts.balanceOf('qa'),before-100+info.payout);
  const paid=accounts.balanceOf('qa');service.handle(client,{type:'ag_open',game:id});assert.equal(accounts.balanceOf('qa'),paid);
 }
});

test('removed games cannot start and disappear from server and browser catalogs',()=>{
 for(const id of ['cases','collection','scratch']){
  assert.ok(!ids.includes(id));assert.ok(!game.GAMES.includes(id));
  assert.throws(()=>game.start(id,game.initial(),100,{},0));
 }
});
test('retiring games refunds unfinished stakes and pays saved results once, across restarts',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'retired-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const file=path.join(dir,'accounts.json');let accounts=new Accounts({file});const user={id:'retirement'};
 const a=accounts.ensure(user);a.balance=1000;a.arcadeRounds={scratch:{phase:'play',revision:2,settled:false,bet:500},collection:{phase:'play',revision:4,settled:false,bet:300},cases:{phase:'done',revision:2,settled:false,bet:100,payout:500}};accounts.flush({strict:true});
 accounts.ensure(user);assert.equal(a.balance,2300);assert.equal(a.arcadeRounds.scratch.retired,true);
 accounts.ensure(user);assert.equal(a.balance,2300);
 accounts=new Accounts({file});assert.equal(accounts.ensure(user).balance,2300);
});
test('failed retirement persistence never credits the wallet or consumes the refund',()=>{
 const accounts=new Accounts(),user={id:'failure'},a=accounts.ensure(user);a.arcadeRounds={scratch:{phase:'play',revision:1,settled:false,bet:100}};
 const previous=a.arcadeRounds,balance=a.balance;accounts.flush=()=>{throw Error('disk failure');};
 assert.throws(()=>accounts.ensure(user));assert.equal(a.balance,balance);assert.equal(a.arcadeRounds,previous);
});
