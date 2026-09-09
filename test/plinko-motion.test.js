'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const motion=require('../public/plinko-motion');
const {geometry:g,pins,create,sample,slotX,restY}=motion;
test('all 1024 Plinko paths clear every peg and settle fully inside the server-selected pocket',()=>{
  const radius=g.ballRadius+g.pinRadius;
  for(let bits=0;bits<1024;bits++) {
    const path=Array.from({length:10},(_,i)=>(bits>>i)&1), m=create(path);
    assert.ok(m.duration>=4000&&m.duration<=5000);
    for(let t=0;t<m.duration;t+=8){
      const ball=sample(m,t);
      for(const pin of pins){
        const dx=ball.x-pin.x,dy=ball.y-pin.y;
        assert.ok(dx*dx+dy*dy>=radius*radius-1e-8,`overlap: path ${bits} at ${t}ms`);
      }
      if(ball.y+g.ballRadius>=g.pocketTop){
        assert.ok(Math.abs(ball.x-slotX(m.slot))+g.ballRadius<12);
        assert.ok(ball.y+g.ballRadius<=g.pocketFloor+1e-8);
      }
    }
    const end=sample(m,m.duration);
    assert.equal(end.x,slotX(path.reduce((a,b)=>a+b,0)));
    assert.equal(end.y,restY);assert.ok(end.landed&&end.done);
    assert.ok(end.y-g.ballRadius>g.pocketTop);
  }
});
test('each of ten peg contacts changes downward movement into an upward rebound without a jump',()=>{
  const m=create([0,1,1,0,0,1,0,1,0,1]);
  assert.equal(m.impacts.length,10);
  for(const impact of m.impacts){
    const t=impact.time*1000, before=sample(m,t-.01), at=sample(m,t), after=sample(m,t+.01);
    assert.ok(before.y<at.y&&after.y<at.y);
    assert.ok(Math.hypot(after.x-before.x,after.y-before.y)<.01);
    assert.ok(Math.abs(Math.hypot(at.x-impact.x,at.y-impact.y)-(g.pinRadius+g.ballRadius))<1e-8);
  }
  const first=sample(m,100), later=sample(m,200), latest=sample(m,300);
  assert.ok(latest.y-later.y>later.y-first.y,'initial fall accelerates');
});
