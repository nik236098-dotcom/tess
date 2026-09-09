'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),p=require('../public/bowling-physics');
test('all outcomes start at the head pin and propagate only through actual pin contacts',()=>{
 for(let count=0;count<=10;count++){
  const t=p.timeline({detail:{count}}),hits=t.events.filter(e=>e.type==='head'||e.type==='pin'),seen=new Map();assert.equal(hits.length,count);
  if(count){assert.equal(hits[0].pin,9);assert.equal(hits[0].source,'ball');}
  for(const e of hits){if(e.source!=='ball'){assert.ok(seen.has(e.source));assert.ok(e.time>seen.get(e.source));}seen.set(e.pin,e.time);}
  assert.equal(t.frames.at(-1).pins.filter(pin=>pin.active).length,count);
 }
});
test('the ball never crosses a pin or falls through the wooden lane, for any result',()=>{
 for(let count=0;count<=10;count++)for(const f of p.timeline({detail:{count}}).frames){
  if(f.z>=p.EDGE){assert.ok(f.y>=(count?p.R:p.R-.16)-1e-8);}else assert.ok(f.y>=p.PIT+p.R-1e-8);
  for(const pin of f.pins)for(const c of p.spheres(pin))assert.ok(Math.hypot(f.x-c.x,f.y-c.y,f.z-c.z)>=p.R+c.r-.003,'ball intersects a pin');
 }
});
test('saved states and skipped frames deterministically resolve to the same final count',()=>{
 for(let count=0;count<=10;count++){const info={detail:{count}},end=p.frame(info,1);assert.deepEqual(p.frame(info,10),end);assert.deepEqual(p.frame(info,-1),p.frame(info,0));assert.equal(p.timeline(info),p.timeline(info));}
});
