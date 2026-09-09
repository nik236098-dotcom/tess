'use strict';
// The server owns the outcome. This shared geometry animates its ten decisions
// with gravity between surface contacts; it never rolls a second result.
(function(root) {
  const geometry = Object.freeze({ width:360, height:350, rows:10, spacing:28, rowGap:23,
    center:180, firstY:48, startY:16, pinRadius:3, ballRadius:5.5, pocketTop:285, pocketFloor:316 });
  const g=geometry, contact=g.pinRadius+g.ballRadius;
  const slotX=slot=>g.center+(slot-g.rows/2)*g.spacing;
  const restY=g.pocketFloor-g.ballRadius;
  const pins=[];
  for(let row=0;row<g.rows;row++)for(let col=-1;col<=row+1;col++)
    pins.push({x:g.center+(col-row/2)*g.spacing,y:g.firstY+row*g.rowGap,row,col});

  function create(path) {
    if(!Array.isArray(path)||path.length!==g.rows||path.some(n=>n!==0&&n!==1))throw new Error('Invalid Plinko path');
    const segments=[], impacts=[]; let time=0, x=g.center, y=g.startY;
    const add=(seconds,data)=>{segments.push({start:time,seconds,x,y,...data});time+=seconds;};
    const initialDrop=g.firstY-contact-y, intro=.38;
    add(intro,{kind:'flight',vx:0,vy:0,gravity:2*initialDrop/intro**2});
    y=g.firstY-contact;
    let downwardSpeed=0;
    for(let row=0;row<path.length;row++) {
      const pin={x,y:y+contact}; impacts.push({time,x:pin.x,y:pin.y});
      // A short upward rebound, then an accelerating fall to the next peg's top.
      const gravity=1100, vy=-(135+(row%3)*5);
      const seconds=(-vy+Math.sqrt(vy**2+2*gravity*g.rowGap))/gravity;
      const dx=path[row]?g.spacing/2:-g.spacing/2;
      add(seconds,{kind:'flight',vx:dx/seconds,vy,gravity,pin});
      x+=dx; y+=g.rowGap; downwardSpeed=vy+gravity*seconds;
    }
    // Last rebound passes the final row, then drops through the pocket opening.
    const gravity=1100, drop=restY-y;
    const seconds=(-downwardSpeed+Math.sqrt(downwardSpeed**2+2*gravity*drop))/gravity;
    add(seconds,{kind:'flight',vx:0,vy:downwardSpeed,gravity});
    y=restY;
    const landedAt=time;
    add(.22,{kind:'settle',height:2.4});
    return {segments,impacts,duration:time*1000,landedAt:landedAt*1000,slot:path.reduce((a,b)=>a+b,0)};
  }
  function sample(motion,elapsed) {
    const seconds=Math.max(0,elapsed)/1000;
    if(elapsed>=motion.duration)return {x:slotX(motion.slot),y:restY,landed:true,done:true,impact:null};
    const segment=motion.segments.find(s=>seconds<s.start+s.seconds)||motion.segments.at(-1);
    const t=Math.min(segment.seconds,Math.max(0,seconds-segment.start));
    const impact=motion.impacts.find(p=>seconds>=p.time&&seconds-p.time<.13);
    return {x:segment.x+(segment.vx||0)*t,
      y:segment.kind==='settle'?restY-segment.height*Math.sin(Math.PI*t/segment.seconds):segment.y+segment.vy*t+segment.gravity*t*t/2,
      landed:elapsed>=motion.landedAt,done:false,
      impact:impact?{x:impact.x,y:impact.y,strength:1-(seconds-impact.time)/.13}:null};
  }
  const api={geometry,pins,slotX,restY,create,sample};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.PlinkoMotion=api;
})(globalThis);
