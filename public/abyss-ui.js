'use strict';
const AbyssUI=(()=>{
 const R=AbyssRules,idle=[0,1,8,2,3,4,5,6,7,0,2,9,3,1,6];
 let bet=20,turbo=false,running=false,entering=false,timer=0,ready=false,loading=false,failed=false,balance=0,returnFocus=null;
 const icon='<svg viewBox="0 0 64 64" aria-hidden="true"><path d="M49 23A20 20 0 1 0 51 39" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round"/><path d="m39 22 13 3-1-14" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
 const symbol=(n,win=false)=>`<div class="ax-cell${win?' is-win':''}${n===9?' is-scatter':''}"><img src="/img/abyss/${R.symbols[n].id}.webp" alt="${R.symbols[n].name}" draggable="false">${n===8||n===9?`<b class="ax-symbol-tag${n===9?' is-scatter':''}">${n===8?'WILD':'SCATTER'}</b>`:''}</div>`;
 function prefs(){try{localStorage.setItem('abyss-prefs',JSON.stringify({bet,turbo}));}catch{}}
 function assets(){
  if(loading||ready)return;loading=true;failed=false;
  Promise.all([...R.symbols.map(s=>s.id),'station'].map(name=>new Promise(resolve=>{const image=new Image();image.onload=()=>resolve(true);image.onerror=()=>resolve(false);image.src='/img/abyss/'+name+'.webp';}))).then(result=>{loading=false;ready=result.every(Boolean);failed=!ready;if(state.ag.game==='abyss')render(false);});
 }
 function prepare(){
  stop();try{const p=JSON.parse(localStorage.getItem('abyss-prefs')||'{}');if(R.stakes.includes(p.bet))bet=p.bet;turbo=p.turbo===true;}catch{}
  state.ag.options.abyss={buyBonus:false};balance=state.balance;$('ag-amount').value=(bet/100).toFixed(2);assets();
 }
 function stop(){running=false;entering=false;clearTimeout(timer);timer=0;close(false);}
 function controls(){
  const a=state.ag,info=a.info,bonus=info?.phase==='play',pending=info?.phase==='done'&&!info.settled,locked=agLocked()||entering;
  const value=bonus?info.unitBet:bet,price=bet*R.buyCost;
  return `<div class="ax-controls"><div class="ax-readout"><span>${bonus?'БОНУС · ОБЩИЙ ВЫИГРЫШ':'ВЫИГРЫШ'}<b>${money((a.animating?a.cgPrevious:info)?.payout||0)}</b></span><button type="button" data-ax="rules" class="ax-info" aria-label="Правила и выплаты">i</button></div><div class="ax-control-row"><div class="ax-bet"><small>${bonus?'БЕСПЛАТНЫЕ ВРАЩЕНИЯ':'СТАВКА ЗА ВРАЩЕНИЕ'}</small>${bonus?`<strong>${(a.animating?a.cgPrevious:info)?.bonus?.remaining??info.bonus.remaining} <em>осталось</em></strong>`:`<div><button type="button" data-ax="minus" aria-label="Уменьшить ставку" ${locked||pending||bet===R.stakes[0]?'disabled':''}>−</button><button type="button" data-ax="stake" class="ax-bet-value" ${locked||pending?'disabled':''}>${money(value)}<small>⌄</small></button><button type="button" data-ax="plus" aria-label="Увеличить ставку" ${locked||pending||bet===R.stakes.at(-1)?'disabled':''}>+</button></div>`}</div><button type="button" class="ax-spin${a.animating?' is-spinning':''}" data-ax="spin" aria-label="${pending?'Получить сохранённую выплату':bonus?'Продолжить бесплатные вращения':'Вращать за '+money(bet)}" ${locked||loading?'disabled':''}>${icon}</button><button type="button" data-ax="turbo" class="ax-turbo${turbo?' is-on':''}" aria-pressed="${turbo}" ${locked?'disabled':''}><span>ϟ</span>ТУРБО</button></div><div class="ax-footer"><button type="button" class="ax-buy" data-ax="buy" ${locked||bonus||pending||!ready?'disabled':''}><span>BONUS BUY</span><b>${money(price)}</b></button><span class="ax-control-note" role="status">${!state.connected?'Восстанавливаем связь…':loading?'Загружаем символы…':failed?'Нажмите ↻ для повторной загрузки':pending?'Выплата сохранена':a.pending?'Сохраняем вращение…':a.animating?'Погружение…':bonus?entering?'Три Scatter · бонус открыт':running?'Бонус идёт автоматически':'Нажмите ↻, чтобы продолжить':'20 линий · '+(turbo?'турбо':'обычная скорость')}</span></div></div>`;
 }
 function render(board=true){
  const a=state.ag,info=a.info;if(a.game!=='abyss')return;
  if(!a.animating)balance=state.balance;$('ag-balance').textContent=money(balance);
  $('ag-amount').value=(bet/100).toFixed(2);$('ag-paytable').innerHTML='';$('ag-settings').innerHTML=controls();
  $('ag-main').disabled=agLocked();$('ag-rules-text').textContent='Abyss Protocol: 5 барабанов, 3 ряда, 20 постоянных линий. Выплаты слева направо за 3–5 одинаковых символов; Wild заменяет любой символ, кроме Scatter. На каждой линии оплачивается одна лучшая комбинация. Ставка за линию — 1/20 общей ставки. Три и более Scatter дают 8 бесплатных вращений. В бонусе Wild встречается чаще, множитель начинается с 1× и после каждого выигрышного вращения растёт на 1, максимум 10×. Повторные 3 Scatter добавляют 4 вращения; за один бонус не более 40. Bonus Buy стоит 100 общих ставок: три Scatter на вводном вращении открывают тот же бонус; вводное вращение не даёт денежной выплаты. Максимальная общая выплата — 2500 ставок за вращение. Турбо влияет только на анимацию. Весь раунд и выплата сохраняются сервером.';
  if(!info||info.phase!=='done'||a.animating||a.pending?.action==='start')GameResult.hide($('ag-overlay'));
  if(!board)return;
  const visual=a.animating?a.cgPrevious:info,grid=info?.detail?.grid||idle,old=visual?.detail?.grid||idle;
  const wins=new Set(!a.animating?info?.detail?.lines?.flatMap(l=>l.cells)||[]:[]),bonus=visual?.bonus;
  if(!a.animating&&info?.detail?.triggered)grid.forEach((n,i)=>{if(n===R.scatter)wins.add(i);});
  const reels=[0,1,2,3,4].map(col=>{
   const result=[grid[col],grid[col+5],grid[col+10]],fill=18+col*3;
   const strip=a.animating?[...result,...Array.from({length:fill},(_,i)=>(i*7+col+Number(info.revision))%10),old[col],old[col+5],old[col+10]]:result;
   return `<div class="ax-reel"><div class="ax-strip" data-ax-reel="${col}" data-length="${strip.length}" style="transform:translateY(${a.animating?-(strip.length-3)/strip.length*100:0}%)">${strip.map((n,i)=>symbol(n,wins.has(i*5+col))).join('')}</div></div>`;
  }).join('');
  $('ag-stage').innerHTML=`<div class="ax-scene"><div class="ax-hero"><div class="ax-brand">ABYSS<span>PROTOCOL</span></div><div class="ax-water-light"></div></div><div class="ax-window"><div class="ax-grid" aria-label="Барабаны Abyss Protocol">${reels}</div></div><div class="ax-signal${visual?.phase==='play'?' is-active':''}"><div class="ax-sonar"><i></i></div><div><small>СИГНАЛ ИЗ ГЛУБИНЫ</small><b>${visual?.phase==='play'?'Бонус · '+(bonus?.remaining||0)+' вращений':'3 SCATTER открывают бонус'}</b><div class="ax-meter"><i style="width:${((bonus?.multiplier||1)-1)/9*100}%"></i></div></div><strong>${bonus?.multiplier||1}×</strong></div><p class="ax-scene-note">${a.animating?'':info?.detail?.capped?'Достигнут максимум 2500×':info?.detail?.triggered&&info.detail.bonusSpin?'+'+info.detail.triggered+' бесплатных вращения':info?.detail?.win?'За вращение '+money(info.detail.win):'Wild заменяет символы · Scatter запускает погружение'}</p></div>`;
  if(a.animating)paint(a.cgTime||0);
 }
 function paint(t){
  for(const el of $('ag-stage').querySelectorAll('[data-ax-reel]')){
   const col=Number(el.dataset.axReel),end=.62+col*.095,u=Math.min(1,t/end),progress=u<.12?u*u/.12:.12+2*(u-.12)-(u-.12)*(u-.12)/.88;
   const length=Number(el.dataset.length);el.style.transform=`translateY(${-(length-3)/length*100*(1-progress)}%)`;
   el.parentElement.classList.toggle('is-settled',u===1);el.classList.toggle('is-blurred',u>.06&&u<.83);
  }
 }
 function receive(message){
  const a=state.ag,previous=a.info,action=a.pending?.id===message.requestId?a.pending.action:null;
  if(action)a.pending=null;a.info=message;
  if(message.unitBet&&message.phase==='play')bet=message.unitBet;
  const changed=!previous||previous.revision!==message.revision;
  if(message.accepted===false){running=false;clearTimeout(timer);render();return;}
  if(changed&&(action==='start'||action==='pick')&&message.detail){a.cgPrevious=previous;a.animating=true;a.cgTime=0;render();animate();return;}
  render();if(message.phase==='done'&&changed)agResult();
 }
 function animate(){
  const a=state.ag,token=++a.token,start=performance.now(),reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches,duration=reduced?0:turbo?1050:2900;
  const tick=now=>{if(token!==a.token||a.game!=='abyss')return;const t=duration?Math.min(1,(now-start)/duration):1;a.cgTime=t;paint(t);if(t<1){a.raf=requestAnimationFrame(tick);return;}
   a.animating=false;a.cgTime=0;entering=!!(a.info.detail.triggered&&!a.info.detail.bonusSpin&&a.info.phase==='play');render();
   if(a.info.phase==='done'){running=false;agResult();return;}
   if(entering){running=false;timer=setTimeout(()=>{timer=0;entering=false;if(token!==a.token||a.game!=='abyss')return;render(false);show('bonus');},1200);return;}
   if(running&&!document.hidden)timer=setTimeout(()=>{timer=0;if(state.ag.game==='abyss'&&state.connected&&!agLocked())spin();},turbo?250:750);
  };a.raf=requestAnimationFrame(tick);
 }
 function spin(){
  if(state.ag.game!=='abyss'||agLocked()||entering)return;
  if(!ready){assets();return;}
  const info=state.ag.info;close(false);
  if(info.phase==='done'&&!info.settled){agOpenRequest();render(false);return;}
  if(info.phase==='play'){running=true;agRequest('pick',{index:0});return;}
  running=false;state.ag.options.abyss={buyBonus:false};agRequest('start');
 }
 function close(focus=true){const node=document.getElementById('ax-dialog');if(node)node.remove();if(focus)returnFocus?.focus();returnFocus=null;}
 function show(kind){
  close(false);returnFocus=document.activeElement;
  const info=state.ag.info;if(!info)return;
  let body='';
  if(kind==='stake')body=`<h2>Ставка за вращение</h2><p>Полная стоимость · все 20 линий</p><div class="ax-stakes">${R.stakes.map(n=>`<button type="button" data-ax-stake="${n}" aria-pressed="${n===bet}">${money(n)}</button>`).join('')}</div>`;
  else if(kind==='buy')body=`<img class="ax-dialog-art" src="/img/abyss/scatter.webp" alt=""><h2>Сигнал из глубины</h2><p>8 бесплатных вращений<br>Растущий множитель до 10×</p><div class="ax-price"><span>Ставка ${money(bet)} × 100</span><strong>${money(bet*R.buyCost)}</strong></div><p>Эта сумма будет списана с баланса. Покупка не гарантирует выигрыш.</p><button type="button" data-ax="confirm-buy" class="ax-confirm" ${bet*R.buyCost>state.balance?'disabled':''}>${bet*R.buyCost>state.balance?'Недостаточно средств':'Купить за '+money(bet*R.buyCost)}</button>`;
  else if(kind==='bonus')body=`<img class="ax-dialog-art" src="/img/abyss/scatter.webp" alt=""><h2>Сигнал обнаружен!</h2><p>Бесплатных вращений: <b>${info.bonus.remaining}</b><br>Выигрыши повышают множитель</p><button type="button" data-ax="spin" class="ax-confirm">Начать погружение</button>`;
  else body=`<h2>Символы и выплаты</h2><p>За 3 / 4 / 5 подряд слева направо.<br>Множители ниже — от ставки одной линии.</p><div class="ax-payments">${R.symbols.slice(0,9).map(s=>`<div><img src="/img/abyss/${s.id}.webp" alt=""><span>${s.name}</span><b>${s.pay.join(' / ')}×</b></div>`).join('')}</div><p>${$('ag-rules-text').textContent}</p>`;
  const overlay=document.createElement('div');overlay.id='ax-dialog';overlay.className='ax-dialog';overlay.innerHTML=`<section role="dialog" aria-modal="true" aria-label="${kind==='stake'?'Выбор ставки':kind==='buy'?'Покупка бонуса':'Abyss Protocol'}"><button type="button" class="ax-close" data-ax="close" aria-label="Закрыть">×</button>${body}</section>`;$('screen-ag').appendChild(overlay);overlay.querySelector('button:not(:disabled)')?.focus();
 }
 document.addEventListener('click',event=>{
  if(state.ag.game!=='abyss')return;const button=event.target.closest('[data-ax],[data-ax-stake]');if(!button||button.disabled)return;
  const action=button.dataset.ax;
  if(action==='close'){close();return;}if(action==='rules'){show('rules');return;}
  if(agLocked()||entering)return;
  if(action==='spin'){spin();return;}
  if(action==='turbo'){turbo=!turbo;prefs();render(false);return;}
  if(state.ag.info?.phase==='play'||state.ag.info?.settled===false)return;
  if(action==='stake'||action==='buy'){show(action);return;}
  if(action==='confirm-buy'){
   if(bet*R.buyCost>state.balance||!ready)return;
   close(false);running=false;state.ag.options.abyss={buyBonus:true};agRequest('start');return;
  }
  const index=R.stakes.indexOf(bet),chosen=button.dataset.axStake?Number(button.dataset.axStake):R.stakes[Math.max(0,Math.min(R.stakes.length-1,index+(action==='plus'?1:-1)))];
  if(R.stakes.includes(chosen)){bet=chosen;prefs();close();render(false);}
 });
 document.addEventListener('keydown',event=>{
  const dialog=document.getElementById('ax-dialog');if(!dialog)return;
  if(event.key==='Escape'){event.preventDefault();close();}
  if(event.key==='Tab'){const buttons=[...dialog.querySelectorAll('button:not(:disabled)')];if(event.shiftKey&&document.activeElement===buttons[0]){event.preventDefault();buttons.at(-1)?.focus();}else if(!event.shiftKey&&document.activeElement===buttons.at(-1)){event.preventDefault();buttons[0]?.focus();}}
 });
 document.addEventListener('visibilitychange',()=>{if(document.hidden){running=false;entering=false;clearTimeout(timer);timer=0;if(state.ag.game==='abyss')render(false);}});
 return {prepare,stop,render,receive,spin,paint};
})();
