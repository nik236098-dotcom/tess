'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),physics=require('../public/bowling-physics'),audio=require('../public/bowling-audio');
function harness(saved){
 const starts=[],stops=[],writes=[],listeners={},param=()=>({value:0,setTargetAtTime(){}});let resumes=0;
 class Context{constructor(){this.state='suspended';this.currentTime=0;this.sampleRate=12000;this.destination={};}resume(){this.state='running';resumes++;return Promise.resolve();}createGain(){return {gain:param(),connect(){},disconnect(){}};}createBiquadFilter(){return {frequency:param(),connect(){},disconnect(){}};}createBuffer(_,size){return {getChannelData:()=>new Float32Array(size)};}createBufferSource(){const source={loop:false,playbackRate:param(),connect(){},disconnect(){},start(){starts.push(source);},stop(){stops.push(source);}};return source;}}
 const env={AudioContext:Context,BowlingPhysics:physics,document:{hidden:false,addEventListener:(k,f)=>listeners[k]=f},localStorage:{getItem:()=>saved,setItem:(k,v)=>writes.push([k,v])}};
 return {env,starts,stops,writes,listeners,resumes:()=>resumes,a:audio.create(env)};
}
const strike={detail:{count:10}};
test('rolling begins only after unlock and impacts follow the contact timeline exactly once',()=>{
 const h=harness();h.a.begin(strike);h.a.frame(.04);assert.equal(h.starts.length,0);
 h.a.unlock();assert.equal(h.resumes(),1);h.a.begin(strike);
 const events=physics.timeline(strike).events;
 for(let i=0;i<=552;i++)h.a.frame(i/552);
 assert.ok(h.starts.some(s=>s.loop));assert.equal(h.starts.filter(s=>!s.loop).length,events.length);
 const total=h.starts.length;h.a.frame(1);assert.equal(h.starts.length,total);assert.ok(h.stops.includes(h.starts.find(s=>s.loop)));
});
test('mute, tab hiding and leaving stop all audio without a late replay',()=>{
 const h=harness();h.a.unlock();h.a.begin(strike);h.a.frame(.1);const roll=h.starts[0];assert.ok(roll.loop);
 h.env.document.hidden=true;h.listeners.visibilitychange();assert.ok(h.stops.includes(roll));const total=h.starts.length;
 h.env.document.hidden=false;h.a.frame(.5);assert.equal(h.starts.length,total);
 h.a.toggle();assert.equal(h.writes.at(-1)[1],'off');h.a.begin(strike);h.a.frame(.5);assert.equal(h.starts.length,total);
 h.a.toggle();h.a.begin(strike);h.a.frame(.1);h.a.stop();const stopped=h.starts.length;h.a.frame(.5);assert.equal(h.starts.length,stopped);
});
test('reduced motion gives one short impact; a delayed normal frame never dumps old contacts',()=>{
 const h=harness();h.a.unlock();h.a.begin(strike,true);h.a.frame(1);h.a.frame(1);assert.equal(h.starts.length,1);assert.equal(h.starts[0].loop,false);
 h.a.begin(strike);h.a.frame(1);assert.equal(h.starts.length,1);
 const empty=harness();empty.a.unlock();empty.a.begin({detail:{count:0}},true);empty.a.frame(1);assert.equal(empty.starts.length,0);
});
test('generated sound buffers are finite and bounded; unsupported audio is harmless',()=>{
 for(const kind of ['roll','head','pin','land']){const data=audio.samples(kind,12000);assert.ok(data.length>1000);assert.ok(data.every(n=>Number.isFinite(n)&&Math.abs(n)<1.4));}
 const a=audio.create({BowlingPhysics:physics});assert.doesNotThrow(()=>{a.unlock();a.begin(strike);a.frame(.5);a.stop();});
});
