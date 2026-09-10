'use strict';
const AbyssFX=(()=>{
 let frames=new Set(),timers=new Set(),counterFinish=null,done=null;
 const reduced=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 function later(fn,ms){const id=setTimeout(()=>{timers.delete(id);fn();},ms);timers.add(id);}
 function clear(){for(const id of frames)cancelAnimationFrame(id);frames.clear();for(const id of timers)clearTimeout(id);timers.clear();document.querySelectorAll('.ax-spin-win,.ax-win-lines,.ax-celebration,.ax-feature-toast').forEach(n=>n.remove());counterFinish=null;done=null;}
 function count(node,total,duration,complete=()=>{}){
  const start=performance.now();let stopped=false,id=0;
  const finish=()=>{if(stopped)return;stopped=true;cancelAnimationFrame(id);frames.delete(id);node.textContent=money(total);complete();};
  const tick=now=>{frames.delete(id);if(stopped||!node.isConnected)return;const t=reduced()?1:Math.min(1,(now-start)/duration);node.textContent=money(Math.round(total*t));if(t===1){finish();return;}id=requestAnimationFrame(tick);frames.add(id);};
  id=requestAnimationFrame(tick);frames.add(id);return finish;
 }
 function spinWin(info){
  const box=document.querySelector('.ax-window');if(!box||!info.detail?.win)return;
  const win=info.detail.win,ratio=win/info.unitBet;
  const node=document.createElement('div');node.className='ax-spin-win'+(ratio<1?' is-small':'');node.innerHTML=`<small>${ratio<1?'Выплата':'Выигрыш'}</small><b></b>`;box.appendChild(node);count(node.querySelector('b'),win,700);later(()=>node.remove(),turboDuration());
  const lines=(info.detail.lines||[]).slice(0,6);if(lines.length){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('ax-win-lines');svg.setAttribute('viewBox','0 0 500 300');svg.setAttribute('preserveAspectRatio','none');svg.innerHTML=lines.map((l,i)=>`<polyline style="--delay:${i*.3}s" points="${l.cells.map(c=>`${c%5*100+50},${Math.floor(c/5)*100+50}`).join(' ')}"/>`).join('');box.appendChild(svg);later(()=>svg.remove(),2600);}
 }
 function turboDuration(){return reduced()?900:1800;}
 function feature(text){const box=document.querySelector('.ax-scene');if(!box)return;const n=document.createElement('div');n.className='ax-feature-toast';n.textContent=text;box.appendChild(n);later(()=>n.remove(),2000);}
 function celebrate(info,kind,onDone){
  clear();done=onDone;const total=kind==='summary'?info.payout:info.detail.win,ratio=total/info.unitBet;
  const title=kind==='summary'?'Бонус завершён':ratio>=500?'EPIC WIN':ratio>=100?'MEGA WIN':'BIG WIN';
  const overlay=document.createElement('div');overlay.className='ax-celebration';overlay.dataset.ax='finish-win';overlay.innerHTML=`<section role="dialog" aria-modal="true" aria-label="${title}"><div class="ax-bonus-rays" aria-hidden="true"></div><div class="ax-bonus-particles" aria-hidden="true">${Array.from({length:18},(_,i)=>`<i style="--i:${i}"></i>`).join('')}</div><h2>${title}</h2><strong class="ax-total-count" style="--amount-size:${Math.min(18,135/money(total).length)}vw">${money(0)}</strong><span class="ax-total-x" hidden>${Number(ratio.toFixed(2))}×</span>${kind==='summary'?`<p>Бесплатных вращений: ${info.bonus.played}</p>`:''}<button type="button" data-ax="finish-win" class="ax-confirm">Нажмите, чтобы показать сумму</button><small></small></section>`;
  document.getElementById('screen-ag').appendChild(overlay);const button=overlay.querySelector('button');counterFinish=count(overlay.querySelector('.ax-total-count'),total,kind==='summary'?12000:9000,()=>{counterFinish=null;overlay.querySelector('.ax-total-x').hidden=false;button.textContent='Нажмите, чтобы продолжить';});button.focus();

 }
 function finish(){if(counterFinish){counterFinish();return false;}const callback=done;clear();callback?.();return true;}
 return {clear,spinWin,feature,celebrate,finish};
})();
