'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const scene=require('../public/fishing-scene');
test('each server catch has its own presentation and attaches to the hook throughout the haul',()=>{
 for(const item of scene.catches){
  const info={phase:'done',detail:{prize:item.value}};
  assert.equal(scene.catchFor(info).name,item.name);
  for(let i=0;i<=1000;i++){
   const f=scene.frame(info,i/1000);
   for(const p of [f.tip,f.float,f.hook,f.fish]){assert.ok(Number.isFinite(p.x));assert.ok(Number.isFinite(p.y));}
   if(item.value&&f.attached){assert.ok(Math.abs(f.fish.x-42*f.fish.scale-f.hook.x)<1e-8);assert.equal(f.fish.y,f.hook.y);}
   if(!item.value)assert.equal(f.fish.visible,false);
  }
  assert.equal(scene.frame(info,1).complete,true);
  assert.match(scene.board(info,false),new RegExp(item.value?item.name:'Пустой заброс'));
  assert.deepEqual(scene.frame(info,2),scene.frame(info,1));
 }
});
test('cast, sink and reel endpoints are continuous and the float stays on the water until the hook reaches it',()=>{
 const info={detail:{prize:10}};
 for(const at of [.23,.53,.64,.73,.97]){
  const before=scene.frame(info,at-1e-7),after=scene.frame(info,at+1e-7);
  for(const key of ['hook','float'])assert.ok(Math.hypot(before[key].x-after[key].x,before[key].y-after[key].y)<.01,`${key} jumps at ${at}`);
 }
 for(let i=731;i<970;i++){
  const f=scene.frame(info,i/1000);
  if(f.hook.y>139)assert.equal(f.float.y,128);
 }
 assert.ok(scene.frame(info,1).hook.y<128);
});
