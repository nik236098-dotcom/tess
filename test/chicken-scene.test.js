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
    assert.ok(f.x>=80&&f.x<=182.001);
    assert.ok(f.camera>=0&&f.camera<=scene.cameraAt(coefficients.length));
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
   if(safe&&f.carY>155&&f.carY<235)assert.ok(Math.abs(f.carX-f.x)>30);
   assert.equal(f.impact,!safe&&i/100>=.79);
  }
 }
 const hit=scene.pose({step:2,last:{safe:false}},{step:2},.79);
 assert.equal(hit.x,hit.carX);assert.equal(hit.carY,198);
 assert.ok(scene.pose({step:3,last:{safe:true}},{step:2},.4).carScale>scene.pose({step:3,last:{safe:true}},{step:2},.1).carScale);
 assert.equal(scene.pose({},null,1).impact,false);
});
test('Sidewalk is the starting point; after it the world scrolls by exactly one lane per step',()=>{
 assert.equal(scene.pose({step:0},null,1).x,80);
 for(let step=1;step<=19;step++){
  const from=scene.pose({step:step+1,last:{safe:true}},{step},0),to=scene.pose({step:step+1,last:{safe:true}},{step},1);
  assert.equal(to.camera-from.camera,108);
  assert.equal(to.x,from.x);
  assert.equal((to.x+to.camera)-(from.x+from.camera),108,'the feet advance in world coordinates');
 }
});
test('Completed lanes get barriers and a failed attempt never receives a successful highlight',()=>{
 for(let step=0;step<=20;step++){
  const coefficients=catalog.coefficients('chicken',{level:'easy'});
  const html=scene.scene({step,coefficients,last:{safe:true}});
  for(const [,index,attrs] of html.matchAll(/data-ch-barrier="(\d+)"([^>]*)/g))assert.equal(!attrs.includes('display="none"'),Number(index)<=step);
  assert.equal(scene.laneState(step+1,{step,last:{safe:false}}),'is-failed');
  if(step)assert.equal(scene.laneState(step,{step,last:{safe:false}}),'is-passed');
  assert.equal(scene.laneState(step+1,{step,last:{safe:false}},false),'');
 }
});
test('Loss finishes with a fallen visible chicken; barrier and lane labels reveal together after a safe step',()=>{
 const nodes=new Map();const get=key=>{if(!nodes.has(key))nodes.set(key,{dataset:{},attrs:{},setAttribute(k,v){this.attrs[k]=v;}});return nodes.get(key);};
 const barrier=get('barrier');barrier.dataset.chBarrier='2';const lane=get('lane');lane.dataset.chLane='2';
 const host={querySelector:get,querySelectorAll:s=>s==='[data-ch-barrier]'?[barrier]:s==='[data-ch-lane]'?[lane]:[]};
 const safe={step:2,last:{safe:true}};
 scene.paint(host,safe,{step:1},.5,true);assert.equal(barrier.attrs.display,'none');assert.ok(!lane.attrs.class.includes('is-current'));
 scene.paint(host,safe,{step:1},1,true);assert.equal(barrier.attrs.display,'inline');assert.match(lane.attrs.class,/is-current/);
 const loss={step:1,last:{safe:false}};
 scene.paint(host,loss,{step:1},1,false);assert.equal(barrier.attrs.display,'none');assert.match(lane.attrs.class,/is-failed/);
 assert.match(get('[data-chicken]').attrs.transform,/rotate\(76\)/);
 assert.equal(get('[data-ch-eye-loss]').attrs.display,'inline');assert.equal(get('[data-ch-eye]').attrs.display,'none');
 assert.equal(get('[data-ch-crossing-car]').attrs.display,'none');
});
