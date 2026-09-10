'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {create}=require('../public/abyss-audio');
function harness({delay=false,fail=false}={}){
 const sources=[],gains=[],requests=[],pending=[],storage=new Map();let context;
 const param=()=>({value:0,setValueAtTime(v){this.value=v;},linearRampToValueAtTime(v){this.value=v;},cancelScheduledValues(){}});
 function node(){return {gain:param(),threshold:param(),knee:param(),ratio:param(),connect(){},disconnect(){}};}
 class AudioContext{
  constructor(){context=this;this.currentTime=0;this.state='running';this.destination={};}
  createGain(){const n=node();gains.push(n);return n;}
  createDynamicsCompressor(){return node();}
  createBufferSource(){const n={...node(),playbackRate:param(),start(){this.started=true;},stop(t=0){this.stoppedAt=t;}};sources.push(n);return n;}
  decodeAudioData(data){return Promise.resolve({name:data.name,duration:6});}
  resume(){this.state='running';return Promise.resolve();}
  suspend(){this.state='suspended';return Promise.resolve();}
 }
 const env={AudioContext,document:{hidden:false},localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},fetch(url){requests.push(url);const response={ok:!fail,arrayBuffer:async()=>({name:url.split('/').pop().split('?')[0]})};return delay?new Promise(r=>pending.push(()=>r(response))):Promise.resolve(response);}};
 const audio=create(env);
 return {audio,env,sources,gains,requests,pending,storage,get context(){return context;},async ready(){audio.unlock();await audio.preload();},played(name){return sources.filter(n=>n.buffer.name===name);}};
}
test('samples load once after interaction; repeated unlock never stacks background music',async()=>{
 const h=harness();h.audio.play('scatter');assert.equal(h.requests.length,0);await h.ready();await h.ready();
 assert.equal(h.requests.length,9);assert.equal(h.played('base.mp3').length,1);assert.ok(h.played('base.mp3')[0].loop);
 for(const url of h.requests)assert.ok(fs.statSync('public'+url.split('?')[0]).size>1000);
});
test('stop and mute prevent pending downloads from resurrecting music or effects',async()=>{
 for(const mute of [false,true]){const h=harness({delay:true});h.audio.unlock();h.audio.spinning(true);h.audio.anticipation(true);h.audio.play('scatter');const waiting=h.audio.preload();
 if(mute)h.audio.configure({muted:true});else h.audio.stop();for(const done of h.pending)done();await waiting;
 assert.equal(h.sources.length,0);assert.equal(h.context.state,'suspended');}
});
test('five visual stop events produce five samples and stop the motor on completion',async()=>{
 const h=harness();await h.ready();h.audio.spinning(true);const motor=h.played('motor.mp3')[0];assert.ok(motor.loop);
 for(let i=0;i<5;i++)h.audio.play('stop');assert.equal(h.played('reel-stop.mp3').length,5);
 h.audio.spinning(false);assert.ok(motor.stoppedAt<=.1);h.audio.spinning(true);assert.equal(h.played('motor.mp3').length,2);
});
test('anticipation follows its window without restarting every animation frame',async()=>{
 const h=harness();await h.ready();for(let i=0;i<120;i++)h.audio.anticipation(true);
 assert.equal(h.played('anticipation.mp3').length,1);h.audio.anticipation(false);assert.ok(h.played('anticipation.mp3')[0].stoppedAt<=.1);
});
test('base and bonus crossfade; volume changes preserve the current music source',async()=>{
 const h=harness();await h.ready();h.audio.setMode(true);h.audio.setMode(true);assert.equal(h.played('bonus.mp3').length,1);assert.equal(h.played('base.mp3')[0].stoppedAt,.55);
 h.audio.configure({music:.1,effects:.4});assert.equal(h.played('bonus.mp3').length,1);h.audio.setMode(false);assert.equal(h.played('base.mp3').length,2);
 h.audio.stop();assert.ok(h.sources.every(n=>n.stoppedAt===0)); // Also immediately kills fading crossfade tails.
});
test('first Scatter sounds; match and win do not double the same reward; settings persist',async()=>{
 const h=harness();await h.ready();h.audio.play('scatter',1);h.audio.play('scatter',2);assert.equal(h.played('scatter.mp3').length,2);assert.equal(h.played('scatter.mp3')[0].playbackRate.value,1);
 h.audio.play('match');h.audio.play('win',2);assert.equal(h.played('match.mp3').length,1);
 h.audio.configure({music:.1,effects:.4,muted:true});assert.deepEqual(create(h.env).settings(),h.audio.settings());const count=h.sources.length;h.audio.play('scatter');assert.equal(h.sources.length,count);
});
test('Big and Mega use different assets; closing celebration stops the fanfare and restores music',async()=>{
 const h=harness();await h.ready();h.audio.play('bigwin',50);assert.equal(h.played('big-win.mp3').length,1);assert.equal(h.gains[1].gain.value,.08);
 h.audio.play('bigwin',100);assert.equal(h.played('mega-win.mp3').length,1);assert.equal(h.played('big-win.mp3')[0].stoppedAt,.15);
 h.audio.finishCelebration();assert.equal(h.gains[1].gain.value,.32);assert.equal(h.played('mega-win.mp3')[0].stoppedAt,.15);
 h.audio.play('summary',500);assert.equal(h.played('mega-win.mp3').length,2);h.played('mega-win.mp3')[1].onended();assert.equal(h.gains[1].gain.value,.32);
});
test('hidden tabs, missing assets and unsupported audio cannot block gameplay',async()=>{
 const h=harness({fail:true});await h.ready();assert.equal(h.sources.length,0);assert.doesNotThrow(()=>{h.audio.play('bigwin');h.audio.spinning(true);h.audio.anticipation(true);h.audio.stop();});
 const good=harness();await good.ready();good.env.document.hidden=true;const before=good.sources.length;good.audio.play('scatter');good.audio.unlock();assert.equal(good.sources.length,before);
 const a=create({document:{hidden:false}});assert.doesNotThrow(()=>{a.unlock();a.spinning(true);a.play('stop');a.configure({music:0});a.stop();});
});
