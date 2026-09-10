'use strict';
(function(root){
 function create(env){
  let ctx=null,master=null,music=null,effects=null,verb=null,active=false,loop=0,step=0,spinVoice=null,tension=null;
  let settings={music:.32,effects:.65,muted:false};const voices=new Set();
  try{const p=JSON.parse(env.localStorage?.getItem('abyss-sound')||'{}');for(const k of ['music','effects'])if(Number.isFinite(p[k]))settings[k]=Math.max(0,Math.min(1,p[k]));settings.muted=p.muted===true;}catch{}
  const save=()=>{try{env.localStorage?.setItem('abyss-sound',JSON.stringify(settings));}catch{}};
  function allowed(){return active&&!settings.muted&&ctx?.state==='running'&&!env.document?.hidden;}
  function track(source,nodes=[]){voices.add(source);source.onended=()=>{voices.delete(source);for(const n of [source,...nodes])try{n.disconnect();}catch{}};return source;}
  function stopVoice(v){if(v)try{v.stop();}catch{}}
  function tone(freq,at,duration,level=.1,bus=effects,type='sine'){
   if(!allowed())return null;const o=ctx.createOscillator(),g=ctx.createGain();o.type=type;o.frequency.setValueAtTime(freq,at);g.gain.setValueAtTime(.0001,at);g.gain.exponentialRampToValueAtTime(Math.max(.0002,level),at+.025);g.gain.exponentialRampToValueAtTime(.0001,at+duration);o.connect(g);g.connect(bus);if(bus===effects)g.connect(verb);track(o,[g]);o.start(at);o.stop(at+duration+.04);return o;
  }
  function reelMotor(){
   if(!allowed())return null;
   // Eight cushioned gear contacts per loop, plus a quiet low motor tone.
   // No random/noise signal: the gaps between contacts remain silent above the motor.
   const length=Math.round(ctx.sampleRate*.64),b=ctx.createBuffer(1,length,ctx.sampleRate),d=b.getChannelData(0);
   for(let i=0;i<length;i++){
    const t=i/ctx.sampleRate,local=t%.08,hit=Math.floor(t/.08);
    const envelope=local<.028?Math.sin(Math.PI*local/.028)**2*Math.exp(-local*80):0;
    d[i]=.035*Math.sin(2*Math.PI*100*t)+envelope*(.42*Math.sin(2*Math.PI*(240+hit%2*25)*local)+.10*Math.sin(2*Math.PI*480*local));
   }
   const source=ctx.createBufferSource(),filter=ctx.createBiquadFilter(),gain=ctx.createGain();
   source.buffer=b;source.loop=true;filter.type='lowpass';filter.frequency.value=850;filter.Q.value=.5;
   gain.gain.setValueAtTime(.0001,ctx.currentTime);gain.gain.linearRampToValueAtTime(.18,ctx.currentTime+.07);
   source.connect(filter);filter.connect(gain);gain.connect(effects);track(source,[filter,gain]);source.start();
   return {stop(){gain.gain.cancelScheduledValues?.(ctx.currentTime);gain.gain.setValueAtTime(gain.gain.value,ctx.currentTime);gain.gain.linearRampToValueAtTime(.0001,ctx.currentTime+.045);source.stop(ctx.currentTime+.05);}};
  }
  function chord(notes,level=.075,spacing=.08,duration=1.1){if(!allowed())return;notes.forEach((f,i)=>tone(f,ctx.currentTime+i*spacing,duration,level));}
  function ambience(){
   if(!allowed())return;const now=ctx.currentTime,bases=[73.416,65.406,58.27,65.406],base=bases[Math.floor(step/4)%4];
   [1,1.5,2.4].forEach((r,i)=>tone(base*r,now+i*.12,4.5,.075,music));
   const notes=[293.665,440,349.228,523.251,440,349.228,261.626,329.628];tone(notes[step%8],now+.35,2.7,.026,music);step++;
  }
  function unlock(){
   active=true;
   try{if(!ctx){const Audio=env.AudioContext||env.webkitAudioContext;if(!Audio)return;ctx=new Audio();master=ctx.createGain();const limiter=ctx.createDynamicsCompressor();limiter.threshold.value=-16;limiter.knee.value=12;limiter.ratio.value=5;master.connect(limiter);limiter.connect(ctx.destination);music=ctx.createGain();effects=ctx.createGain();music.connect(master);effects.connect(master);
    const delay=ctx.createDelay(1),feedback=ctx.createGain();verb=ctx.createGain();verb.gain.value=.15;delay.delayTime.value=.23;feedback.gain.value=.2;verb.connect(delay);delay.connect(feedback);feedback.connect(delay);delay.connect(effects);
   }
   master.gain.value=settings.muted?0:.7;music.gain.value=settings.music;effects.gain.value=settings.effects;
   const begin=()=>{if(!active||settings.muted||env.document?.hidden)return;if(!loop){ambience();loop=env.setInterval(ambience,2400);}};
   if(ctx.state!=='running')ctx.resume()?.then(begin).catch(()=>{});else begin();
   }catch{} // Sound support never affects a wager.
  }
  function halt(){active=false;env.clearInterval(loop);loop=0;for(const v of [...voices])stopVoice(v);voices.clear();spinVoice=null;tension=null;if(ctx?.state==='running')ctx.suspend()?.catch(()=>{});}
  function configure(p){for(const k of ['music','effects'])if(Number.isFinite(p[k]))settings[k]=Math.max(0,Math.min(1,p[k]));if(typeof p.muted==='boolean')settings.muted=p.muted;save();if(settings.muted)halt();else unlock();}
  function spinning(on){stopVoice(spinVoice);spinVoice=null;if(on)spinVoice=reelMotor();}
  function anticipation(on){if(!on){stopVoice(tension);tension=null;return;}if(tension||!allowed())return;tension=tone(220,ctx.currentTime,6,.12);if(tension)tension.frequency.exponentialRampToValueAtTime(740,ctx.currentTime+5);}
  function play(kind,value=1){
   if(!allowed())return;
   if(kind==='stop'){tone(150,ctx.currentTime,.085,.055);tone(300,ctx.currentTime,.055,.018);}
   else if(kind==='wild')chord([220,330,660],.07,.045,.65);
   else if(kind==='scatter')chord([392,493.883,587.33].slice(0,Math.min(3,value)),.075,.075,.8);
   else if(kind==='match')chord([440,554.365,659.255],.045,.045,.45);
   else if(kind==='win')chord(value>=50?[293.665,440,587.33,739.99,880]:[293.665,440,587.33],value>=50?.11:.055,.11,value>=50?2:1);
   else if(kind==='bonus')chord([220,293.665,440,587.33,880],.1,.13,2);
   else if(kind==='multiplier')chord([523.251,659.255,880],.06,.07,.65);
   else if(kind==='summary')chord([146.832,220,293.665,440,587.33],.09,.13,2.5);
  }
  return {unlock,stop:halt,configure,settings:()=>({...settings}),spinning,anticipation,play};
 }
 if(typeof module==='object'&&module.exports)module.exports={create};else root.AbyssAudio=create(root);
})(globalThis);
