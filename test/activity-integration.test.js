'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const { once } = require('node:events');
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const { createApp } = require('../server');
async function client(server, name = 'player') {
  const ws = new WebSocket(`ws://127.0.0.1:${server.address().port}/ws`), inbox = [], waiting = [];
  ws.addEventListener('message', event => { const m=JSON.parse(event.data); const i=waiting.findIndex(w=>w.match(m)); if(i<0)inbox.push(m);else waiting.splice(i,1)[0].resolve(m); });
  const wait = match => { const i=inbox.findIndex(match);if(i>=0)return Promise.resolve(inbox.splice(i,1)[0]);return new Promise((resolve,reject)=>{const w={match,resolve:m=>{clearTimeout(timer);resolve(m);}};waiting.push(w);const timer=setTimeout(()=>reject(Error('Missing server response')),3000);timer.unref();}); };
  await once(ws,'open');const send=m=>ws.send(JSON.stringify(m));send({type:'auth',devId:name,name});await wait(m=>m.type==='auth_ok');
  return {ws,send,wait};
}
async function server(file=null) { const s=createApp({botToken:'',botRuntime:false,devLogin:true,devAdmin:false,adminIds:['dev:admin'],accountsFile:file,paymentsFile:null,promoFile:null});await new Promise(r=>s.listen(0,'127.0.0.1',r));return s; }
test('real WebSocket: own complete bet history, other IDs ignored, private slots rejected and absent from Live', {timeout:10000}, async t=>{
  const s=await server();t.after(()=>s.shutdown());const a=await client(s),admin=await client(s,'admin');
  t.after(()=>{a.ws.close();admin.ws.close();});
  for(const game of ['abyss','cryo','midnight']){a.send({type:'ag_open',game});assert.match((await a.wait(m=>m.type==='error')).message,/администратору/);admin.send({type:'ag_open',game});assert.equal((await admin.wait(m=>m.type==='ag')).game,game);}
  a.send({type:'nv_bet',amount:100,target:75,mode:'under'});const nv=await a.wait(m=>m.type==='nv');assert.ok(nv.round);
  a.send({type:'game_history',userId:'dev:admin'});const history=await a.wait(m=>m.type==='game_history');assert.equal(history.rows.length,1);assert.equal(history.rows[0].userId,'dev:player');assert.equal(history.rows[0].bet,100);
  admin.send({type:'game_history',userId:'dev:player'});assert.equal((await admin.wait(m=>m.type==='game_history')).rows.length,0);
  a.send({type:'referral_claim'});assert.match((await a.wait(m=>m.type==='error')).message,/Нет доступных/);
});
test('Mines active stake and private layout survive restart; finished result is recorded exactly once', {timeout:10000},async t=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'croco-resume-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));const file=path.join(dir,'accounts.json');
  let s=await server(file),a=await client(s);a.send({type:'mn_start',amount:100,mines:3});const started=await a.wait(m=>m.type==='mn');assert.equal(started.phase,'play');
  const saved=s.accounts.get('dev:player').minesRound;assert.equal(saved.phase,'play');const cell=saved.layout.$set[0];const balance=s.accounts.get('dev:player').balance;
  a.ws.close();await s.shutdown();s=await server(file);t.after(()=>s.shutdown());a=await client(s);t.after(()=>a.ws.close());
  a.send({type:'mn_open'});assert.equal((await a.wait(m=>m.type==='mn')).phase,'play');assert.equal(s.accounts.get('dev:player').balance,balance);
  a.send({type:'mn_pick',index:cell});assert.equal((await a.wait(m=>m.type==='mn')).phase,'done');
  a.send({type:'game_history'});const h=await a.wait(m=>m.type==='game_history');assert.equal(h.rows.length,1);assert.equal(h.rows[0].payout,0);
  a.send({type:'mn_pick',index:cell});await a.wait(m=>m.type==='error');assert.equal(s.activity.history('dev:player').total,1);
});

test('wallet restores only the signed-in players invoice and payout', async t => {
  const s = await server(); t.after(() => s.shutdown());
  const now = Date.now();
  for (const userId of ['dev:player', 'dev:other']) {
    s.payments.invoices.set(userId, { id: userId, userId, provider: 'cryptobot', status: 'pending', amount: 25, cents: 2500, currency: 'USDT', createdAt: now, expiresAt: now + 10000 });
    s.payments.payouts.set(userId, { id: userId, userId, provider: 'cryptobot', status: 'review', cents: 1000, amount: 10, currency: 'USDT', createdAt: now });
  }
  const a = await client(s); t.after(() => a.ws.close());
  const wallet = await a.wait(m => m.type === 'wallet_state');
  assert.equal(wallet.invoice.id, 'dev:player'); assert.equal(wallet.payout.id, 'dev:player');
});
