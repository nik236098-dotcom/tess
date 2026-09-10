'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const race=require('../public/race-scene'),renderer=require('../public/race-renderer');
const permutations=a=>a.length?a.flatMap((v,i)=>permutations(a.filter((_,j)=>i!==j)).map(rest=>[v,...rest])):[[]];
test('3D tyre rotation follows ground distance and the actual finish plane preserves every server order',()=>{
 for(const order of permutations([0,1,2,3])){
  const crossed=new Set();
  for(let step=0;step<=400;step++){
   const f=race.frame({detail:{order}},step/400);
   for(let i=0;i<4;i++){
    const m=renderer.motion(f,i),g=renderer.geometry;
    assert.ok(Math.abs(m.wheelAngle*g.wheelRadius+m.travel)<1e-10,'tyres must roll without slipping');
    const finished=m.z-g.nose<=g.finish;
    assert.equal(finished,f.cars[i].finished,'rendered nose and server timeline must cross together');
    if(finished)crossed.add(i);
   }
  }
  assert.deepEqual([...crossed],order);
 }
});
test('cars accelerate and brake; wheels and suspension settle at both ends of a race',()=>{
 const info={detail:{order:[3,1,2,0]}};
 for(const t of [0,.1,.19,1]){
  const f=race.frame(info,t);for(let i=0;i<4;i++){const m=renderer.motion(f,i);assert.equal(f.cars[i].speed,0);assert.equal(Math.abs(m.heave),0);assert.equal(Math.abs(m.pitch),0);assert.equal(Math.abs(m.roll),0);}
 }
 const early=race.frame(info,.35),late=race.frame(info,.96);
 assert.ok(early.cars.every(c=>c.speed>0&&c.acceleration>0));
 assert.ok(late.cars.every(c=>c.speed>0&&c.acceleration<0));
 assert.ok(late.cars.every((_,i)=>renderer.motion(late,i).braking));
 for(let step=0;step<=1000;step++){const f=race.frame(info,step/1000);for(let i=0;i<4;i++)if(renderer.motion(f,i).braking)assert.ok(f.cars[i].finished,'braking starts after the finish');}
});
