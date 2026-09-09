'use strict';
(function(root){
 const clamp=n=>Math.max(0,Math.min(1,n)),ease=n=>{n=clamp(n);return n*n*(3-2*n);};
 const carColors=['#6796ff','#f47792','#ad9be8','#ffd271'];
 const geometry={finishY:110,nose:72,startY:370,lanes:[0,1,2,3]};
 function frame(info,t){
  t=clamp(t);const order=info.detail?.order||[0,1,2,3],u=clamp((t-.19)/.81);
  const cars=geometry.lanes.map(i=>{
   const rank=Math.max(0,order.indexOf(i)),end=1.25-rank*.055;
   // The crossing is measured at the nose, in the same coordinates as the art.
   const distance=end*ease(u)+.14*Math.sin(u*Math.PI*4+i)*u*u*(1-u)*(1-u);
   const scale=1-.4*distance,y=geometry.startY-(geometry.startY-geometry.finishY-geometry.nose*.6)*distance;
   return {x:200+(i-1.5)*(83-24*distance),y,scale,distance,noseY:y-geometry.nose*scale,finished:distance>=1,wheel:u>0&&u<1?Math.sin(u*240+i)*.35*Math.sin(u*Math.PI):0};
  });
  return {cars,started:t>=.19,complete:t===1,countdown:t<.19?Math.max(1,3-Math.floor(t/.064)):0};
 }
 function fallbackCar(color){return `<g><rect x="-29" y="-48" width="12" height="35" rx="5" fill="#080d1c"/><rect x="17" y="-48" width="12" height="35" rx="5" fill="#080d1c"/><path d="M-24-4V-51Q-23-72 0-72Q23-72 24-51V-4Q0 5-24-4" fill="${color}" stroke="#adc7ff" stroke-width="1.2"/><path d="M-17-49Q0-61 17-49L19-30H-19Z" fill="#172542"/><path d="M-4-70H4V-5H-4Z" fill="#e3ddff"/><rect x="-28" y="-15" width="56" height="6" rx="3" fill="${color}" stroke="#bcc8fa"/><path d="M-18-7h8m20 0h8" stroke="#ff687b" stroke-width="4" stroke-linecap="round"/></g>`;}
 function board(info,animating,side){
  const done=info?.phase==='done'&&!animating,selected=Number(side)||0;
  return `<div class="rc-scene"><div class="rc-heading"><span>${done?'Финиш':animating?'Заезд':'Выберите машину'}</span><b>3.92× <small>· 25%</small></b></div><svg class="rc-track" viewBox="0 0 400 410" role="img" aria-label="Четыре машины на трассе. Выбрана машина ${selected+1}."><defs><linearGradient id="rc-asphalt" x2="0" y2="1"><stop stop-color="#1b2039"/><stop offset="1" stop-color="#272c49"/></linearGradient><linearGradient id="rc-curb" x2="1" y2="0"><stop stop-color="#6558b1"/><stop offset=".5" stop-color="#b8acf1"/><stop offset="1" stop-color="#403965"/></linearGradient><pattern id="rc-checks" width="16" height="16" patternUnits="userSpaceOnUse"><rect width="16" height="16" fill="#ece9fc"/><path d="M0 0H8V8H0ZM8 8H16V16H8Z" fill="#292943"/></pattern>${[0,1,2,3].map(n=>`<filter id="rc-paint-${n}" color-interpolation-filters="sRGB"><feColorMatrix type="hueRotate" values="${[0,120,40,195][n]}"/></filter>`).join('')}</defs>
   <path d="M101 55H299L393 390Q200 409 7 390Z" fill="#090d1c"/>
   <path d="M107 49H293L383 379Q200 396 17 379Z" fill="url(#rc-asphalt)"/>
   <path d="M106 49 15 379M294 49 385 379" fill="none" stroke="url(#rc-curb)" stroke-width="7"/>
   <path d="M106 49 15 379M294 49 385 379" fill="none" stroke="#d2c9ed" stroke-width="5" stroke-dasharray="13 17" opacity=".5"/>
   ${[1,2,3].map(i=>`<path d="M${108+i*46} 49 ${17+i*91.5} 380" stroke="#687092" stroke-width="2" stroke-dasharray="12 17" opacity=".55"/>`).join('')}
   <path d="M91 104H309L313 116H87Z" fill="url(#rc-checks)" opacity=".95"/>
   <path d="M95 97V76H305V97" fill="none" stroke="#9984e7" stroke-width="4" stroke-linecap="round"/>
   <g class="rc-lights">${[0,1,2].map(i=>`<circle data-rc-light="${i}" cx="${185+i*15}" cy="78" r="4" fill="#3c3455"/>`).join('')}</g>
   ${geometry.lanes.map(i=>`<g data-rc-car="${i}" class="rc-car${i===selected?' is-selected':''}"><ellipse cx="0" cy="-3" rx="30" ry="9" fill="#050916" opacity=".45"/><g class="rc-car-fallback">${fallbackCar(carColors[i])}</g><image class="rc-car-image" href="/img/race/car-v2.webp" x="-35" y="-72" width="70" height="77" preserveAspectRatio="none" filter="url(#rc-paint-${i})"/><g transform="translate(0 15)"><rect x="-13" y="-8" width="26" height="17" rx="7" fill="${i===selected?'#8b75ed':'#171b34'}" stroke="${carColors[i]}"/><text y="4" text-anchor="middle" fill="#fff" font-family="Inter,Arial" font-size="11" font-weight="700">${i+1}</text></g></g>`).join('')}
   <text class="rc-countdown" data-rc-countdown="" x="200" y="230" text-anchor="middle"></text>
  </svg><div class="rc-race-status" role="status" aria-live="polite">${animating?'На старт…':done?'Первым финишировал №'+(info.detail.winner+1):'Ваша машина: №'+(selected+1)}</div><div class="rc-order" aria-label="Порядок финиша">${done?info.detail.order.map((n,i)=>`<span style="--car-color:${carColors[n]}" class="${n===selected?'is-selected':''}"><small>${i+1}</small><i></i>№${n+1}</span>`).join(''):geometry.lanes.map(i=>`<span class="rc-order-empty">${i+1}<small>—</small></span>`).join('')}</div></div>`;
 }
 function paint(host,info,t){
  const f=frame(info,t);f.cars.forEach((c,i)=>host.querySelector(`[data-rc-car="${i}"]`)?.setAttribute('transform',`translate(${c.x} ${c.y+c.wheel}) scale(${c.scale})`));
  const count=host.querySelector('[data-rc-countdown]');if(count)count.textContent=t>0&&t<.27?f.countdown||'GO':'';
  for(let i=0;i<3;i++)host.querySelector(`[data-rc-light="${i}"]`)?.setAttribute('fill',t===0?'#3c3455':f.started?'#68e9a4':3-f.countdown>=i?'#ef7591':'#3c3455');
  const status=host.querySelector('.rc-race-status');if(status&&t>0&&t<1)status.textContent=f.started?'Заезд идёт…':'На старт…';
 }
 // A native fallback prevents an image loading failure from locking a wager.
 if(root.Image){const img=new root.Image();img.onload=()=>root.document?.documentElement.classList.add('race-sprite-ready');img.src='/img/race/car-v2.webp';}
 const api={frame,board,paint,geometry,carColors,ready:()=>true,loadingLabel:()=>''};if(typeof module==='object'&&module.exports)module.exports=api;else root.RaceScene=api;
})(globalThis);
