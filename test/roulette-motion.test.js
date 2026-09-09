'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const View=require('../public/roulette-view');
const Server=require('../server/roulette/wheel');
const mod=n=>(n%360+360)%360;
const angleError=(a,b)=>Math.min(mod(a-b),mod(b-a));
test('visual pockets and selectable numbers match server order, colors and allowed bets',()=>{
 assert.deepEqual(View.order,Server.WHEEL_ORDER);
 for(const n of View.order)assert.equal(View.colour(n),Server.colourOf(n));
 const cells=View.cells(),numbers=cells.filter(c=>c.type==='straight');
 assert.equal(new Set(numbers.map(c=>c.value)).size,37);
 assert.equal(cells.filter(c=>c.type==='dozen').length,3);
 for(const c of cells)assert.doesNotThrow(()=>Server.normalizeBets([{type:c.type,value:c.value,amount:100}],{minBet:100,maxBet:10000,maxTotal:10000}));
 assert.deepEqual(numbers.filter(c=>c.row==='1').map(c=>c.value),[3,6,9,12,15,18,21,24,27,30,33,36]);
});
test('all 37 results settle at the center of their real pocket and continue with the rotor',()=>{
 for(const number of View.order)for(const start of [-720,0,139.42,3456]){
  const p=View.plan(number,start,78,176,()=>.37);
  assert.ok(angleError(View.sample(p,0).ball,78)<1e-8,'no starting teleport');
  assert.equal(View.sample(p,0).radius,176);
  for(const t of [.88,.9,.95,1]){const f=View.sample(p,t);assert.ok(angleError(f.ball-f.wheel,View.pocket(number))<1e-8);assert.equal(f.radius,176);}
 }
});
test('capture has continuous position and speed without frame-rate dependence',()=>{
 const p=View.plan(12,40,-123,264,()=>.5),epsilon=1e-5;
 const before=View.sample(p,p.capture-epsilon),at=View.sample(p,p.capture),after=View.sample(p,p.capture+epsilon);
 assert.ok(Math.abs((at.ball-before.ball)/epsilon-(after.ball-at.ball)/epsilon)<.1);
 assert.ok(Math.abs(at.radius-before.radius)<1e-7);
 for(const fps of [30,60,120]){
  let pose;for(let i=0;i<=fps*8;i++)pose=View.sample(p,i/(fps*8));
  assert.deepEqual(pose,View.sample(p,1));
 }
 for(let i=0;i<=1000;i++){const f=View.sample(p,i/1000);assert.ok(Number.isFinite(f.ball));assert.ok(f.radius>=176&&f.radius<=265);}
});
