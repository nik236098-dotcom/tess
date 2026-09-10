'use strict';
(function(root){
 const FILES={base:'base.mp3',bonus:'bonus.mp3',motor:'motor.mp3',stop:'reel-stop.mp3',scatter:'scatter.mp3',match:'match.mp3',anticipation:'anticipation.mp3',big:'big-win.mp3',mega:'mega-win.mp3'};
 function create(env){
  let ctx=null,master,music,effects,active=false,featureMode=false,loading=null;
  let musicVoice=null,spinVoice=null,tension=null,celebration=null,spinWanted=false,tensionWanted=false,stoppedReels=0;
  const buffers=new Map(),voices=new Set();
  const settings={music:.32,effects:.65,muted:false};
  try{const p=JSON.parse(env.localStorage?.getItem('abyss-sound')||'{}');for(const k of ['music','effects'])if(Number.isFinite(p[k]))settings[k]=Math.max(0,Math.min(1,p[k]));settings.muted=p.muted===true;}catch{}
  const allowed=()=>active&&!settings.muted&&ctx?.state==='running'&&!env.document?.hidden;
  const ramp=(param,value,seconds=.08)=>{param.cancelScheduledValues(ctx.currentTime);param.setValueAtTime(param.value,ctx.currentTime);param.linearRampToValueAtTime(value,ctx.currentTime+seconds);};
  function stopVoice(v,fade=0){
   if(!v||v.stopped)return;v.stopped=true;
   try{if(fade)ramp(v.gain.gain,0,fade);v.source.stop(ctx.currentTime+fade);}catch{}
  }
  function sample(name,{bus=effects,level=1,loop=false,rate=1,fade=0}={}){
   if(!allowed()||!buffers.has(name))return null;
   try{
    const source=ctx.createBufferSource(),gain=ctx.createGain();source.buffer=buffers.get(name);source.loop=loop;source.playbackRate.value=rate;
    gain.gain.setValueAtTime(fade?0:level,ctx.currentTime);if(fade)gain.gain.linearRampToValueAtTime(level,ctx.currentTime+fade);
    source.connect(gain);gain.connect(bus);const v={source,gain,name,stopped:false};voices.add(v);
    source.onended=()=>{voices.delete(v);source.disconnect();gain.disconnect();if(celebration===v){celebration=null;duck(false);}};
    source.start();return v;
   }catch{return null;} // Asset / browser failures must never affect wagers.
  }
  function duck(on){if(ctx&&music)ramp(music.gain,settings.music*(on?0.25:1),.25);}
  function syncMusic(){
   if(!allowed())return;
   const name=featureMode?'bonus':'base';if(musicVoice?.name===name&&!musicVoice.stopped)return;
   if(!buffers.has(name))return;stopVoice(musicVoice,.55);musicVoice=sample(name,{bus:music,loop:true,fade:.55});
  }
  function syncLoops(){
   syncMusic();
   if(spinWanted&&!spinVoice)spinVoice=sample('motor',{loop:true,level:.48*Math.max(.15,(5-stoppedReels)/5),fade:.04});
   if(tensionWanted&&!tension)tension=sample('anticipation',{loop:true,level:.7,fade:.05});
  }
  function preload(){
   if(!ctx||typeof env.fetch!=='function')return Promise.resolve();
   if(loading)return loading;
   // Decode once. A completed download may start only a currently requested loop,
   // never replay an old Scatter / win after the user has left the game.
   loading=Promise.allSettled(Object.entries(FILES).filter(([k])=>!buffers.has(k)).map(async([key,file])=>{
    const response=await env.fetch('/audio/abyss/'+file+'?v=1');if(!response.ok)throw Error('Audio unavailable');
    const decoded=await ctx.decodeAudioData(await response.arrayBuffer());buffers.set(key,decoded);if(allowed())syncLoops();
   })).then(()=>{loading=null;});return loading;
  }
  function unlock(){
   active=true;
   try{
    if(!ctx){const Audio=env.AudioContext||env.webkitAudioContext;if(!Audio)return;ctx=new Audio();master=ctx.createGain();music=ctx.createGain();effects=ctx.createGain();
     const limiter=ctx.createDynamicsCompressor();limiter.threshold.value=-6;limiter.knee.value=8;limiter.ratio.value=4;
     music.connect(master);effects.connect(master);master.connect(limiter);limiter.connect(ctx.destination);
    }
    master.gain.value=settings.muted?0:.8;music.gain.value=settings.music*(celebration?0.25:1);effects.gain.value=settings.effects;
    if(settings.muted||env.document?.hidden)return;
    preload();if(ctx.state!=='running')Promise.resolve(ctx.resume()).then(()=>{if(allowed())syncLoops();}).catch(()=>{});else syncLoops();
   }catch{}
  }
  function halt(){
   active=false;spinWanted=false;tensionWanted=false;stoppedReels=0;musicVoice=spinVoice=tension=celebration=null;
   for(const v of voices){try{v.source.stop(ctx.currentTime);}catch{}v.stopped=true;}voices.clear();
   if(ctx?.state==='running')Promise.resolve(ctx.suspend()).catch(()=>{});
  }
  function configure(p){
   for(const k of ['music','effects'])if(Number.isFinite(p[k]))settings[k]=Math.max(0,Math.min(1,p[k]));
   if(typeof p.muted==='boolean')settings.muted=p.muted;
   try{env.localStorage?.setItem('abyss-sound',JSON.stringify(settings));}catch{}
   if(settings.muted)halt();else unlock();
  }
  function setMode(bonus){featureMode=bonus===true;if(ctx)syncMusic();}
  function spinning(on){
   if(!on){spinWanted=false;stopVoice(spinVoice,.06);spinVoice=null;return;}
   spinWanted=true;stoppedReels=0;stopVoice(spinVoice,.03);spinVoice=null;finishCelebration();syncLoops();
  }
  function anticipation(on){
   tensionWanted=on===true;
   if(!tensionWanted){stopVoice(tension,.08);tension=null;}else if(allowed())syncLoops();
  }
  function finishCelebration(){stopVoice(celebration,.15);celebration=null;duck(false);}
  function fanfare(name){finishCelebration();celebration=sample(name,{level:.8});if(celebration)duck(true);}
  function play(kind,value=1){
   if(!allowed())return;
   if(kind==='stop'){
    sample('stop',{level:.7});stoppedReels=Math.min(5,stoppedReels+1);
    if(spinVoice)ramp(spinVoice.gain.gain,.48*(5-stoppedReels)/5,.05);
   }else if(kind==='scatter')sample('scatter',{level:.82,rate:2**(Math.min(2,Math.max(0,value-1))/12)});
   else if(kind==='wild')sample('scatter',{level:.6,rate:.8});
   else if(kind==='match')sample('match',{level:.7});
   else if(kind==='multiplier')sample('match',{level:.4,rate:1.12});
   else if(kind==='bonus')sample('scatter',{level:.85,rate:.92});
   else if(kind==='bigwin'||kind==='summary')fanfare(value>=100?'mega':'big');
   // A normal win already has the match cue; do not double the reward sound.
  }
  return {unlock,preload,setMode,mode:()=>featureMode,stop:halt,configure,settings:()=>({...settings}),spinning,anticipation,play,finishCelebration};
 }
 if(typeof module==='object'&&module.exports)module.exports={create};else root.AbyssAudio=create(root);
})(globalThis);
