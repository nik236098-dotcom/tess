'use strict';
/* Timelines only describe presentation. Server results are never recalculated here. */
(function(root){
 const clamp=n=>Math.max(0,Math.min(1,n));
 const ease=n=>{n=clamp(n);return n*n*(3-2*n);};
 const out=n=>1-(1-clamp(n))**3;
 const phase=(t,a,b)=>clamp((t-a)/(b-a));
 const dartsTiming={launch:.12,impact:.64};
 const durations={diamonds:1900,videopoker:1400,sicbo:2700,chicken:1450,coin:2100,rps:1600,slots:3200,andar:3200,darts:1400,bowling:4600,balloon:1450,race:6500,fishing:4600};
 function duration(game,info){return game==='andar'?Math.min(18000,1500+(info.detail?.dealt.length||0)*420):durations[game]||1600;}
 function frame(game,info,previous,t){
  t=clamp(t);const d=info.detail||{},last=info.last||{},p=ease(t);
  switch(game){
   case 'diamonds':return {items:Array.from({length:5},(_,i)=>{const u=phase(t,i*.12,.5+i*.12),fall=phase(u,0,.7),bounce=phase(u,.7,1);return {y:u<.7?-62*(1-out(fall)):-5*Math.sin(bounce*Math.PI),rotation:0,opacity:Math.min(1,u*6),settled:u===1};})};
   case 'videopoker':return {cards:Array.from({length:5},(_,i)=>{const kept=info.phase==='done'&&info.held?.includes(i);const u=phase(t,i*.07,.65+i*.07);return {flip:kept?180:180*ease(u),y:kept?0:(1-out(u))*-45};})};
   case 'sicbo':return {dice:Array.from({length:3},(_,i)=>{const u=phase(t,0,.78+i*.09),rest=1-u,roll=rest*rest;return {x:[-10,8,-8][i]*roll,y:-12*roll,height:46*Math.abs(Math.sin(u*Math.PI*3))*roll,rx:-58+720*roll,ry:26+(i%2?-720:720)*roll,rz:[-10,12,-8][i]+360*roll,shadow:1-.35*Math.abs(Math.sin(u*Math.PI*3))*roll,settled:u===1};})};
   case 'coin':{const u=phase(t,0,.82),start=previous?.last?.opponent===1?180:0,end=1440+(last.opponent===1?180:0),bounce=phase(t,.82,1),height=t<.82?64*Math.sin(u*Math.PI):9*Math.sin(bounce*Math.PI);return {angle:start+(end-start)*out(u),y:-height,shadow:1-height/110};}
   case 'rps':return {reveal:t>=.65,y:t<.65?-18*Math.abs(Math.sin(t/.65*Math.PI*3)):0,scale:1+.1*Math.sin(phase(t,.65,1)*Math.PI)};
   case 'slots':return {reels:[0,1,2].map(i=>({position:18*out(phase(t,0,.7+i*.13)),settled:t>=.7+i*.13}))};
   case 'andar':{const n=d.dealt?.length||0,progress=phase(t,.15,.95)*n;return {count:Math.min(n,Math.floor(progress)),flight:progress%1,index:Math.min(n-1,Math.floor(progress)),complete:t>=.95};}

   case 'darts':{
    const u=phase(t,dartsTiming.launch,dartsTiming.impact),travel=u*u,radius=clamp(d.radius||0),angle=d.angle||0;
    const x=150+119*radius*Math.sin(angle),y=151-119*radius*Math.cos(angle);
    return {x,y:y+(370-y)*(1-travel),scale:.72+1.1*(1-travel),opacity:t<dartsTiming.launch?0:Math.min(1,u*12),hit:t>=dartsTiming.impact,rotation:0,ripple:phase(t,dartsTiming.impact,.88)};
   }
   case 'bowling':return (typeof module==='object'&&module.exports?require('./bowling-scene'):root.BowlingScene).frame(info,t);
   case 'balloon':return (typeof module==='object'&&module.exports?require('./balloon-scene'):root.BalloonScene).frame(info,previous,t);
   case 'race':return (typeof module==='object'&&module.exports?require('./race-scene'):root.RaceScene).frame(info,t);
   case 'fishing':return (typeof module==='object'&&module.exports?require('./fishing-scene'):root.FishingScene).frame(info,t);
   default:return {progress:p};
  }
 }
 const api={clamp,ease,out,phase,duration,frame,dartsTiming};
 if(typeof module==='object'&&module.exports)module.exports=api;else root.CasinoMotion=api;
})(globalThis);
