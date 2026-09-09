'use strict';
/* Presentation only: every pump and burst follows the saved server result. */
(function(root){
 const clamp=n=>Math.max(0,Math.min(1,n)),smooth=n=>{n=clamp(n);return n*n*(3-2*n);};
 function frame(info,previous,t){
  t=clamp(t);const before=previous?.step||0,after=info.step||0,burst=info.last?.safe===false;
  const pumping=burst||after>before,stroke=pumping?(t>=.72?0:Math.sin(Math.PI*clamp(t/.72))):0;
  const step=before+((burst?before+1:after)-before)*smooth((t-.08)/.48);
  return {scale:.84+.0064*Math.min(25,step),pump:stroke*55,sway:pumping?Math.sin(t*Math.PI*4)*(1-t)*1.8:0,burst:burst&&t>=.66,progress:t===1?1:clamp((t-.66)/.34)};
 }
 function board(info,animating,locked,coefficients=[],previous=null){
  const live=info?.phase==='play',done=info?.phase==='done'&&!animating;
  const shown=animating?previous:info,step=shown?.step||0,lost=done&&info.last?.safe===false;
  const values=[1,...(info?.coefficients||coefficients)],number=n=>Number(n).toFixed(2).replace('.',',');
  const steps=values.map((value,i)=>`<div role="listitem" class="bl-step ${i===step&&!lost?'is-current':''} ${lost&&i===step+1?'is-lost':''}" ${i===step&&!lost?'aria-current="step"':''} data-bl-step="${i}"><small>${i?'Шаг '+i:'Старт'}</small><b>${number(value)}×</b></div>`).join('');
  return `<div class="bl-panel"><svg class="bl-scene" viewBox="0 0 360 390" role="img" aria-label="Воздушный шар с ручным насосом"><defs>
   <radialGradient id="bl-room"><stop stop-color="#234e87"/><stop offset="1" stop-color="#08162b"/></radialGradient>
   <radialGradient id="bl-latex" cx="32%" cy="23%" r="80%"><stop stop-color="#a0d4ff"/><stop offset=".18" stop-color="#5ba7ff"/><stop offset=".40" stop-color="#2188fc"/><stop offset=".64" stop-color="#086cdd"/><stop offset=".84" stop-color="#0756b5"/><stop offset="1" stop-color="#092d62"/></radialGradient>
   <linearGradient id="bl-chrome"><stop stop-color="#0b1828"/><stop offset=".2" stop-color="#7e98b4"/><stop offset=".33" stop-color="#ebf4ff"/><stop offset=".46" stop-color="#60748d"/><stop offset=".65" stop-color="#172536"/><stop offset=".85" stop-color="#afc2d5"/><stop offset="1" stop-color="#21354d"/></linearGradient>
   <linearGradient id="bl-body"><stop stop-color="#091c38"/><stop offset=".32" stop-color="#255b9e"/><stop offset=".47" stop-color="#3e79b8"/><stop offset=".64" stop-color="#123767"/><stop offset="1" stop-color="#06152d"/></linearGradient>
   <linearGradient id="bl-grip" x2="0" y2="1"><stop stop-color="#53647a"/><stop offset=".22" stop-color="#26364a"/><stop offset=".75" stop-color="#0a1423"/><stop offset="1" stop-color="#2e3d50"/></linearGradient>
   <filter id="bl-soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4"/></filter><linearGradient id="bl-shine" x2="100%" y2="100%"><stop stop-color="#fff" stop-opacity=".85"/><stop offset="1" stop-color="#d7edff" stop-opacity="0"/></linearGradient>
   <radialGradient id="bl-gloss"><stop stop-color="#f1f9ff" stop-opacity=".9"/><stop offset=".55" stop-color="#c9e8ff" stop-opacity=".35"/><stop offset="1" stop-color="#b0dfff" stop-opacity="0"/></radialGradient><linearGradient id="bl-floor" x2="0" y2="100%"><stop stop-color="#102844"/><stop offset="1" stop-color="#071325"/></linearGradient><radialGradient id="bl-shadow"><stop stop-color="#020915" stop-opacity=".9"/><stop offset="1" stop-color="#020915" stop-opacity="0"/></radialGradient>
  </defs><rect width="360" height="390" fill="url(#bl-room)"/><path d="M0 325Q180 300 360 325V390H0Z" fill="url(#bl-floor)"/>
  <ellipse cx="130" cy="350" rx="103" ry="20" fill="url(#bl-shadow)"/><ellipse cx="278" cy="354" rx="66" ry="19" fill="url(#bl-shadow)"/>
  <path d="M131 286C129 328 174 366 214 346S248 330 260 332" fill="none" stroke="#030e1d" stroke-width="8"/><path d="M131 286C129 328 174 366 214 346S248 330 260 332" fill="none" stroke="#3e6487" stroke-width="3"/>
  <g id="bl-balloon"><path d="M131 284C113 268 38 222 29 149C18 68 62 19 128 18C199 16 242 72 231 149C222 218 150 268 131 284Z" fill="url(#bl-latex)" stroke="#56a3f1" stroke-opacity=".6" stroke-width="1.2"/>
  <ellipse cx="76" cy="75" rx="24" ry="49" transform="rotate(37 76 75)" fill="url(#bl-gloss)"/><path d="M48 101C50 77 74 49 98 42C85 56 65 79 61 104Z" fill="url(#bl-shine)" filter="url(#bl-soft)"/><path d="M216 109C227 155 208 192 191 211L188 186C202 164 205 142 200 114Z" fill="url(#bl-shine)" filter="url(#bl-soft)" opacity=".55"/>
  <path d="M35 135C26 74 62 28 113 22" fill="none" stroke="#c3e6ff" stroke-opacity=".45" stroke-width="1.5"/><ellipse cx="208" cy="143" rx="9" ry="34" fill="url(#bl-gloss)" opacity=".4"/><path d="M129 263L131 283 138 267M119 261L131 283" fill="none" stroke="#79bcff" stroke-opacity=".25"/>
  <path d="M127 283L135 283 138 292Q131 295 124 292Z" fill="#167be0" stroke="#73b9fc"/><ellipse cx="131" cy="283" rx="5" ry="2" fill="#184c88"/></g>
  <g id="bl-fragments" opacity="0">${Array.from({length:16},(_,i)=>`<path data-bl-piece="${i}" d="M-8-4Q0-12 10-2L2 8-5 3Z" fill="${['#3398ff','#126ce0','#8ac5ff','#0750ad'][i%4]}"/>`).join('')}</g>
  <g id="bl-handle"><rect x="274" y="103" width="8" height="129" rx="3" fill="url(#bl-chrome)"/><rect x="239" y="95" width="79" height="12" rx="5" fill="url(#bl-chrome)"/><rect x="231" y="90" width="31" height="23" rx="6" fill="url(#bl-grip)" stroke="#6f8096" stroke-width=".6"/><rect x="294" y="90" width="31" height="23" rx="6" fill="url(#bl-grip)" stroke="#6f8096" stroke-width=".6"/></g>
  <path d="M252 344H304L316 352V359H240V352Z" fill="url(#bl-chrome)" stroke="#68809d"/><rect x="259" y="189" width="39" height="157" rx="4" fill="url(#bl-body)" stroke="#6e8aaa" stroke-width=".6"/>
  <rect x="257" y="185" width="43" height="13" rx="4" fill="url(#bl-chrome)"/><ellipse cx="278.5" cy="185" rx="21.5" ry="4" fill="url(#bl-chrome)"/><path d="M262 203V331M265 203V331" stroke="#a0c8ee" stroke-opacity=".15" stroke-width="1"/><rect x="260" y="199" width="3" height="132" rx="1.5" fill="#71a3d7" opacity=".35"/><rect x="257" y="336" width="43" height="10" rx="3" fill="url(#bl-chrome)"/><rect x="249" y="327" width="14" height="10" rx="3" fill="url(#bl-chrome)"/></svg>
  <div class="bl-readout"><div class="bl-steps" role="list" aria-label="Шаги и коэффициенты" tabindex="0">${steps}</div><span role="status" aria-live="polite">${animating?'Надуваем шар…':lost?'Шар лопнул · 0,00×':done?'Раунд завершён · '+number(info.multiplier??0)+'×':`Успешных качков: ${step}`}</span></div></div>${live?`<button type="button" class="cg-action bl-inflate" data-cg-pick="0" ${locked?'disabled':''}>${animating?'Надуваем…':'Надуть ещё'}</button>`:''}`;
 }
 function paint(host,info,previous,t){
  const f=frame(info,previous,t),ball=host.querySelector('#bl-balloon'),handle=host.querySelector('#bl-handle');
  if(!ball||!handle)return;
  ball.setAttribute('transform',`translate(131 286) rotate(${f.sway}) scale(${f.scale} ${f.scale*(1+.012*Math.sin(f.pump/55*Math.PI))}) translate(-131 -286)`);
  ball.setAttribute('opacity',f.burst?'0':'1');handle.setAttribute('transform',`translate(0 ${f.pump})`);
  host.querySelector('#bl-fragments')?.setAttribute('opacity',f.burst?String(1-f.progress):'0');
  for(let i=0;i<16;i++){const a=i*Math.PI*2/16,p=f.progress,r=20+p*(75+i%4*17),x=131+Math.cos(a)*r,y=155+Math.sin(a)*r+p*p*155;
   host.querySelector(`[data-bl-piece="${i}"]`)?.setAttribute('transform',`translate(${x} ${y}) rotate(${i*29+p*(i%2?320:-290)}) scale(${1-p*.55})`);
  }
 }
 const api={board,paint,frame};if(typeof module==='object'&&module.exports)module.exports=api;else root.BalloonScene=api;
})(globalThis);
