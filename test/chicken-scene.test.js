'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const scene=require('../public/chicken-scene'),catalog=require('../server/arcade/catalog');
test('Chicken camera follows every possible lane, including the end and a failed attempt',()=>{
 for(const level of ['easy','medium','hard']){
  const coefficients=catalog.coefficients('chicken',{level});
  for(let step=0;step<coefficients.length;step++)for(const safe of [true,false]){
   const info={step:step+(safe?1:0),coefficients,last:{safe}},previous={step};let x=-Infinity;
   for(let i=0;i<=100;i++){
    const f=scene.pose(info,previous,i/100);
    assert.ok(f.x>=x-1e-8);x=f.x;
    assert.ok(f.x>=28&&f.x<=328.001);
    assert.ok(f.camera>=1&&f.camera<=coefficients.length-4);
    for(const value of Object.values(f))if(typeof value==='number')assert.ok(Number.isFinite(value));
   }
   const final=scene.pose(info,null,1);
   assert.equal(final.x,scene.laneX(final.target,final.camera));
   assert.match(scene.scene(info),new RegExp(`data-ch-lane="${final.target}"`));
  }
 }
});
test('Chicken alternates jointed legs and always has a planted foot while walking',()=>{
 const previous={step:2},info={step:3,last:{safe:true}},near=new Set(),far=new Set();
 for(let i=0;i<=100;i++){
  const f=scene.pose(info,previous,i/100);near.add(scene.legPath(f.near,true));far.add(scene.legPath(f.far,false));
  assert.ok(f.near.y<=0&&f.far.y<=0);
  assert.ok(f.near.y===0||f.far.y===0,'one foot must remain grounded');
 }
 assert.ok(near.size>30&&far.size>30,'both joint chains articulate');
 const end=scene.pose(info,previous,1);assert.equal(end.bodyY,0);assert.equal(end.wing,0);assert.equal(end.near.y,0);assert.equal(end.far.y,0);
});
test('Front-facing traffic clears a successful crossing and meets the chicken only on a server loss',()=>{
 for(const safe of [true,false]){
  const info={step:safe?3:2,last:{safe}},previous={step:2};
  for(let i=0;i<=100;i++){
   const f=scene.pose(info,previous,i/100);
   if(safe&&f.carY>113&&f.carY<193)assert.ok(Math.abs(f.carX-f.x)>30);
   assert.equal(f.impact,!safe&&i/100>=.79);
  }
 }
 const hit=scene.pose({step:2,last:{safe:false}},{step:2},.79);
 assert.equal(hit.x,hit.carX);assert.equal(hit.carY,170);
 assert.ok(scene.pose({step:3,last:{safe:true}},{step:2},.4).carScale>scene.pose({step:3,last:{safe:true}},{step:2},.1).carScale);
 assert.equal(scene.pose({},null,1).impact,false);
});
