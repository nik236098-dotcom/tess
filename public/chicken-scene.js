'use strict';
/* Articulated, resolution-independent game art. Outcomes come from the server. */
(function(root){
 const clamp=n=>Math.max(0,Math.min(1,n)),ease=n=>{n=clamp(n);return n*n*(3-2*n);};
 const range=(t,a,b)=>clamp((t-a)/(b-a));
 const laneX=(step,camera)=>72+(step-camera)*64;
 function pose(info,previous,t){
  t=clamp(t);const failed=info.last?.safe===false,step=info.step||0,target=step+(failed?1:0);
  const from=previous?.step??Math.max(0,target-1),walk=range(t,.12,.77),travel=ease(walk);
  const max=info.coefficients?.length||20,cam=s=>Math.max(1,Math.min(max-4,s-2));
  const camera=cam(from)+(cam(target)-cam(from))*travel;
  const start=from?laneX(from,camera):28,end=laneX(target||1,camera);
  const x=target?start+(end-start)*travel:28;
  // Two footfalls per lane. A planted foot travels backwards relative to the body.
  const stride=walk*2,weight=walk===0||walk===1?0:Math.sin(Math.PI*walk),leg=offset=>{
   const cycle=(stride+offset)%1,stance=cycle<.6;
   const u=stance?cycle/.6:(cycle-.6)/.4;
   return {x:(stance?9-18*u:-9+18*ease(u))*weight,y:stance?0:-8*Math.sin(u*Math.PI)*weight};
  };
  const impact=failed&&t>=.79,carY=failed?-65+235*range(t,.24,.79)+205*range(t,.79,1):-65+440*range(t,0,.48);
  return {x,camera,target,walk,bodyY:weight?-1.8*Math.sin(stride*Math.PI*2)**2*weight:0,wing:weight?5*Math.sin(stride*Math.PI*2)*weight:0,
   near:leg(0),far:leg(.5),impact,fade:impact?1-.65*range(t,.79,1):1,
   carX:laneX(target||1,camera),carY,carScale:.4+.8*clamp((carY+65)/400)};
 }
 function legPath(foot,near){
  const hip=near?5:-8,ankle=hip+foot.x,knee=hip-5+foot.x*.35,y=49+foot.y;
  return `M${hip} 29 Q${knee} 36 ${ankle} ${y} M${ankle} ${y} l9 2 M${ankle} ${y} l5 5`;
 }
 function chicken(prefix){return `<g fill="none" stroke-linecap="round" stroke-linejoin="round">
  <path data-ch-leg="far" d="${legPath({x:0,y:0},false)}" stroke="#ca751f" stroke-width="4.5"/>
  <g data-ch-body="">
   <path d="M-22 11C-40 11-42-2-39-8Q-33-6-27 0C-42-18-34-23-27-17L-13-3Z" fill="url(#${prefix}-cream)" stroke="#e3bba3" stroke-width=".6"/>
   <path d="M-26 1C-31 20-18 37 2 36C23 35 28 16 24 0L20-20C19-33 4-37-6-26C-14-17-9-7-26 1Z" fill="url(#${prefix}-cream)" stroke="#e6c3aa" stroke-width=".7"/>
   <path d="M-23 18Q-15 32 6 30Q19 28 22 15C20 37-8 47-23 18" fill="#dca58d" opacity=".35"/>
   <path d="M0-29C-15-34-13-44-8-43L-3-36C-9-50 1-51 5-37C6-49 14-46 12-36C24-44 23-30 16-28Z" fill="url(#${prefix}-comb)" stroke="#c73743" stroke-width=".6"/>
   <ellipse cx="21" cy="-3" rx="4" ry="8" fill="url(#${prefix}-comb)"/>
   <ellipse cx="13" cy="-17" rx="5" ry="7" fill="#fff7e8"/>
   <ellipse cx="15" cy="-16" rx="2.8" ry="4.6" fill="#312037"/>
   <circle cx="15.6" cy="-18" r="1.1" fill="white"/>
   <path d="M8-25q5-2 10 1" stroke="#4c3032" stroke-width="2.6"/>
   <path d="M20-15Q25-19 33-10Q35-6 22-6Z" fill="url(#${prefix}-beak)" stroke="#da8415" stroke-width=".7"/>
   <path d="M23-7L31-8" stroke="#d98b24" stroke-width=".7"/>
   <path d="M-20 5C-27 5-30 16-19 23C-8 30 6 21 4 15Q-9 20-20 5Z" data-ch-wing="" fill="url(#${prefix}-wing)" stroke="#deb89d" stroke-width=".8"/>
   <path d="M-26 7Q-21-1-15 0" stroke="#fff9ef" stroke-width="2.5" opacity=".7"/>
  </g><path data-ch-leg="near" d="${legPath({x:0,y:0},true)}" stroke="#f3a12c" stroke-width="4.5"/>
 </g>`;}
 function car(prefix,color){return `<g stroke-linejoin="round">
  <ellipse cy="28" rx="31" ry="8" fill="#070815" opacity=".4"/>
  <rect x="-29" y="11" width="10" height="19" rx="4" fill="#10131f"/><rect x="19" y="11" width="10" height="19" rx="4" fill="#10131f"/>
  <path d="M-25-4L-20-26Q-17-33 0-33Q17-33 20-26L25-4Z" fill="${color}" stroke="#141329" stroke-width="1"/>
  <path d="M-18-24Q0-28 18-24L21-6H-21Z" fill="url(#${prefix}-glass)" stroke="#222237" stroke-width="2"/>
  <path d="M-14-23L-3-25L-15-8H-20Z" fill="#cce1f6" opacity=".2"/>
  <path d="M-24-6Q0-11 24-6L30 10V24Q0 34-30 24V10Z" fill="${color}" stroke="#24203c" stroke-width="1"/>
  <path d="M-22-4Q0-8 22-4L26 7Q0 1-26 7Z" fill="#fff" opacity=".18"/>
  <rect x="-34" y="-5" width="10" height="6" rx="3" fill="#34374c"/><rect x="24" y="-5" width="10" height="6" rx="3" fill="#34374c"/>
  <path d="M-27 20Q0 27 27 20L26 26Q0 33-26 26Z" fill="#26283b"/>
  <rect x="-12" y="14" width="24" height="7" rx="3" fill="#192034"/><path d="M-9 16H9M-8 19H8" stroke="#56586c"/>
  <path d="M-26 9Q-19 7-14 12L-15 16Q-23 18-27 14Z" fill="#fff4b8" stroke="#ffcf76"/>
  <path d="M26 9Q19 7 14 12L15 16Q23 18 27 14Z" fill="#fff4b8" stroke="#ffcf76"/>
  <rect x="-7" y="24" width="14" height="4" rx="1" fill="#c3bace"/>
 </g>`;}
 function defs(p){return `<defs>
 <linearGradient id="${p}-cream" x1="0" y1="0" x2=".8" y2="1"><stop stop-color="#fffdf0"/><stop offset=".55" stop-color="#fff0d9"/><stop offset="1" stop-color="#dca98d"/></linearGradient>
 <linearGradient id="${p}-wing" x2=".7" y2="1"><stop stop-color="#fff4dc"/><stop offset="1" stop-color="#e4b497"/></linearGradient>
 <linearGradient id="${p}-comb" x2=".8" y2="1"><stop stop-color="#ff7567"/><stop offset="1" stop-color="#cd243d"/></linearGradient>
 <linearGradient id="${p}-beak" x2=".4" y2="1"><stop stop-color="#ffdb57"/><stop offset="1" stop-color="#f29419"/></linearGradient>
 <linearGradient id="${p}-glass" x2=".5" y2="1"><stop stop-color="#55738e"/><stop offset="1" stop-color="#1a223d"/></linearGradient>
 <linearGradient id="${p}-blue" x1="0" y1="0" x2=".8" y2="1"><stop stop-color="#8cafff"/><stop offset=".4" stop-color="#487ceb"/><stop offset=".7" stop-color="#2856c0"/><stop offset="1" stop-color="#193570"/></linearGradient>
 <linearGradient id="${p}-red" x1="0" y1="0" x2=".8" y2="1"><stop stop-color="#ffada1"/><stop offset=".4" stop-color="#f26c77"/><stop offset=".7" stop-color="#cd435e"/><stop offset="1" stop-color="#76334a"/></linearGradient>
 <linearGradient id="${p}-road" x2="0" y2="1"><stop stop-color="#34304e"/><stop offset="1" stop-color="#242139"/></linearGradient>
 <linearGradient id="${p}-curb" x2="1" y2="0"><stop stop-color="#6e508f"/><stop offset=".5" stop-color="#433357"/><stop offset="1" stop-color="#8c69b4"/></linearGradient>
 <radialGradient id="${p}-light"><stop stop-color="#ffdc98" stop-opacity=".5"/><stop offset="1" stop-color="#ffdc98" stop-opacity="0"/></radialGradient>
 <pattern id="${p}-grain" width="29" height="23" patternUnits="userSpaceOnUse"><circle cx="3" cy="7" r=".6" fill="#ddd0fa" opacity=".07"/><circle cx="18" cy="18" r=".8" fill="#060615" opacity=".18"/></pattern>
 <clipPath id="${p}-road-clip"><path d="M36 0H364L380 300H20Z"/></clipPath>
 </defs>`;}
 function scene(info={},previous=null,animating=false){
  const p='ch-road',f=pose(info,animating?previous:null,1),lanes=info.coefficients||[];
  const start=Math.max(1,Math.floor(f.camera)-1);
  const indices=Array.from({length:Math.min(8,Math.max(5,lanes.length-start+1))},(_,i)=>start+i).filter(i=>!lanes.length||i<=lanes.length);
  return `<div class="ch-scene${animating?' is-moving':''}${!animating&&info.last?.safe===false?' is-crashed':''}"><svg class="ch-road-svg" viewBox="0 0 400 300" role="img" aria-label="Курица переходит дорогу. Машины едут навстречу.">${defs(p)}
  <rect width="400" height="300" fill="url(#${p}-road)"/><rect width="400" height="300" fill="url(#${p}-grain)"/>
  <path d="M0 0H36L20 300H0ZM364 0H400V300H380Z" fill="url(#${p}-curb)"/>
  <path d="M36 0L20 300M364 0L380 300" stroke="#ad85d5" stroke-width="3" opacity=".65"/>
  ${Array.from({length:13},(_,i)=>`<path d="M0 ${i*25}H${36-i*1.33}M${364+i*1.33} ${i*25}H400" stroke="#291d40" stroke-width="1.5" opacity=".55"/><path d="M0 ${i*25+2}H${36-i*1.33}M${364+i*1.33} ${i*25+2}H400" stroke="#b38bdd" stroke-width="1" opacity=".2"/>`).join('')}
  <g clip-path="url(#${p}-road-clip)">${Array.from({length:8},(_,i)=>{const x=40+(i-1)*64;return `<path data-ch-mark="${i}" d="M${200+(x-200)*.85} 0L${x} 300" stroke="#c1acd4" stroke-width="2" stroke-dasharray="13 16" opacity=".35"/>`;}).join('')}</g>
  ${[30,268].flatMap(y=>[15,385].map(x=>`<g transform="translate(${x} ${y})"><circle r="16" fill="url(#${p}-light)"/><path d="M0 0V18" stroke="#1b162c" stroke-width="3"/><ellipse cy="19" rx="5" ry="2" fill="#171227"/><path d="M-4-7H4L3 2H-3Z" fill="#ffdda1" stroke="#261e32" stroke-width="2"/><path d="M-5-8L0-12 5-8" fill="#30203e"/></g>`)).join('')}
  <path d="M42 176H358" stroke="#b291e3" stroke-width="1.5" stroke-dasharray="1 5" stroke-linecap="round" opacity=".6"/>
  <g class="ch-traffic ch-traffic-blue" data-ch-traffic="blue" transform="translate(75 244) scale(.85)">${car(p,'url(#ch-road-blue)')}</g>
  <g class="ch-traffic ch-traffic-red" data-ch-traffic="red" transform="translate(326 48) scale(.58)">${car(p,'url(#ch-road-red)')}</g>
  <ellipse data-ch-shadow="" cx="${f.x}" cy="184" rx="21" ry="5" fill="#a965fc" opacity=".3"/>
  <g data-chicken="" transform="translate(${f.x} 151) scale(.7)">${chicken(p)}</g>
  <g data-ch-crossing-car="" display="none">${car(p,'url(#ch-road-red)')}</g>
  <g data-ch-impact="" display="none"><path d="m0-19 4 12 12-5-6 11 11 5-13 2 3 12-10-8-7 9 1-13-12-2 10-7-5-10 11 4Z" fill="#ffd36f"/><text y="5" text-anchor="middle" fill="#743344" font-size="14" font-weight="900">!</text></g>
  </svg><span class="ch-step">ШАГ ${info.step||0}</span><div class="ch-lane-values" aria-label="Коэффициенты шагов">${indices.map(i=>`<span data-ch-lane="${i}" style="left:${laneX(i,f.camera)/4}%" class="ch-lane ${lanes[i-1]>=1000?'is-long':''} ${i===(info.step||0)?'is-current':i<(info.step||0)?'is-passed':''}">${Number(lanes[i-1]||1).toFixed(2)}×${i<(info.step||0)?'<i>✓</i>':''}</span>`).join('')}</div></div>`;
 }
 function paint(host,info,previous,t,animating){
  const f=pose(info,animating?previous:null,t),q=s=>host.querySelector(s),attr=(s,k,v)=>q(s)?.setAttribute(k,v);
  attr('[data-chicken]','transform',`translate(${f.x} 151) scale(.7)`);
  attr('[data-ch-body]','transform',`translate(0 ${f.bodyY})`);
  attr('[data-chicken]','opacity',f.fade);
  attr('[data-ch-shadow]','cx',f.x);attr('[data-ch-shadow]','rx',21+f.bodyY);
  attr('[data-ch-leg="near"]','d',legPath(f.near,true));attr('[data-ch-leg="far"]','d',legPath(f.far,false));
  attr('[data-ch-wing]','transform',`rotate(${f.wing} -12 8)`);
  attr('[data-ch-crossing-car]','display',animating?'inline':'none');
  attr('[data-ch-crossing-car]','transform',`translate(${f.carX} ${f.carY}) scale(${f.carScale})`);
  attr('[data-ch-impact]','display',f.impact?'inline':'none');attr('[data-ch-impact]','transform',`translate(${f.x} 128)`);
  const current=info.step||0;
  // Decorative traffic never runs through the occupied or target crossing lane.
  const occupied=laneX(current||1,f.camera),other=occupied>200?72:328;
  attr('[data-ch-traffic="blue"]','transform',`translate(${other} 245) scale(.88)`);
  attr('[data-ch-traffic="red"]','transform',`translate(${other===72?136:264} 44) scale(.55)`);
  for(const node of host.querySelectorAll('[data-ch-lane]'))node.style.left=laneX(Number(node.dataset.chLane),f.camera)/4+'%';
  for(const node of host.querySelectorAll('[data-ch-mark]')){
   const x=40+(Number(node.dataset.chMark)-1)*64-(f.camera-Math.floor(f.camera))*64;
   node.setAttribute('d',`M${200+(x-200)*.85} 0L${x} 300`);
  }
 }
 function cover(){const p='ch-cover';return `<svg class="ch-cover" viewBox="0 0 150 140" aria-hidden="true">${defs(p)}<path d="M24 120L44 18H111L140 120" fill="#302841"/><path d="M71 25L64 120M102 25L114 120" stroke="#9481b7" stroke-width="2" stroke-dasharray="10 10"/><ellipse cx="78" cy="115" rx="33" ry="7" fill="#a461e5" opacity=".3"/><g transform="translate(78 72) scale(.95)">${chicken(p)}</g></svg>`;}
 const api={pose,legPath,scene,paint,cover,laneX};if(typeof module==='object'&&module.exports)module.exports=api;else root.ChickenScene=api;
})(globalThis);
