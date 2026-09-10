'use strict';
(function(root){
 function create(env){
  let ctx=null,master=null,music=null,baseMusic=null,bonusMusic=null,featureMode=false,effects=null,verb=null,active=false,loop=0,step=0,spinVoice=null,tension=null,announcement=null;
  let settings={music:.32,effects:.65,muted:false};const voices=new Set();
  try{const p=JSON.parse(env.localStorage?.getItem('abyss-sound')||'{}');for(const k of ['music','effects'])if(Number.isFinite(p[k]))settings[k]=Math.max(0,Math.min(1,p[k]));settings.muted=p.muted===true;}catch{}
  const save=()=>{try{env.localStorage?.setItem('abyss-sound',JSON.stringify(settings));}catch{}};
  function allowed(){return active&&!settings.muted&&ctx?.state==='running'&&!env.document?.hidden;}
  function track(source,nodes=[]){voices.add(source);source.onended=()=>{voices.delete(source);for(const n of [source,...nodes])try{n.disconnect();}catch{}};return source;}
  function stopVoice(v){if(v)try{v.stop();}catch{}}
  function tone(freq,at,duration,level=.1,bus=effects,type='sine',attack=.025,sustain=false){
   if(!allowed())return null;
   const o=ctx.createOscillator(),g=ctx.createGain(),peak=Math.max(.0002,level),nodes=[g];
   o.type=type;o.frequency.setValueAtTime(freq,at);
   g.gain.setValueAtTime(.0001,at);g.gain.exponentialRampToValueAtTime(peak,at+attack);
   if(sustain)g.gain.setValueAtTime(peak*.85,at+duration*.58);
   g.gain.exponentialRampToValueAtTime(.0001,at+duration);o.connect(g);
   if(sustain){
    const filter=ctx.createBiquadFilter();filter.type='lowpass';filter.frequency.setValueAtTime(900,at);filter.frequency.linearRampToValueAtTime(650,at+duration);filter.Q.value=.35;
    g.connect(filter);filter.connect(bus);nodes.push(filter);
    o.frequency.linearRampToValueAtTime(freq*1.001,at+duration);
   }else g.connect(bus);
   if(bus===effects)g.connect(verb);
   track(o,nodes);o.start(at);o.stop(at+duration+.04);return o;
  }
  function pad(notes,at,bus,level){
   for(const f of notes){
    tone(f,at,5.8,level,bus,'sine',1.1,true);
    tone(f*.9985,at+.06,5.65,level*.35,bus,'sine',1.25,true);
    tone(f*2,at+.12,5.4,level*.16,bus,'sine',1.4,true);
   }
  }
  function reelMotor(){
   if(!allowed())return null;
   // Eight cushioned gear contacts per loop, plus a quiet low motor tone.
   // No random/noise signal: the gaps between contacts remain silent above the motor.
   const length=Math.round(ctx.sampleRate*.64),b=ctx.createBuffer(1,length,ctx.sampleRate),d=b.getChannelData(0);
   for(let i=0;i<length;i++){
    const t=i/ctx.sampleRate,local=t%.08,hit=Math.floor(t/.08);
    const envelope=local<.028?Math.sin(Math.PI*local/.028)**2*Math.exp(-local*80):0;
    d[i]=.035*Math.sin(2*Math.PI*100*t)+envelope*(.42*Math.sin(2*Math.PI*(360+hit%2*40)*local)+.10*Math.sin(2*Math.PI*720*local));
   }
   const source=ctx.createBufferSource(),filter=ctx.createBiquadFilter(),gain=ctx.createGain();
   source.buffer=b;source.loop=true;filter.type='lowpass';filter.frequency.value=1400;filter.Q.value=.5;
   gain.gain.setValueAtTime(.0001,ctx.currentTime);gain.gain.linearRampToValueAtTime(.18,ctx.currentTime+.07);
   source.connect(filter);filter.connect(gain);gain.connect(effects);track(source,[filter,gain]);source.start();
   return {stop(){gain.gain.cancelScheduledValues?.(ctx.currentTime);gain.gain.setValueAtTime(gain.gain.value,ctx.currentTime);gain.gain.linearRampToValueAtTime(.0001,ctx.currentTime+.045);source.stop(ctx.currentTime+.05);}};
  }
  function chord(notes,level=.075,spacing=.08,duration=1.1){if(!allowed())return;notes.forEach((f,i)=>tone(f,ctx.currentTime+i*spacing,duration,level));}
  function ambience(){
   if(!allowed())return;const now=ctx.currentTime,bar=Math.floor(step/2)%4;
   // Sustained minor/add9 voicings, slowly moving layered pads: no chip arpeggio.
   const chords=[[146.832,174.614,220,329.628],[130.813,164.814,195.998,293.665],[116.541,146.832,174.614,261.626],[130.813,174.614,195.998,293.665]];
   if(step%2===0){
    pad(chords[bar],now,baseMusic,.022);
    pad(chords[bar],now,bonusMusic,.035);
    tone(chords[bar][0]/2,now,5.5,.055,baseMusic,'sine',.65,true);
    // A sparse, soft lead floats above the bonus bed instead of eighth-note bells.
    tone([440,392,349.228,391.995][bar],now+.45,3.8,.028,bonusMusic,'sine',.45,true);
   }
   // Rounded low kick and muted percussion provide energy without bright bleeps or noise.
   [0,.6,1.2,1.8].forEach(at=>{
    const kick=tone(105,now+at,.32,.14,bonusMusic,'sine',.009);
    kick?.frequency.exponentialRampToValueAtTime(48,now+at+.16);
    tone(chords[bar][0]/2,now+at+.22,.48,.055,bonusMusic,'sine',.055);
   });
   [.61,1.81].forEach(at=>{tone(185,now+at,.11,.036,bonusMusic,'sine',.006);tone(310,now+at,.065,.012,bonusMusic,'sine',.006);});
   step++;
  }
  function setMode(bonus){
   const next=bonus===true;if(next===featureMode)return;featureMode=next;
   if(!ctx||!baseMusic)return;
   for(const [bus,value] of [[baseMusic,next?0:1],[bonusMusic,next?1:0]]){bus.gain.cancelScheduledValues?.(ctx.currentTime);bus.gain.setValueAtTime(bus.gain.value,ctx.currentTime);bus.gain.linearRampToValueAtTime(value,ctx.currentTime+.8);}
  }
  function unlock(){
   active=true;
   try{if(!ctx){const Audio=env.AudioContext||env.webkitAudioContext;if(!Audio)return;ctx=new Audio();master=ctx.createGain();const limiter=ctx.createDynamicsCompressor();limiter.threshold.value=-16;limiter.knee.value=12;limiter.ratio.value=5;master.connect(limiter);limiter.connect(ctx.destination);music=ctx.createGain();effects=ctx.createGain();music.connect(master);effects.connect(master);baseMusic=ctx.createGain();bonusMusic=ctx.createGain();baseMusic.gain.value=featureMode?0:1;bonusMusic.gain.value=featureMode?1:0;baseMusic.connect(music);bonusMusic.connect(music);
    const delay=ctx.createDelay(1),feedback=ctx.createGain();verb=ctx.createGain();verb.gain.value=.15;delay.delayTime.value=.23;feedback.gain.value=.2;verb.connect(delay);delay.connect(feedback);feedback.connect(delay);delay.connect(effects);
   }
   master.gain.value=settings.muted?0:.7;music.gain.value=settings.music;effects.gain.value=settings.effects;
   const begin=()=>{if(!active||settings.muted||env.document?.hidden)return;if(!loop){ambience();loop=env.setInterval(ambience,2400);}};
   if(ctx.state!=='running')ctx.resume()?.then(begin).catch(()=>{});else begin();
   }catch{} // Sound support never affects a wager.
  }
  function halt(){if(announcement){try{env.speechSynthesis.cancel();}catch{}announcement=null;}active=false;env.clearInterval(loop);loop=0;step=0;for(const v of [...voices])stopVoice(v);voices.clear();spinVoice=null;tension=null;if(ctx?.state==='running')ctx.suspend()?.catch(()=>{});}
  function configure(p){for(const k of ['music','effects'])if(Number.isFinite(p[k]))settings[k]=Math.max(0,Math.min(1,p[k]));if(typeof p.muted==='boolean')settings.muted=p.muted;save();if(settings.muted)halt();else unlock();}
  function spinning(on){stopVoice(spinVoice);spinVoice=null;if(on)spinVoice=reelMotor();}
  function anticipation(on){if(!on){stopVoice(tension);tension=null;return;}if(tension||!allowed())return;tension=tone(220,ctx.currentTime,6,.12);if(tension)tension.frequency.exponentialRampToValueAtTime(740,ctx.currentTime+5);}
  function announce(text){
   if(!allowed()||settings.effects<=0||!env.speechSynthesis||!env.SpeechSynthesisUtterance)return;
   try{
    if(announcement)env.speechSynthesis.cancel();
    const line=new env.SpeechSynthesisUtterance(text),voices=env.speechSynthesis.getVoices();
    const english=voices.filter(v=>/^en[-_]/i.test(v.lang));
    line.voice=english.find(v=>/Daniel|Aaron|Guy|Ryan|Natural/i.test(v.name))||english.find(v=>/^en-US$/i.test(v.lang))||english[0]||null;
    line.lang=line.voice?.lang||'en-US';line.rate=.86;line.pitch=.85;line.volume=settings.effects;
    announcement=line;line.onend=line.onerror=()=>{if(announcement===line)announcement=null;};env.speechSynthesis.speak(line);
   }catch{announcement=null;}
  }
  function play(kind,value=1){
   if(!allowed())return;
   if(kind==='stop'){tone(330,ctx.currentTime,.09,.055);tone(660,ctx.currentTime,.12,.022);}
   else if(kind==='wild')chord([220,330,660],.07,.045,.65);
   else if(kind==='scatter'){const lift=2**(Math.min(2,Math.max(0,value-1))*2/12);chord([523.251,659.255,783.991].map(f=>f*lift),.075,.055,.85);tone(1046.502*lift,ctx.currentTime,.5,.025);}
   else if(kind==='match')chord([440,554.365,659.255],.045,.045,.45);
   else if(kind==='win')chord(value>=50?[293.665,440,587.33,739.99,880]:[293.665,440,587.33],value>=50?.11:.055,.11,value>=50?2:1);
   else if(kind==='bigwin'){
    announce(value>=500?'Epic win!':value>=100?'Mega win!':'Big win!');
    const tier=value>=500?2:value>=100?1:0;
    chord([293.665,369.994,440,587.33,739.989,880],.075,.12,1.8);
    [587.33,739.989,880,1174.66].slice(0,2+tier).forEach((f,i)=>{tone(f,ctx.currentTime+1+i*.18,1.4,.055);tone(f/2,ctx.currentTime+1+i*.18,1.2,.03,effects,'triangle');});
    tone(146.832,ctx.currentTime,2.4,.065);
   }
   else if(kind==='bonus')chord([293.665,369.994,440,587.33,739.989,880],.09,.1,1.8);
   else if(kind==='multiplier')chord([523.251,659.255,880],.06,.07,.65);
   else if(kind==='summary')chord([146.832,220,293.665,440,587.33],.09,.13,2.5);
  }
  return {unlock,setMode,mode:()=>featureMode,stop:halt,configure,settings:()=>({...settings}),spinning,anticipation,play};
 }
 if(typeof module==='object'&&module.exports)module.exports={create};else root.AbyssAudio=create(root);
})(globalThis);
