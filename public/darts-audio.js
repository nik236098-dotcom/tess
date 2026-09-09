'use strict';
/* Quiet, short synthesized effects. No downloads, autoplay or recurring timers. */
(function(root){
 function create(env){
  const key='pokergena.darts.sound';let context=null,enabled=true,sequence=null;const voices=new Set();
  try{enabled=env.localStorage?.getItem(key)!=='off';}catch{}
  function stop(){sequence=null;for(const v of [...voices]){try{v.stop();}catch{}}voices.clear();}
  function unlock(){
   if(!enabled)return;
   try{const Audio=env.AudioContext||env.webkitAudioContext;if(!Audio)return;context??=new Audio();if(context.state!=='running')context.resume()?.catch(()=>{});}catch{}
  }
  function toggle(){enabled=!enabled;try{env.localStorage?.setItem(key,enabled?'on':'off');}catch{}if(enabled)unlock();else stop();return enabled;}
  function sound(type){
   if(!enabled||!context||context.state!=='running'||env.document?.hidden)return;
   try{
    const hit=type==='impact',duration=hit?.115:.19,now=context.currentTime;
    const source=context.createBufferSource(),buffer=context.createBuffer(1,Math.ceil(context.sampleRate*duration),context.sampleRate),data=buffer.getChannelData(0);
    // A filtered air sweep for flight, a dry noise transient for sisal impact.
    for(let i=0;i<data.length;i++)data[i]=(Math.random()*2-1)*(hit?Math.exp(-i/data.length*5):1);
    source.buffer=buffer;
    const filter=context.createBiquadFilter(),gain=context.createGain();filter.type=hit?'lowpass':'bandpass';filter.Q.value=hit?.65:.8;
    filter.frequency.setValueAtTime(hit?2300:2600,now);filter.frequency.exponentialRampToValueAtTime(hit?500:700,now+duration);
    gain.gain.setValueAtTime(.0001,now);gain.gain.exponentialRampToValueAtTime(hit?.26:.09,now+(hit?.003:.045));gain.gain.exponentialRampToValueAtTime(.0001,now+duration);
    source.connect(filter);filter.connect(gain);gain.connect(context.destination);voices.add(source);
    source.onended=()=>{voices.delete(source);source.disconnect();filter.disconnect();gain.disconnect();};source.start(now);source.stop(now+duration);
   }catch{} // Audio support never affects a wager or the animation lock.
  }
  function begin(revision,reduced=false){stop();sequence={revision,reduced,thrown:false,hit:false};}
  function advance(s,t){
   if(!s)return;
   const timing=env.CasinoMotion?.dartsTiming||{launch:.12,impact:.64};
   if(t>=timing.impact&&!s.hit){s.thrown=true;s.hit=true;sound('impact');}
   else if(t>=timing.launch&&!s.thrown){s.thrown=true;if(!s.reduced)sound('throw');}
  }
  function frame(t){advance(sequence,t);}
  function channel(reduced=false){const s={reduced,thrown:false,hit:false};return {frame:t=>advance(s,t)};}
  return {unlock,toggle,stop,begin,frame,channel,isEnabled:()=>enabled};
 }
 if(typeof module==='object'&&module.exports)module.exports={create};else root.DartsAudio=create(root);
})(globalThis);
