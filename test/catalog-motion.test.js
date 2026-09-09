'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const motion=require('../public/casino-motion');
const {ids,games}=require('../public/casino-rules');
const engine=require('../server/arcade/game');
test('every retained game has a bounded timeline, finite frames and exact completion',()=>{
 for(const id of ids){
  let r=engine.start(id,engine.initial(),100,structuredClone(games[id].defaults),0,n=>n-1);
  if(games[id].series)r=engine.actGame(id,r,'ag_pick',0,r.revision,n=>n-1);
  const info=engine.publicState(id,r);
  assert.ok(motion.duration(id,info)>=1000&&motion.duration(id,info)<=6500,id);
  const finite=x=>{if(typeof x==='number')assert.ok(Number.isFinite(x),id);else if(x&&typeof x==='object')Object.values(x).forEach(finite);};
  for(let i=0;i<=100;i++)finite(motion.frame(id,info,null,i/100));
  assert.deepEqual(motion.frame(id,info,null,3),motion.frame(id,info,null,1));
 }
});
test('slots travel continuously forward and stop exactly on the server result, in column order',()=>{
 let previous=[0,0,0];
 for(let i=0;i<=100;i++){
  const f=motion.frame('slots',{},null,i/100);
  f.reels.forEach((r,c)=>{assert.ok(r.position>=previous[c]-1e-9);assert.ok(r.position<=18);previous[c]=r.position;});
 }
 assert.deepEqual(previous,[18,18,18]);
 assert.deepEqual(motion.frame('slots',{},null,.75).reels.map(r=>r.settled),[true,false,false]);
 assert.deepEqual(motion.frame('slots',{},null,.9).reels.map(r=>r.settled),[true,true,false]);
});
test('held video cards never flip or move during an exchange',()=>{
 for(let i=0;i<=50;i++)for(const slot of [1,4])assert.deepEqual(motion.frame('videopoker',{phase:'done',held:[1,4]},null,i/50).cards[slot],{flip:180,y:0});
});
test('bowling collision happens before pins fall, and standing pins stay upright',()=>{
 const info={detail:{fallen:[true,false,true,false,false,false,false,false,false,false]}};
 assert.equal(motion.frame('bowling',info,null,.5).pins[0].fall,0);
 const end=motion.frame('bowling',info,null,1);assert.equal(end.pins[0].fall,1);assert.equal(end.pins[1].fall,0);assert.equal(end.y,20);
});
test('pinball paths stay outside all bumper interiors and reach the selected bumper surface',()=>{
 for(let choice=0;choice<2;choice++)for(let bumper=0;bumper<3;bumper++)for(const safe of [true,false]){
  const info={last:{choice,bumper,safe}};
  let contact=false;
  for(let i=0;i<=1000;i++){
   const f=motion.frame('pinball',info,null,i/1000);
   for(const [x,y] of motion.bumpers)assert.ok(Math.hypot(f.x-x,f.y-y)>=10.4,`path intersects bumper: ${choice}/${bumper}/${i}`);
   contact ||= f.impact;
  }
  assert.ok(contact);
  assert.equal(motion.frame('pinball',info,null,1).y,safe?86:106);
 }
});
test('Andar reveals every card in order and finishes with the matching card',()=>{
 const info={detail:{dealt:Array.from({length:37},(_,i)=>({id:i}))}};
 let last=0;for(let i=0;i<=1000;i++){const f=motion.frame('andar',info,null,i/1000);assert.ok(f.count>=last);assert.ok(f.count<=37);last=f.count;}
 assert.equal(last,37);
});
