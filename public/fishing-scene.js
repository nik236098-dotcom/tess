'use strict';
/* A cast, bite and haul share one line endpoint. The server selects the catch. */
(function(root){
 const clamp=n=>Math.max(0,Math.min(1,n)),phase=(t,a,b)=>clamp((t-a)/(b-a)),ease=n=>{n=clamp(n);return n*n*(3-2*n);};
 const catches=[{value:0,name:'Пусто',color:'#9992b1',scale:0},{value:.5,name:'Малёк',color:'#8ec8ea',scale:.48},{value:2,name:'Окунь',color:'#72c8a6',scale:.7},{value:5,name:'Щука',color:'#86b896',scale:.85},{value:10,name:'Золотая рыба',color:'#ffd17b',scale:.8},{value:55,name:'Жемчужина',color:'#c6a6ff',scale:.8}];
 const catchFor=info=>catches.find(c=>c.value===Number(info?.detail?.prize))||catches[0];
 function frame(info,t){
  t=clamp(t);const prize=catchFor(info),cast=ease(phase(t,0,.23)),sink=ease(phase(t,.23,.53)),haul=ease(phase(t,.73,.97));
  const rodAngle=-5*(1-cast)-8*haul,angle=rodAngle*Math.PI/180;
  const tip={x:44+184*Math.cos(angle)+65*Math.sin(angle),y:104+184*Math.sin(angle)-65*Math.cos(angle)};
  const float={x:tip.x+(271-tip.x)*cast-44*haul,y:tip.y+(128-tip.y)*cast-50*Math.sin(cast*Math.PI)};
  float.y+=t>.23&&t<.73?2*Math.sin(t*38)*Math.sin(phase(t,.23,.73)*Math.PI)+8*Math.sin(phase(t,.58,.73)*Math.PI):0;
  const hook={x:271-43*haul,y:139+164*sink-227*haul};
  if(t<.23){hook.x=float.x;hook.y=float.y+11;}
  if(t>.73){float.x=hook.x;float.y=Math.min(128,hook.y-11);}
  const attached=t>=.64&&prize.value>0;
  const approach=ease(phase(t,.47,.64)),mouth=42*prize.scale;
  const fish={x:attached?hook.x+mouth:443+(hook.x+mouth-443)*approach,y:attached?hook.y:303+9*Math.sin(t*27)*(1-approach),tail:Math.sin(t*64)*(attached?8:17),visible:prize.value>0&&t>=.47,scale:prize.scale};
  return {rodAngle,tip,float,hook,fish,attached,ripple:t>=.2&&t<.32?Math.sin(phase(t,.2,.32)*Math.PI):t>.64&&t<.8?Math.sin(phase(t,.64,.8)*Math.PI):0,haul,complete:t===1,status:t<.23?'Забрасываем…':t<.6?'Ждём поклёвку…':t<.73?prize.value?'Клюёт!':'Проверяем леску…':t<.97?'Поднимаем улов…':prize.value?prize.name+' · '+prize.value+'×':'Пустой заброс'};
 }
 function fishArt(prize,prefix){
  if(prize.value===55)return `<g><path d="M-40 0Q-45-31-21-35Q0-54 22-34Q44-30 40 0Z" fill="#8e73c7" stroke="#d8bcff" stroke-width="2"/><path d="M-29-24 0 2M-14-35 0 2M10-35 0 2M29-24 0 2" stroke="#c5a7ee" stroke-width="2"/><path d="M-43 1Q0-19 43 1Q31 29 0 32Q-29 29-43 1Z" fill="#bd9aec" stroke="#ebd5ff" stroke-width="2"/><circle cx="0" cy="-2" r="20" fill="url(#${prefix}-pearl)"/><circle cx="-6" cy="-9" r="5" fill="#fff" opacity=".8"/><path d="M-40 0H-32" stroke="#d8bcff" stroke-width="2"/></g>`;
  const pike=prize.value===5,gold=prize.value===10;
  return `<g transform="scale(-1 1)"><g data-fs-tail=""><path d="M-24 0Q-45-28-53-18L-46 0-53 20Q-42 27-23 1Z" fill="${prize.color}" stroke="#344868" stroke-width="1.1"/><path d="M-43-11-29 0-43 12" stroke="#fff" opacity=".25" fill="none"/></g><path d="M-17-10Q-10-${gold?43:31} 7-18L20-10Z" fill="${prize.color}" opacity=".8"/><path d="M-10 12Q3 35 16 14" fill="${prize.color}" opacity=".7"/><path d="M-30 0C-19-${pike?17:27} 23-${pike?17:28} 42 0C23 ${pike?16:25}-16 ${pike?17:27}-30 0Z" fill="url(#${prefix}-fish)" stroke="${prize.color}" stroke-width="1.2"/>${prize.value===2?'<path d="M-16-13-10 13M-3-17 3 16M10-16 15 12" stroke="#2b7771" stroke-width="5" opacity=".6"/>':''}<path d="M-19 5Q7 23 32 5Q9 16-19 5" fill="#fff4e4" opacity=".4"/><path d="M13-12Q4 0 14 11" stroke="#3e4e63" opacity=".45" fill="none"/><path d="M3 2Q-9 13-10 0Z" fill="#fff2dc" opacity=".45"/><circle cx="27" cy="-5" r="5" fill="#fff6e9"/><circle cx="29" cy="-5" r="2.8" fill="#172136"/><circle cx="29.5" cy="-6.1" r=".9" fill="#fff"/><path d="M37 1H42" stroke="#243148" stroke-width="1.3" stroke-linecap="round"/></g>`;
 }
 function board(info,animating){
  const done=info?.phase==='done'&&!animating,prize=catchFor(info),p='fs';
  return `<div class="fs-scene"><svg class="fs-water" viewBox="0 0 400 386" role="img" aria-label="Удочка, поплавок и улов"><defs><linearGradient id="fs-depth" x2="0" y2="1"><stop stop-color="#24465c" stop-opacity=".7"/><stop offset=".55" stop-color="#172e49" stop-opacity=".55"/><stop offset="1" stop-color="#111329" stop-opacity="0"/></linearGradient><linearGradient id="fs-rod" x2=".7" y2="1"><stop stop-color="#d2bdff"/><stop offset="1" stop-color="#7d65b5"/></linearGradient><linearGradient id="fs-fish" x2=".2" y2="1"><stop stop-color="${prize.color}"/><stop offset=".5" stop-color="${prize.color}"/><stop offset="1" stop-color="#f4e7db"/></linearGradient><radialGradient id="fs-pearl" cx=".3" cy=".25"><stop stop-color="#fff"/><stop offset=".65" stop-color="#e5e4ff"/><stop offset="1" stop-color="#a2a3d3"/></radialGradient><linearGradient id="fs-shores"><stop stop-color="#000"/><stop offset=".08" stop-color="#fff"/><stop offset=".92" stop-color="#fff"/><stop offset="1" stop-color="#000"/></linearGradient><mask id="fs-fade"><rect width="400" height="386" fill="url(#fs-shores)"/></mask></defs><g mask="url(#fs-fade)">
   <path d="M0 127Q55 119 105 129T210 127T315 128T400 125V386H0Z" fill="url(#fs-depth)"/><path d="M7 127Q55 119 105 129T210 127T315 128T392 126" stroke="#79bebf" stroke-width="1.2" fill="none" opacity=".4"/>
   <g fill="none" stroke="#60999f" opacity=".16" stroke-linecap="round"><path d="M35 165q22-5 42 0m196 18q28-5 55 0M90 223q27-5 40 0M185 315q27-5 51 0"/><circle cx="62" cy="277" r="3"/><circle cx="337" cy="255" r="4"/><circle cx="328" cy="276" r="2"/></g>
   <g fill="#365c74" opacity=".27"><path d="M38 244q24-21 49 0-25 19-49 0l-14 9v-18Z"/><path d="M260 327q24-18 45 0-21 17-45 0l-13 8v-16Z"/></g>
   <path d="M22 354q11-35 3-67m1 43q-17-18-20-30m21 11q19-28 16-45M376 360q-9-46 5-71m-8 48q-15-26-12-45" stroke="#386371" stroke-width="4" fill="none" opacity=".4" stroke-linecap="round"/>
   </g><g data-fs-rod="" transform="rotate(0 44 104)"><path d="M44 104Q113 5 228 39" fill="none" stroke="#493b72" stroke-width="7" stroke-linecap="round"/><path d="M44 102Q114 8 228 39" fill="none" stroke="url(#fs-rod)" stroke-width="4" stroke-linecap="round"/><path d="M42 106 64 79" stroke="#ac83bf" stroke-width="12" stroke-linecap="round"/><path d="M46 102 62 82" stroke="#d8a5c8" stroke-width="3" stroke-linecap="round"/><circle cx="56" cy="112" r="11" fill="#8a77ad" stroke="#d5c6ef" stroke-width="2"/><circle cx="56" cy="112" r="5" fill="#2c2948"/><path d="M65 114 73 119" stroke="#c5adf1" stroke-width="3" stroke-linecap="round"/></g>
   <path data-fs-line="" d="M228 39 271 128 271 139" fill="none" stroke="#b8cbd1" stroke-width="1" opacity=".85"/>
   <ellipse data-fs-ripple="" cx="271" cy="131" rx="20" ry="5" fill="none" stroke="#a2ded9" stroke-width="1.5" opacity="0"/>
   <g data-fs-float="" transform="translate(271 128)"><ellipse cy="3" rx="10" ry="3" fill="#132036" opacity=".4"/><path d="M0-17V-8" stroke="#eac9e0" stroke-width="1.5"/><path d="M-5 0Q-7-11 0-11Q7-11 5 0Z" fill="#ef7b9a"/><path d="M-5 0H5Q5 8 0 10Q-5 8-5 0Z" fill="#fff2ef"/></g>
   <path data-fs-hook="" d="M271 133v8q0 8 6 7q5-1 3-8" fill="none" stroke="#d2b8df" stroke-width="1.8" stroke-linecap="round"/>
   <g data-fs-fish="" visibility="hidden">${fishArt(prize,p)}</g>
  </svg><div class="fs-status" role="status" aria-live="polite"><b>${done?prize.value?prize.name+' · '+prize.value+'×':'Пустой заброс':animating?'Забрасываем…':'Что принесёт следующий заброс?'}</b><small>${done?'Улов определён':animating?'':'Пять видов улова'}</small></div><div class="fs-catches" aria-label="Коэффициенты улова">${catches.slice(1).map(c=>`<span title="${c.name}" class="${done&&prize.value===c.value?'is-current':''}" style="--catch:${c.color}"><i></i><b>${c.value}×</b></span>`).join('')}</div></div>`;
 }
 function paint(host,info,t){
  const f=frame(info,t),set=(s,k,v)=>host.querySelector(s)?.setAttribute(k,String(v));
  set('[data-fs-rod]','transform',`rotate(${f.rodAngle} 44 104)`);
  set('[data-fs-line]','d',`M${f.tip.x} ${f.tip.y} Q${(f.tip.x+f.float.x)/2} ${(f.tip.y+f.float.y)/2+4*(1-f.haul)} ${f.float.x} ${f.float.y} L${f.hook.x} ${f.hook.y}`);
  set('[data-fs-float]','transform',`translate(${f.float.x} ${f.float.y})`);
  set('[data-fs-hook]','d',`M${f.hook.x} ${f.hook.y-5}v8q0 7 5 6q5-1 3-7`);
  set('[data-fs-fish]','visibility',f.fish.visible?'visible':'hidden');
  set('[data-fs-fish]','transform',`translate(${f.fish.x} ${f.fish.y}) scale(${f.fish.scale})`);
  set('[data-fs-tail]','transform',`rotate(${f.fish.tail} -26 0)`);
  set('[data-fs-ripple]','rx',18+22*f.ripple);set('[data-fs-ripple]','opacity',f.ripple*.65);
  const label=host.querySelector('.fs-status b');if(label&&t>0&&t<1)label.textContent=f.status;
 }
 const api={frame,board,paint,catchFor,catches};if(typeof module==='object'&&module.exports)module.exports=api;else root.FishingScene=api;
})(globalThis);
