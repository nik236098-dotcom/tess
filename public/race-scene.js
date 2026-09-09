'use strict';
(function(root){
 let loaded=0,failed=false;
 if(root.Image)for(const name of ['track','cars']){const asset=new root.Image();asset.onload=()=>{loaded++;root.document?.getElementById('ag-stage')?.dispatchEvent(new root.Event('raceready'));};asset.onerror=()=>{failed=true;root.document?.getElementById('ag-stage')?.dispatchEvent(new root.Event('raceready'));};asset.src='/img/race/'+name+'.webp';}
 const ready=()=>loaded===2&&!failed;
 const loadingLabel=()=>failed?'Не загрузилась трасса — переоткрой приложение':'Загружаем трассу…';
 const clamp=n=>Math.max(0,Math.min(1,n));
 function frame(info,t){
  t=clamp(t);const order=info.detail?.order||[0,1,2,3];
  return {cars:[0,1,2,3].map(i=>{
   const rank=order.indexOf(i),finish=.72+rank*.065,run=clamp((t-.12)/(finish-.12));
   // Monotonic acceleration, then a short run beyond the finish in server order.
   const distance=run*run*(2-run),after=clamp((t-finish)/(1-finish));
   const y=510-320*distance-after*(72-rank*14),scale=1-.34*distance-.035*after;
   const lane=i-1.5,x=512+lane*(198-75*distance);
   return {x,y,scale,finished:t>=finish,wheel:t>.12&&t<1?Math.sin(t*180+i)*.8:0};
  }),started:t>=.12,complete:t===1};
 }
 function board(info,animating,side){
  const done=info?.phase==='done'&&!animating;
  return `<div class="rc-scene"><svg class="rc-track" viewBox="0 80 1024 890" role="img" aria-label="Четыре игрушечные машины на гоночной трассе"><defs><clipPath id="rc-car-cut" transform="translate(130 160) scale(.95 .965) translate(-130 -160)"><path d="M131 52C95 51 69 55 61 69Q57 81 56 98L48 100Q35 102 35 126L34 151Q35 163 45 164L43 179Q32 190 32 204L24 208Q19 212 19 237L20 252Q22 263 34 265L81 265Q89 273 104 265L158 265Q170 273 181 264L214 265Q228 265 231 251L232 221Q231 205 218 204L216 183 210 166Q227 166 228 153L228 124Q227 103 215 101L212 98Q211 77 204 67C190 55 161 51 131 52Z"/></clipPath></defs><image href="/img/race/track.webp" width="1024" height="1536"/>
   ${[0,1,2,3].map(i=>`<g data-rc-car="${i}"><ellipse cx="0" cy="230" rx="83" ry="15" fill="#04101e" opacity=".4"/><svg x="-128" y="0" width="256" height="280" viewBox="0 0 256 320" overflow="hidden"><g clip-path="url(#rc-car-cut)"><image x="${-i*256}" href="/img/race/cars.webp" width="1024" height="320" preserveAspectRatio="none"/></g></svg></g>`).join('')}
   </svg><div class="rc-race-status" role="status" aria-live="polite">${animating?'Заезд идёт…':done?'Первым финишировал №'+(info.detail.winner+1):'Выбери победителя'}</div></div>`;
 }
 function paint(host,info,t){const f=frame(info,t);f.cars.forEach((c,i)=>host.querySelector(`[data-rc-car="${i}"]`)?.setAttribute('transform',`translate(${c.x} ${c.y+c.wheel}) scale(${c.scale})`));}
 const api={frame,board,paint,ready,loadingLabel};if(typeof module==='object'&&module.exports)module.exports=api;else root.RaceScene=api;
})(globalThis);
