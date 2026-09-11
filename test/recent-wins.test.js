'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {RecentWins}=require('../server/recent-wins');
function file(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'croco-live-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return path.join(dir,'recent-wins.json');}
test('Live survives reconstruction with exact order, timestamps, payout and multiplier; only newest 12 remain',t=>{
 const f=file(t),feed=new RecentWins({file:f});
 for(let i=0;i<15;i++)feed.add({name:'Player '+i,game:'mines',amount:150,bet:100,payout:250});
 const restored=new RecentWins({file:f});assert.deepEqual(restored.entries,feed.entries);assert.equal(restored.entries.length,12);assert.equal(restored.entries[0].name,'Player 14');assert.equal(restored.entries[0].multiplier,2.5);assert.equal(fs.existsSync(f+'.tmp'),false);
});
test('failed feed write leaves settled in-memory win available and previous file intact',t=>{
 const f=file(t),errors=[],feed=new RecentWins({file:f,log:(...args)=>errors.push(args)});
 feed.add({name:'First',game:'mines',amount:100});const saved=fs.readFileSync(f,'utf8');fs.mkdirSync(f+'.tmp');
 assert.doesNotThrow(()=>feed.add({name:'Second',game:'crash',amount:200}));assert.equal(feed.entries[0].name,'Second');assert.equal(fs.readFileSync(f,'utf8'),saved);assert.equal(errors.length,1);
});
test('absent or malformed file does not prevent startup; invalid wins are ignored',t=>{
 const f=file(t);assert.deepEqual(new RecentWins({file:f}).entries,[]);fs.writeFileSync(f,'{');let logged=false;
 const feed=new RecentWins({file:f,log:()=>{logged=true;}});assert.ok(logged);feed.add({amount:NaN});feed.add({amount:0});assert.deepEqual(feed.entries,[]);
});
