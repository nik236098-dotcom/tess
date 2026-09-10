'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),{create}=require('../public/abyss-audio');
function harness(){
 const nodes=[],intervals=new Map(),storage=new Map();let next=1,context;
 const param=()=>({value:0,setValueAtTime(){},linearRampToValueAtTime(){},exponentialRampToValueAtTime(){}});
 function node(source=false){const n={gain:param(),frequency:param(),Q:param(),delayTime:param(),threshold:param(),knee:param(),ratio:param(),connect(){},disconnect(){},start(){this.started=true;},stop(at){this.stoppedAt=at??0;}};if(source)nodes.push(n);return n;}
 class AudioContext{constructor(){context=this;this.currentTime=0;this.state='running';this.sampleRate=1000;this.destination={};}createGain(){return node();}createDynamicsCompressor(){return node();}createDelay(){return node();}createBiquadFilter(){return node();}createOscillator(){return node(true);}createBufferSource(){return node(true);}createBuffer(c,n){return {getChannelData:()=>new Float32Array(n)};}resume(){this.state='running';return Promise.resolve();}suspend(){this.state='suspended';return Promise.resolve();}}
 const env={AudioContext,document:{hidden:false},setInterval:fn=>{intervals.set(next,fn);return next++;},clearInterval:id=>intervals.delete(id),localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)}};
 return {audio:create(env),env,nodes,intervals,storage,get context(){return context;}};
}
test('audio waits for interaction; unlock creates one ambience loop; leaving stops every source',()=>{
 const h=harness();h.audio.play('win');assert.equal(h.nodes.length,0);h.audio.unlock();h.audio.unlock();assert.equal(h.intervals.size,1);h.audio.spinning(true);h.audio.anticipation(true);for(const kind of ['stop','wild','scatter','match','win','bonus','multiplier','summary'])h.audio.play(kind,100);assert.ok(h.nodes.length>20);h.audio.stop();assert.equal(h.intervals.size,0);assert.equal(h.context.state,'suspended');assert.ok(h.nodes.every(n=>n.stoppedAt===0));
});
test('mute and volumes persist; hidden tabs cannot produce new effects',()=>{
 const h=harness();h.audio.unlock();h.audio.configure({music:.1,effects:.4,muted:true});assert.deepEqual(h.audio.settings(),{music:.1,effects:.4,muted:true});const count=h.nodes.length;h.audio.play('bonus');assert.equal(h.nodes.length,count);assert.equal(h.intervals.size,0);const restored=create(h.env);assert.deepEqual(restored.settings(),h.audio.settings());h.env.document.hidden=true;h.audio.configure({muted:false});h.audio.play('win');assert.equal(h.nodes.length,count);
});
test('unsupported audio never prevents gameplay configuration',()=>{const a=create({document:{hidden:false},clearInterval(){}});assert.doesNotThrow(()=>{a.unlock();a.play('wild');a.spinning(true);a.anticipation(true);a.configure({music:0});a.stop();});});
