'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const rules=require('../public/darts-rules');
const motion=require('../public/casino-motion'),scene=require('../public/darts-scene'),audio=require('../public/darts-audio'),engine=require('../server/arcade/game');

test('dart tip reaches the server point and remains anchored throughout the impact wobble',()=>{
 for(const area of [0,.009999,.01,.089999,.09,.359999,.36,.999999])for(let i=0;i<24;i++){
  const angle=i/24*Math.PI*2,info={detail:{radius:Math.sqrt(area),angle}};
  const end=motion.frame('darts',info,null,1);
  assert.ok(Math.abs(end.x-(150+119*Math.sqrt(area)*Math.sin(angle)))<1e-9);
  assert.ok(Math.abs(end.y-(151-119*Math.sqrt(area)*Math.cos(angle)))<1e-9);
  for(let t=motion.dartsTiming.impact;t<=1;t+=.01){const f=motion.frame('darts',info,null,t);assert.equal(f.x,end.x);assert.equal(f.y,end.y);assert.equal(f.scale,.72);assert.equal(f.hit,true);}
  assert.equal(motion.frame('darts',info,null,motion.dartsTiming.launch-.01).opacity,0);
  // Settled fins remain above the payout row and left of the history column.
  const radians=end.rotation*Math.PI/180;
  for(const [x,y]of [[0,0],[31,61],[43,60],[48,49],[54,61]]){
   const px=end.x+.72*(x*Math.cos(radians)-y*Math.sin(radians)),py=end.y+.72*(x*Math.sin(radians)+y*Math.cos(radians));
   assert.ok(px>12&&px<292&&py>18&&py<328,`${px}/${py}`);
  }
 }
});
test('radial zones keep all six Medium payouts, expected areas and exact boundaries',()=>{
 const expected=[.4,.6,1.3,3.1,6,16];assert.deepEqual(scene.zones.map(z=>z.value),expected);
 const counts=expected.map(()=>0);let total=0;
 for(let i=0;i<1200;i++){const m=rules.outcome((i+.5)/1200);counts[expected.indexOf(m)]++;total+=m;}
 assert.deepEqual(counts,[663,345,90,50,40,12]);assert.ok(Math.abs(total/1200-.9801666666666666)<1e-12);
 const range=2**32;
 for(const threshold of [0,12/1200,52/1200,102/1200,192/1200,537/1200,1])for(const offset of [-1,0,1]){
  const sample=Math.floor(threshold*range)+offset;if(sample<0||sample>=range)continue;
  let i=0;const r=engine.start('darts',engine.initial(),999,{},0,()=>i++?0:sample);
  assert.equal(r.multiplier,rules.outcome(sample/range));assert.equal(r.payout,Math.floor(999*Math.round(r.multiplier*100)/100));
  assert.equal(r.detail.rules,rules.version);
 }
 assert.throws(()=>rules.outcome(1));assert.throws(()=>rules.outcome(NaN));
 assert.equal(scene.label(16),'16×');assert.equal(scene.label(.4),'0,4×');
 const html=scene.svg({phase:'done',multiplier:6,history:[{multiplier:6},{multiplier:16},{multiplier:1.3},{multiplier:.4}]});
 assert.ok(html.includes('data-dt-dart'));assert.ok(!html.includes('objects.webp'));
});
test('an old saved payout is never reinterpreted as a hit on the new target',()=>{
 let writes=0;const stage={querySelector:()=>({setAttribute(){writes++;}})};
 scene.paint(stage,motion.frame('darts',{detail:{radius:.2,angle:0}},null,1),{detail:{radius:.2,angle:0},multiplier:5});
 assert.equal(writes,0);
});

function audioEnv(saved){
 const starts=[],stops=[],writes=[],env={document:{hidden:false},CasinoMotion:motion,localStorage:{getItem:()=>saved,setItem:(k,v)=>writes.push([k,v])}};
 let resumes=0;
 class Context{
  constructor(){this.state='suspended';this.currentTime=0;this.sampleRate=44100;this.destination={};}
  resume(){resumes++;this.state='running';return Promise.resolve();}
  createBuffer(channels,size){return {getChannelData:()=>new Float32Array(size)};}
  createBufferSource(){return {connect(){},disconnect(){},start:time=>starts.push(time),stop:time=>stops.push(time)};}
  createBiquadFilter(){return {Q:{},frequency:{setValueAtTime(){},exponentialRampToValueAtTime(){}},connect(){},disconnect(){}};}
  createGain(){return {gain:{setValueAtTime(){},exponentialRampToValueAtTime(){}},connect(){},disconnect(){}};}
 }
 env.AudioContext=Context;return {env,starts,stops,writes,resumes:()=>resumes};
}
test('audio unlocks on gesture; throw and impact sound once each at the animation events',()=>{
 const h=audioEnv(),a=audio.create(h.env);a.begin(1);a.frame(.2);assert.equal(h.starts.length,0);
 a.unlock();assert.equal(h.resumes(),1);a.begin(2);
 for(const t of [0,.1,.119])a.frame(t);assert.equal(h.starts.length,0);
 for(const t of [.12,.3,.5,.639])a.frame(t);assert.equal(h.starts.length,1);
 for(const t of [.64,.7,.8,1,1])a.frame(t);assert.equal(h.starts.length,2);
 a.stop();a.frame(1);assert.equal(h.starts.length,2);
});
test('muting is persistent; hidden tabs and absent audio support cannot make a late sound',()=>{
 const h=audioEnv('off'),a=audio.create(h.env);a.unlock();assert.equal(h.resumes(),0);
 a.begin(1);a.frame(.2);assert.equal(h.starts.length,0);
 assert.equal(a.toggle(),true);assert.equal(h.writes.at(-1)[1],'on');a.begin(2);h.env.document.hidden=true;a.frame(.2);a.frame(1);
 h.env.document.hidden=false;a.frame(1);assert.equal(h.starts.length,0);
 a.begin(3);a.frame(.2);assert.equal(h.starts.length,1);a.toggle();a.frame(1);assert.equal(h.starts.length,1);assert.equal(h.writes.at(-1)[1],'off');
 const unsupported=audio.create({});assert.doesNotThrow(()=>{unsupported.unlock();unsupported.begin(1);unsupported.frame(1);unsupported.stop();});
});
test('reduced motion and a delayed frame play only the hit, never a simultaneous whoosh',()=>{
 for(const reduced of [false,true]){const h=audioEnv(),a=audio.create(h.env);a.unlock();a.begin(1,reduced);a.frame(1);a.frame(1);assert.equal(h.starts.length,1);}
});

test('four overlapping audio channels keep their own throw and impact events',()=>{
 const h=audioEnv(),a=audio.create(h.env);a.unlock();const channels=Array.from({length:4},()=>a.channel());
 for(const c of channels)c.frame(.12);assert.equal(h.starts.length,4);
 for(const c of channels){c.frame(.4);c.frame(.64);c.frame(1);}assert.equal(h.starts.length,8);
});
