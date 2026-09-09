'use strict';
/* Native SVG: the visible zone radii are the same as the server's area thresholds. */
(function(root){
 const rules=typeof module==='object'&&module.exports?require('./darts-rules'):root.DartsRules;
 const zones=rules.bands;
 const label=n=>String(Number(Number(n).toFixed(2))).replace('.',',')+'×';
 const zone=value=>zones.find(z=>z.value===value)||zones[0];
 function history(info){
  const items=(info?.history||[]).slice(0,4).reverse();
  return Array.from({length:4},(_,i)=>{
   const item=items[i-(4-items.length)],latest=item&&i===3,c=latest?zone(item.multiplier).color:'#28364f';
   return `<g transform="translate(294 ${80+i*40})"><rect width="52" height="36" rx="10" fill="${c}"/><text x="26" y="23" text-anchor="middle" fill="${latest&&item.multiplier>=1?'#171c31':'#eff3ff'}" font-size="13" font-weight="700">${item?label(item.multiplier):'—'}</text></g>`;
  }).join('');
 }
 function legends(value){return zones.map((z,i)=>`<g transform="translate(${12+i*57} 328)"><rect width="51" height="44" rx="12" fill="${value===z.value?'#334561':'#242f47'}" stroke="${value===z.value?z.color:'#3e4d68'}" stroke-width="${value===z.value?1.8:1}"/><rect x="8" y="37" width="35" height="3" rx="1.5" fill="${z.color}"/><text x="25.5" y="26" text-anchor="middle" fill="#f1f4ff" font-size="16" font-weight="700">${label(z.value)}</text></g>`).join('');}
 // The local origin is the embedded tip; the body projects toward the viewer.
 const dart=`<ellipse cx="3" cy="4" rx="5" ry="2.5" fill="#060d20" opacity=".55"/><path d="M0 0 0 9" stroke="#dce9f6" stroke-width="2.2" stroke-linecap="round"/><path d="M-3 8Q0 5 3 8L4 28Q0 32-4 28Z" fill="#506789" stroke="#c1d5ea" stroke-width="1"/><path d="M-1 9V28" stroke="#edf6ff" stroke-width="1.8"/><path d="M-3 13H3M-3 17H3M-3 21H3M-3 25H3" stroke="#253c5e" stroke-width="1.2"/><path d="M0 30V42" stroke="#c6d8f1" stroke-width="3"/><path d="M0 37-12 46-10 58 0 52Z" fill="#5272db" stroke="#a5baff" stroke-width="1"/><path d="M0 37 12 46 10 58 0 52Z" fill="#95b1ff" stroke="#d1deff" stroke-width="1"/><path d="M0 37V57" stroke="#e4edff" stroke-width="2"/>`;
 function flightMarkup(id="single"){return `<g data-dt-flight="${id}"><circle data-dt-impact="" visibility="hidden" opacity="0" r="4" fill="none" stroke="#eef5ff" stroke-width="1.5"/><g data-dt-dart="" visibility="hidden" opacity="0">${dart}</g></g>`;}
 function svg(info){return `<svg class="dt-scene" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 386" role="img" aria-label="Мишень: от края к центру 0,4; 0,6; 1,3; 3,1; 6 и 16 икс" font-family="Arial, sans-serif"><defs><radialGradient id="dt-rim"><stop stop-color="#5a6e96"/><stop offset="1" stop-color="#354562"/></radialGradient></defs><ellipse cx="150" cy="159" rx="131" ry="130" fill="#0c142b" opacity=".6"/><circle cx="150" cy="151" r="130" fill="url(#dt-rim)"/><circle cx="150" cy="151" r="121" fill="#0e182c"/><g>${zones.map(z=>`<circle cx="150" cy="151" r="${119*z.radius}" fill="${z.color}"/>`).join('')}</g><circle cx="150" cy="151" r="119" fill="none" stroke="#7488b2" stroke-opacity=".35"/><g data-dt-history="">${history(info)}</g><g data-dt-legends="">${legends(info?.phase==='done'?info.multiplier:null)}</g>${flightMarkup()}</svg>`;}
 const speaker=`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path class="dt-sound-wave" d="M16 8q4 4 0 8m3-11q7 7 0 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path class="dt-sound-off" d="m17 9 5 6m0-6-5 6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>`;
 function board(info,sound){return `<div class="dt-panel"><div class="dt-toolbar"><span>Один бросок — один результат</span><button type="button" class="dt-sound" data-dt-sound aria-pressed="${Boolean(sound)}" aria-label="${sound?'Выключить':'Включить'} звук">${speaker}</button></div>${svg(info)}</div>`;}
 function paint(stage,f,info){
  if(info.detail?.rules!==rules.version)return;
  const set=(selector,attrs)=>{const n=stage.querySelector(selector);if(n)for(const [key,value]of Object.entries(attrs))n.setAttribute(key,String(value));};
  set('[data-dt-dart]',{visibility:f.opacity?'visible':'hidden',opacity:f.opacity,transform:`translate(${f.x} ${f.y}) rotate(${f.rotation}) scale(${f.scale})`});
  set('[data-dt-impact]',{visibility:f.hit&&f.ripple<1?'visible':'hidden',cx:f.x,cy:f.y,r:4+18*f.ripple,opacity:f.hit?1-f.ripple:0});
  const root=stage.querySelector('.dt-panel');
  if(root&&f.hit&&root.dataset.revealed!==String(info.revision)){
   const h=stage.querySelector('[data-dt-history]'),l=stage.querySelector('[data-dt-legends]');
   if(h)h.innerHTML=history(info);if(l)l.innerHTML=legends(info.multiplier);
   root.dataset.revealed=String(info.revision);
  }
 }
 const api={board,svg,paint,zones,history,legends,label,flightMarkup};
 if(typeof module==='object'&&module.exports)module.exports=api;else root.DartsScene=api;
})(globalThis);
