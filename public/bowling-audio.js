'use strict';
(function(root){
 // Shared sample builders also let the offline preview use exactly the in-game sounds.
 function samples(kind,rate,seed=1){
  const duration=kind==='roll'?1.4:kind==='head'?.32:kind==='land'?.17:.24,data=new Float32Array(Math.ceil(rate*duration));let random=seed|0,brown=0;
  const noise=()=>{random=(Math.imul(random,1664525)+1013904223)|0;return (random>>>0)/2147483648-1;};
  for(let i=0;i<data.length;i++){
   const t=i/rate,n=noise();brown=(brown+n*.075)/1.075;
   if(kind==='roll'){const grain=(.65+.35*Math.sin(t*Math.PI*2*37)**2);data[i]=brown*grain*.85+n*.045+Math.sin(t*Math.PI*2*84)*.035;}
   else{const attack=Math.min(1,t/.0015),base=kind==='head'?175:kind==='land'?220:340+seed%140;
    data[i]=attack*(Math.sin(2*Math.PI*base*t)*Math.exp(-t*24)*.48+Math.sin(2*Math.PI*base*2.37*t)*Math.exp(-t*31)*.24+n*Math.exp(-t*(kind==='head'?43:65))*.62+brown*Math.exp(-t*16)*.18);
   }
  }
  if(kind==='roll'){const fade=Math.floor(rate*.025);for(let i=0;i<fade;i++){data[i]*=i/fade;data[data.length-1-i]*=i/fade;}}
  return data;
 }
 function create(env){
  let context=null,enabled=true,sequence=null,rolling=null,master=null;const voices=new Set(),key='pokergena.bowling.sound';
  try{enabled=env.localStorage?.getItem(key)!=='off';}catch{}
  function stopRolling(){if(rolling){try{rolling.source.stop();}catch{}rolling=null;}}
  function stop(){sequence=null;stopRolling();for(const source of [...voices]){try{source.stop();}catch{}}voices.clear();}
  function unlock(){if(!enabled)return;try{const Audio=env.AudioContext||env.webkitAudioContext;if(!Audio)return;if(!context){context=new Audio();master=context.createGain();master.gain.value=.68;master.connect(context.destination);}if(context.state!=='running')context.resume()?.catch(()=>{});}catch{}}
  function playable(){return enabled&&context?.state==='running'&&!env.document?.hidden;}
  function voice(kind,seed){
   if(!playable())return null;
   try{const data=samples(kind,context.sampleRate,seed),buffer=context.createBuffer(1,data.length,context.sampleRate);buffer.getChannelData(0).set(data);const source=context.createBufferSource(),gain=context.createGain(),filter=context.createBiquadFilter();source.buffer=buffer;source.loop=kind==='roll';filter.type='lowpass';filter.frequency.value=kind==='roll'?1150:kind==='head'?2800:4300;gain.gain.value=kind==='roll'?.24:kind==='head'?.54:kind==='land'?.15:.28;
    source.connect(filter);filter.connect(gain);gain.connect(master);voices.add(source);source.onended=()=>{voices.delete(source);source.disconnect();filter.disconnect();gain.disconnect();};source.start();if(!source.loop)source.stop(context.currentTime+data.length/context.sampleRate);return {source,gain,filter};
   }catch{return null;}
  }
  function begin(info,reduced=false){stop();const timeline=env.BowlingPhysics.timeline(info);sequence={info,reduced,events:timeline.events,index:0,last:0,finished:false};}
  function frame(t){
   const s=sequence;if(!s)return;
   if(env.document?.hidden){stop();return;}
   const now=t*env.BowlingPhysics.DURATION/1000,pose=env.BowlingPhysics.frame(s.info,t);
   if(s.reduced){if(t>=1&&!s.finished){s.finished=true;if(env.BowlingPhysics.count(s.info))voice('head',71);}return;}
   if(now>=.12&&t<1&&!pose.inPit&&pose.speed>.18){
    if(!rolling)rolling=voice('roll',19);
    if(rolling){const amount=.20*Math.min(1,pose.speed/5.25)*(.45+.55*Math.max(0,(pose.z+6.15)/11.95));rolling.gain.gain.setTargetAtTime(amount,context.currentTime,.045);rolling.source.playbackRate.setTargetAtTime(.65+.35*Math.min(1,pose.speed/5.25),context.currentTime,.04);}
   }else stopRolling();
   while(s.index<s.events.length&&s.events[s.index].time<=now){const e=s.events[s.index++];if(now-e.time<=.12)voice(e.type,e.pin*71+31);}
   s.last=now;if(t>=1){stopRolling();s.finished=true;}
  }
  function toggle(){enabled=!enabled;try{env.localStorage?.setItem(key,enabled?'on':'off');}catch{}if(enabled)unlock();else stop();return enabled;}
  env.document?.addEventListener?.('visibilitychange',()=>{if(env.document.hidden)stop();});
  return {unlock,begin,frame,stop,toggle,isEnabled:()=>enabled};
 }
 if(typeof module==='object'&&module.exports)module.exports={create,samples};else root.BowlingAudio=create(root);
})(globalThis);
