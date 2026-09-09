'use strict';
/* Timelines only describe presentation. Server results are never recalculated here. */
(function(root){
 const clamp=n=>Math.max(0,Math.min(1,n));
 const ease=n=>{n=clamp(n);return n*n*(3-2*n);};
 const out=n=>1-(1-clamp(n))**3;
 const phase=(t,a,b)=>clamp((t-a)/(b-a));
 const durations={diamonds:1900,videopoker:1400,limbo:2400,sicbo:1850,chicken:1450,coin:1600,rps:1600,slots:2800,andar:3200,penalty:1800,darts:1400,bowling:2600,balloon:1450,race:3800,pinball:2100,fishing:2800};
 function duration(game,info){return game==='andar'?Math.min(6500,1100+(info.detail?.dealt.length||0)*125):durations[game]||1600;}
 // Paths approach a bumper tangentially, reverse at its surface, and return to a flipper.
 // Bumper centers: [30,24], [70,35], [44,54]; radius 9 scene units.
 const bumpers=[[30,24],[70,35],[44,54]], rests=[[37,86],[63,86]];
 function pinball(last,t,previous){
  const side=last?.choice||0,[bx,by]=bumpers[last?.bumper||0],rest=rests[side],wall=bx>=50?88:12;
  const points=[previous?.last?.safe?rests[previous.last.choice||0]:[50,91],rest,[wall,75],[wall,by+18],[bx,by+11],[wall,by+19],[wall,75],last?.safe===false?[50,106]:rest];
  const scaled=clamp(t)*(points.length-1),i=Math.min(points.length-2,Math.floor(scaled)),p=scaled-i;
  return {x:points[i][0]+(points[i+1][0]-points[i][0])*p,y:points[i][1]+(points[i+1][1]-points[i][1])*p,impact:Math.abs(scaled-4)<.35};
 }
 function frame(game,info,previous,t){
  t=clamp(t);const d=info.detail||{},last=info.last||{},p=ease(t);
  switch(game){
   case 'diamonds':return {items:Array.from({length:5},(_,i)=>{const u=phase(t,i*.09,.6+i*.09);return {y:(1-out(u))*-105,rotation:(1-u)*(-25+i*9),opacity:Math.min(1,u*5),settled:u===1};})};
   case 'videopoker':return {cards:Array.from({length:5},(_,i)=>{const kept=info.phase==='done'&&info.held?.includes(i);const u=phase(t,i*.07,.65+i*.07);return {flip:kept?180:180*ease(u),y:kept?0:(1-out(u))*-45};})};
   case 'limbo':return {value:Math.exp(Math.log(Math.max(1,d.value||1))*out(t)),x:12+76*t,y:82-65*t*t};
   case 'sicbo':return {dice:Array.from({length:3},(_,i)=>{const u=phase(t,0,.72+i*.09);return {angle:(1-out(u))*(720+i*180),y:-70*Math.sin(u*Math.PI)*(1-u),scale:.8+.2*out(u),settled:u===1};})};
   case 'chicken':return {x:32+10*Math.sin(phase(t,0,.8)*Math.PI),y:-30*Math.sin(phase(t,0,.8)*Math.PI),carY:-55+170*phase(t,.25,.85),impact:!last.safe&&t>.72};
   case 'coin':return {angle:1080*out(t)+(last.opponent===1?180*out(t):0),y:-55*Math.sin(t*Math.PI),shadow:.6+.4*(1-Math.sin(t*Math.PI))};
   case 'rps':return {reveal:t>=.65,y:t<.65?-18*Math.abs(Math.sin(t/.65*Math.PI*3)):0,scale:1+.1*Math.sin(phase(t,.65,1)*Math.PI)};
   case 'slots':return {reels:[0,1,2].map(i=>({position:18*out(phase(t,0,.7+i*.13)),settled:t>=.7+i*.13}))};
   case 'andar':{const n=d.dealt?.length||0,progress=phase(t,.15,.95)*n;return {count:Math.min(n,Math.floor(progress)),flight:progress%1,index:Math.min(n-1,Math.floor(progress)),complete:t>=.95};}
   case 'penalty':{const u=out(phase(t,.12,.76));return {x:50+((last.choice??2)*18+14-50)*u,y:86-51*u-14*Math.sin(u*Math.PI),scale:1-.5*u,rotation:420*u,keeperX:50+((last.opponent??2)*18+14-50)*ease(phase(t,.24,.68)),hit:t>=.76};}
   case 'darts':{const u=out(phase(t,.2,.8));return {x:50+43*(d.radius||0)*Math.sin(d.angle||0),y:50-43*(d.radius||0)*Math.cos(d.angle||0)+(1-u)*65,scale:1+.6*(1-u),opacity:Math.min(1,u*5),hit:t>=.8};}
   case 'bowling':{const u=ease(phase(t,0,.6)),travel=phase(t,.6,.93),rows=[22,22,22,22,28,28,28,34,34,40];return {y:90-50*u-20*travel,scale:1-.65*u,rotation:540*(u+travel*.3),pins:Array.from({length:10},(_,i)=>{const hit=.6+(40-rows[i])/20*.33,v=phase(t,hit,Math.min(1,hit+.12));return {fall:d.fallen?.[i]?ease(v):0,angle:(i%2?1:-1)*75*ease(v)};})};}
   case 'balloon':{const old=previous?.step||0,now=info.step||old;return {scale:1+.018*(old+(now-old)*out(phase(t,0,.7))),pump:Math.sin(phase(t,0,.55)*Math.PI),burst:last.safe===false&&t>.68,burstProgress:phase(t,.68,1)};}
   case 'race':return {cars:[0,1,2,3].map(i=>{const rank=d.order?.indexOf(i)??i;return {y:85-(70-rank*7)*ease(t)+(t===1?0:Math.sin(t*9+i)*4*Math.sin(t*Math.PI)),finished:t===1};})};
   case 'pinball':return pinball(last,t,previous);
   case 'fishing':{const u=phase(t,.16,.68),haul=out(phase(t,.7,1));return {hookY:8+61*ease(u)-57*haul,fishX:105-55*out(phase(t,.28,.7)),fishY:69-57*haul,reveal:t>.36&&Boolean(d.prize),caught:t>.7};}
   default:return {progress:p};
  }
 }
 const api={clamp,ease,out,phase,duration,frame,bumpers};
 if(typeof module==='object'&&module.exports)module.exports=api;else root.CasinoMotion=api;
})(globalThis);
