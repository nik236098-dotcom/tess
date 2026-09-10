'use strict';
const FeatureSlotsUI=(()=>{
 let game="cryo",R=FeatureSlotRules.cryo;
 const active=()=>Object.hasOwn(FeatureSlotRules,state.ag.game);
 const sound=FeatureSlotAudio,fx=typeof AbyssFX==='undefined'?{clear(){},spinWin(){},feature(){},celebrate(){},finish(){}}:AbyssFX;
 const idle=[0,1,8,2,3,4,5,6,7,0,2,9,3,1,6];
 let bet=20,turbo=false,running=false,entering=false,celebrating=false,timer=0,ready=false,loading=false,failed=false,balance=0,returnFocus=null;
 const icon='<svg viewBox="0 0 64 64" aria-hidden="true"><path d="M49 23A20 20 0 1 0 51 39" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round"/><path d="m39 22 13 3-1-14" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
 const symbol=(n,win=false)=>`<div class="ax-cell${win?' is-win':''}${n===9?' is-scatter':''}"><img src="/img/feature-slots/${game}/${R.symbols[n].id}.svg" alt="${R.symbols[n].name}" draggable="false">${n===8||n===9?`<b class="ax-symbol-tag${n===9?' is-scatter':''}">${n===8?'WILD':'SCATTER'}</b>`:''}</div>`;
 function prefs(){try{localStorage.setItem(game+'-prefs',JSON.stringify({bet,turbo}));}catch{}}
 function assets(){
  if(loading||ready)return;loading=true;failed=false;
  const assetGame=game;Promise.all([...R.symbols.map(s=>s.id),'station'].map(name=>new Promise(resolve=>{const image=new Image();image.onload=()=>resolve(true);image.onerror=()=>resolve(false);image.src='/img/feature-slots/'+game+'/'+name+'.svg';}))).then(result=>{if(assetGame!==game)return;loading=false;ready=result.every(Boolean);failed=!ready;if(active())render(false);});
 }
 function prepare(id){
  stop();game=id;R=FeatureSlotRules[id];ready=false;loading=false;bet=20;turbo=false;sound.theme(id);try{const p=JSON.parse(localStorage.getItem(game+'-prefs')||'{}');if(R.stakes.includes(p.bet))bet=p.bet;turbo=p.turbo===true;}catch{}
  sound.setMode?.(false);state.ag.options[game]={buyBonus:false};balance=state.balance;$('ag-amount').value=(bet/100).toFixed(2);assets();
 }
 function stop(){running=false;entering=false;celebrating=false;sound.stop();fx.clear();clearTimeout(timer);timer=0;close(false);}
 function controls(){
  const a=state.ag,info=a.info,bonus=info?.phase==='play',pending=info?.phase==='done'&&!info.settled,locked=agLocked()||entering||celebrating;
  const visual=a.animating?a.cgPrevious:info,price=bet*R.buyCost;
  const status=!state.connected?'Восстанавливаем связь…':loading?'Загружаем символы…':failed?'Нажмите вращение для повторной загрузки':pending?'Выплата сохранена':a.pending?'Сохраняем вращение…':a.animating?'Барабаны вращаются':bonus?entering?'Бонус открыт':running?'Бесплатные вращения':'Бонус на паузе':'';
  return `<div class="ax-controls ax-console${bonus?' is-feature':''}"><div class="ax-console-readout"><span>${bonus?'Общий выигрыш бонуса':'Выигрыш'}<b>${money(visual?.payout||0)}</b></span></div><div class="ax-console-actions">${bonus?`<div class="ax-console-tile ax-remaining"><small>Осталось</small><strong>${visual?.bonus?.remaining??info.bonus.remaining}</strong><span>вращений</span></div>`:`<button type="button" data-ax="stake" class="ax-console-tile" ${locked||pending?'disabled':''}><small>Ставка</small><strong>${money(bet)}</strong><span>⌄</span></button>`}<button type="button" class="ax-spin${a.animating?' is-spinning':''}" data-ax="spin" aria-label="${pending?'Получить сохранённую выплату':bonus?'Продолжить бесплатные вращения':'Вращать за '+money(bet)}" ${locked||loading?'disabled':''}>${icon}</button>${bonus?`<button type="button" data-ax="pause" class="ax-console-tile ax-feature-control" ${celebrating||entering?'disabled':''}><small>Бонус</small><strong>${running?'Ⅱ':'▷'}</strong><span>${running?'Пауза':'Продолжить'}</span></button>`:`<button type="button" data-ax="buy" class="ax-console-tile ax-feature-control" ${locked||pending||!ready?'disabled':''}><small>Bonus Buy</small><strong>${money(price)}</strong><span>8 вращений</span></button>`}</div><div class="ax-console-status" role="status">${status}</div><div class="ax-utilities"><button type="button" data-ax="menu" aria-label="Настройки слота"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 3 1-1h4l1 3 3 1 3 3-1 3 1 3-3 3-3 1-1 3h-4l-1-3-3-1-3-3 1-3-1-3 3-3 3-1Z"/><circle cx="12" cy="12" r="3.5"/></svg>Настройки</button><button type="button" data-ax="turbo" aria-pressed="${turbo}" ${locked?'disabled':''}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 2-10 12h7l-1 8 10-13h-7Z"/></svg>Турбо<i></i></button></div></div>`;
 }
 function render(board=true){
  const a=state.ag,info=a.info;if(a.game!==game)return;
  if(!a.animating)balance=state.balance;$('ag-balance').textContent=money(balance);
  $('ag-amount').value=(bet/100).toFixed(2);$('ag-paytable').innerHTML='';$('ag-settings').innerHTML=controls();
  $('ag-main').disabled=agLocked();$('ag-rules-text').textContent=R.description;
  GameResult.hide($('ag-overlay'));$('screen-ag').classList?.toggle?.('ax-feature-mode',(a.animating?a.cgPrevious:info)?.phase==='play'||celebrating&&info?.bonus?.played>0);
  if(!board)return;
  const visual=a.animating?a.cgPrevious:info,grid=info?.detail?.grid||idle,old=visual?.detail?.grid||idle;
  const wins=new Set(!a.animating?info?.detail?.lines?.flatMap(l=>l.cells)||[]:[]),bonus=visual?.bonus;
  if(!a.animating&&info?.detail?.triggered)grid.forEach((n,i)=>{if(n===R.scatter)wins.add(i);});
  const inBonus=visual?.phase==='play',finishedBonus=visual?.phase==='done'&&visual?.bonus?.played>0;
  const shownMultiplier=(finishedBonus?visual.detail?.usedMultiplier:bonus?.multiplier)||1;
  const signalLabel=inBonus?R.feature:finishedBonus?'БОНУС ЗАВЕРШЁН':R.feature;
  const signalText=inBonus?(game==='cryo'?'Wild сохраняются · повторный Wild усиливает':'Ключи '+(bonus?.keys||0)+'/9 · открой следующий вагон'):'3 SCATTER открывают бонус';
  const detail=info?.detail;
  const note=a.animating?'':detail?.capped?'Достигнут максимум 2500×':detail?.win&&detail.bonusSpin&&game!=='cryo'?money(detail.rawWin/detail.usedMultiplier)+' × '+detail.usedMultiplier+' = '+money(detail.win):detail?.triggered&&detail.bonusSpin?'+'+detail.triggered+' бесплатных вращения':detail?.win?'За вращение '+money(detail.win):(game==='cryo'?'FROZEN WILDS · 1× → 2× → 3× → 5×':'CONDUCTOR WILDS · COLLECT VAULT KEYS');

  const reels=[0,1,2,3,4].map(col=>{
   const result=[grid[col],grid[col+5],grid[col+10]],fill=18+col*3;
   const strip=a.animating?[...result,...Array.from({length:fill},(_,i)=>(i*7+col+Number(info.revision))%10),old[col],old[col+5],old[col+10]]:result;
   const locks=(a.animating?(info?.detail?.bonusSpin?a.cgPrevious:null):info)?.bonus?.locked||{};
   const frozen=game==='cryo'?[0,1,2].filter(row=>locks[row*5+col]).map(row=>`<div class="fs-frozen${!a.animating&&info?.detail?.upgraded?.includes(row*5+col)?' is-upgraded':''}" style="top:${row*100/3}%">${symbol(8,wins.has(row*5+col))}<strong>×${locks[row*5+col]}</strong><i></i></div>`).join(''):'';
   return `<div class="ax-reel">${frozen}<div class="ax-strip" data-ax-reel="${col}" data-length="${strip.length}" style="transform:translateY(${a.animating?-(strip.length-3)/strip.length*100:0}%)">${strip.map((n,i)=>symbol(n,wins.has(i*5+col))).join('')}</div></div>`;
  }).join('');
  $('ag-stage').innerHTML=`<div class="ax-scene"><div class="ax-hero"><div class="ax-brand">${R.title.split(' ')[0]}<span>${R.title.split(' ').slice(1).join(' ')}</span></div><div class="ax-water-light"></div></div><div class="ax-window"><div class="ax-grid" aria-label="Барабаны ${R.title}">${reels}</div></div><div class="ax-signal${visual?.phase==='play'?' is-active':''}"><div class="ax-sonar"><i></i></div><div><small>${signalLabel}</small><b>${signalText}</b><div class="ax-meter"><i style="width:${(game==='cryo'?Object.keys(bonus?.locked||{}).length/15:(bonus?.keys||0)/9)*100}%"></i></div></div><strong>${game==='cryo'?Object.keys(bonus?.locked||{}).length+'/15':shownMultiplier+'×'}</strong></div><p class="ax-scene-note">${note}</p></div>`;
  if(a.animating)paint(a.cgTime||0);
 }
 function reelTiming(){
  const grid=state.ag.info?.detail?.grid||idle,stops=[];
  let seen=0,offset=0;
  for(let col=0;col<5;col++){
   const base=.62+col*.095,anticipate=seen>=2&&seen<3&&col>0;
   const cue=anticipate?stops[col-1].end:0,end=anticipate?cue+.58:base+offset;
   stops.push({end,cue,anticipate});offset=end-base;
   seen+=[grid[col],grid[col+5],grid[col+10]].filter(n=>n===R.scatter).length;
  }
  return stops;
 }
 function paint(t){
  const timing=reelTiming();
  for(const el of $('ag-stage').querySelectorAll('[data-ax-reel]')){
   const col=Number(el.dataset.axReel),stop=timing[col],u=Math.min(1,t/stop.end),progress=u<.12?u*u/.12:.12+2*(u-.12)-(u-.12)*(u-.12)/.88;
   const length=Number(el.dataset.length);el.style.transform=`translateY(${-(length-3)/length*100*(1-progress)}%)`;
   el.parentElement.classList.toggle('is-settled',u===1);el.classList.toggle('is-blurred',u>.06&&u<.83);
   el.parentElement.classList.toggle('is-anticipating',stop.anticipate&&t>=stop.cue&&t<stop.end);
  }
 }
 function receive(message){
  const a=state.ag,previous=a.info,action=a.pending?.id===message.requestId?a.pending.action:null;
  if(action)a.pending=null;a.info=message;
  if(message.unitBet&&message.phase==='play')bet=message.unitBet;
  const changed=!previous||previous.revision!==message.revision;
  if(message.accepted===false){running=false;entering=false;sound.spinning(false);sound.anticipation(false);clearTimeout(timer);render();return;}
  if(changed&&(action==='start'||action==='pick')&&message.detail){a.cgPrevious=previous;a.animating=true;a.cgTime=0;fx.clear();sound.spinning(true);render();animate();return;}
  sound.setMode?.(message.phase==='play');render();
 }
 function animate(){
  const a=state.ag,token=++a.token,start=performance.now(),reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches,duration=reduced?0:turbo?1050:2900,total=reelTiming().at(-1).end;
  const sounded=new Set();let scatterSounds=0;
  const tick=now=>{if(token!==a.token||a.game!==game)return;const t=duration?Math.min(total,(now-start)/duration):total;a.cgTime=t;paint(t);const timing=reelTiming();
   sound.anticipation(timing.some(s=>s.anticipate&&t>=s.cue&&t<s.end));
   timing.forEach((s,col)=>{if(t>=s.end&&!sounded.has(col)){sounded.add(col);sound.play('stop');const symbols=[a.info.detail.grid[col],a.info.detail.grid[col+5],a.info.detail.grid[col+10]];if(symbols.includes(R.wild))sound.play('wild');for(const n of symbols)if(n===R.scatter)sound.play('scatter',++scatterSounds);}});
   if(t<total){a.raf=requestAnimationFrame(tick);return;}
   sound.spinning(false);sound.anticipation(false);a.animating=false;a.cgTime=0;entering=!!(a.info.detail.triggered&&!a.info.detail.bonusSpin&&a.info.phase==='play');render();
   const info=a.info;if(info.phase==='play')sound.setMode?.(true);
   if(info.detail.win){fx.spinWin(info);sound.play('match');if(info.detail.win/info.unitBet<50&&!(info.phase==='done'&&info.bonus?.played>0))sound.play('win',info.detail.win/info.unitBet);}
   if(info.detail.bonusSpin&&info.bonus.multiplier>(a.cgPrevious?.bonus?.multiplier||1)){if(!info.detail.triggered)fx.feature('Множитель '+info.bonus.multiplier+'×');sound.play('multiplier');}
   if(info.detail.upgraded?.length){fx.feature('FROZEN WILD · усиление');sound.play('multiplier');}
   if(info.detail.triggered&&info.detail.bonusSpin){fx.feature('+'+info.detail.triggered+' бесплатных вращения');sound.play('bonus');}
   if(info.phase==='done'&&info.bonus?.played>0){running=false;celebrate('summary');return;}
   if(entering){running=false;timer=setTimeout(()=>{timer=0;entering=false;if(token!==a.token||a.game!==game)return;render(false);sound.play('bonus');show('bonus');},1200);return;}
   if(info.detail.win/info.unitBet>=50){celebrate('big');return;}
   if(info.phase==='done'){running=false;return;}
   advanceBonus();
  };a.raf=requestAnimationFrame(tick);
 }
 function advanceBonus(){
  clearTimeout(timer);timer=0;
  if(running&&!document.hidden&&state.ag.info?.phase==='play')timer=setTimeout(()=>{timer=0;if(active()&&state.connected&&!agLocked()&&!celebrating)spin();},state.ag.info?.detail?.win?1400:turbo?250:750);
 }
 function celebrate(kind){
  celebrating=true;render(false);if(kind!=='summary'||state.ag.info.payout>0)sound.play(kind==='summary'?'summary':'bigwin',state.ag.info.detail.win/state.ag.info.unitBet);
  fx.celebrate(state.ag.info,kind,()=>{celebrating=false;if(kind==='summary')sound.setMode?.(false);render(false);advanceBonus();});
 }
 function spin(){
  if(!active()||agLocked()||entering||celebrating)return;
  if(!ready){assets();return;}
  const info=state.ag.info;sound.setMode?.(info.phase==='play');sound.unlock();fx.clear();close(false);
  if(info.phase==='done'&&!info.settled){agOpenRequest();render(false);return;}
  if(info.phase==='play'){running=true;agRequest('pick',{index:0});return;}
  running=false;state.ag.options[game]={buyBonus:false};agRequest('start');
 }
 function close(focus=true){const node=document.getElementById('ax-dialog');if(node)node.remove();if(focus)returnFocus?.focus();returnFocus=null;}
 function show(kind){
  const previousFocus=returnFocus||document.activeElement;close(false);returnFocus=previousFocus;
  const info=state.ag.info;if(!info)return;
  let body='';
  if(kind==='menu'){body=`<h2>Настройки слота</h2><div class="ax-menu-list"><button type="button" data-ax="sound"><span>Музыка и эффекты</span><b>${sound.settings().muted?'Выкл':'›'}</b></button><button type="button" data-ax="rules"><span>Правила и выплаты</span><b>›</b></button></div>`;}
  else if(kind==='sound'){const p=sound.settings();body=`<h2>Музыка и эффекты</h2><button type="button" data-ax="mute" class="ax-confirm">${p.muted?'Включить звук':'Выключить звук'}</button><label class="ax-volume">Музыка<input data-ax-volume="music" type="range" min="0" max="100" value="${Math.round(p.music*100)}"></label><label class="ax-volume">Эффекты<input data-ax-volume="effects" type="range" min="0" max="100" value="${Math.round(p.effects*100)}"></label>`;}
  else if(kind==='stake')body=`<h2>Ставка за вращение</h2><div class="ax-stake-summary"><small>Выбрано</small><strong>${money(bet)}</strong><span>Bonus Buy · ${money(bet*R.buyCost)}</span></div><p>Полная стоимость · все 20 линий</p><div class="ax-stakes">${R.stakes.map(n=>`<button type="button" data-ax-stake="${n}" aria-pressed="${n===bet}">${money(n)}</button>`).join('')}</div>`;
  else if(kind==='buy')body=`<img class="ax-dialog-art" src="/img/feature-slots/${game}/9.svg" alt=""><h2>${R.feature}</h2><p>8 бесплатных вращений<br>${game==='cryo'?'Сохраняющиеся Wild · усиление до 5×':'Собирай ключи · множитель до 5×'}</p><div class="ax-buy-stake"><label for="ax-buy-unit">Ставка за вращение</label><div><button type="button" data-ax="buy-minus" aria-label="Уменьшить ставку бонуса" ${bet===R.stakes[0]?'disabled':''}>−</button><select id="ax-buy-unit" aria-label="Ставка бонуса">${R.stakes.map(n=>`<option value="${n}" ${n===bet?'selected':''}>${money(n)}</option>`).join('')}</select><button type="button" data-ax="buy-plus" aria-label="Увеличить ставку бонуса" ${bet===R.stakes.at(-1)?'disabled':''}>+</button></div></div><div class="ax-price" aria-live="polite"><span>Стоимость бонуса · ${money(bet)} × ${R.buyCost}</span><strong>${money(bet*R.buyCost)}</strong></div><p>Эта сумма будет списана с баланса. Покупка не гарантирует выигрыш.</p><button type="button" data-ax="confirm-buy" class="ax-confirm" ${bet*R.buyCost>state.balance?'disabled':''}>${bet*R.buyCost>state.balance?'Недостаточно средств':'Купить за '+money(bet*R.buyCost)}</button>`;
  else if(kind==='bonus')body=`<div class="ax-bonus-rays" aria-hidden="true"></div><div class="ax-bonus-particles" aria-hidden="true">${Array.from({length:14},(_,i)=>`<i style="--i:${i}"></i>`).join('')}</div><h2>ВЫ ВЫИГРАЛИ</h2><div class="ax-bonus-count">${info.bonus.remaining}</div><p class="ax-bonus-label">бесплатных вращений</p><button type="button" data-ax="spin" class="ax-confirm">Нажмите, чтобы начать</button>`;
  else body=`<h2>Символы и выплаты</h2><p>За 3 / 4 / 5 подряд слева направо.<br>Множители ниже — от ставки одной линии.</p><div class="ax-payments">${R.symbols.slice(0,9).map(s=>`<div><img src="/img/feature-slots/${game}/${s.id}.svg" alt=""><span>${s.name}</span><b>${s.pay.join(' / ')}×</b></div>`).join('')}</div><h3>20 выигрышных линий</h3><div class="ax-payline-guide">${R.lines.map((line,i)=>`<div><small>${i+1}</small><svg viewBox="0 0 100 60" aria-label="Линия ${i+1}"><polyline points="${line.map((row,col)=>`${col*20+10},${row*20+10}`).join(' ')}"/></svg></div>`).join('')}</div><p>${$('ag-rules-text').textContent}</p>`;
  const overlay=document.createElement('div');overlay.id='ax-dialog';overlay.className='ax-dialog'+(kind==='bonus'?' ax-bonus-intro':'');if(kind==='bonus')overlay.dataset.ax='spin';overlay.innerHTML=`<section role="dialog" aria-modal="true" aria-label="${kind==='stake'?'Выбор ставки':kind==='buy'?'Покупка бонуса':R.title}">${kind==='bonus'?'':'<button type="button" class="ax-close" data-ax="close" aria-label="Закрыть">×</button>'}${body}</section>`;$('screen-ag').appendChild(overlay);overlay.querySelector('button:not(:disabled)')?.focus();
 }
 document.addEventListener('click',event=>{
  if(!active())return;const button=event.target.closest('[data-ax],[data-ax-stake]');if(!button||button.disabled)return;
  const action=button.dataset.ax;
  sound.unlock();
  if(action==='finish-win'){fx.finish();return;}
  if(celebrating)return;
  if(action==='mute'){sound.configure({muted:!sound.settings().muted});show('sound');render(false);return;}
  if(action==='pause'){if(running){running=false;clearTimeout(timer);timer=0;render(false);}else if(!agLocked()&&!entering)spin();return;}
  if(action==='close'){close();return;}if(action==='rules'||action==='sound'||action==='menu'){running=false;clearTimeout(timer);timer=0;show(action);render(false);return;}
  if(agLocked()||entering)return;
  if(action==='spin'){spin();return;}
  if(action==='turbo'){turbo=!turbo;prefs();render(false);return;}
  if(state.ag.info?.phase==='play'||state.ag.info?.settled===false)return;
  if(action==='test-bonus'||action==='confirm-test')return;
  if(action==='stake'||action==='buy'){show(action);return;}
  if(action==='buy-minus'||action==='buy-plus'){const index=R.stakes.indexOf(bet);changeBuyStake(R.stakes[index+(action==='buy-plus'?1:-1)],action);return;}
  if(action==='confirm-buy'){
   if(bet*R.buyCost>state.balance||!ready)return;
   close(false);fx.clear();running=false;state.ag.options[game]={buyBonus:true};agRequest('start');return;
  }
  const index=R.stakes.indexOf(bet),chosen=button.dataset.axStake?Number(button.dataset.axStake):R.stakes[Math.max(0,Math.min(R.stakes.length-1,index+(action==='plus'?1:-1)))];
  if(R.stakes.includes(chosen)){bet=chosen;prefs();close();render(false);}
 });
 function changeBuyStake(value,focusAction){
  if(!active()||agLocked()||entering||celebrating||state.ag.info?.phase==='play'||state.ag.info?.settled===false||!R.stakes.includes(value))return;
  bet=value;prefs();render(false);show('buy');
  const dialog=document.getElementById('ax-dialog');
  const target=focusAction?dialog?.querySelector(`[data-ax="${focusAction}"]:not(:disabled)`):null;
  (target||dialog?.querySelector('#ax-buy-unit'))?.focus();
 }
 document.addEventListener('change',event=>{if(active()&&event.target.id==='ax-buy-unit')changeBuyStake(Number(event.target.value));});
 document.addEventListener('input',event=>{const kind=event.target.dataset?.axVolume;if(active()&&['music','effects'].includes(kind))sound.configure({[kind]:Number(event.target.value)/100});});
 document.addEventListener('keydown',event=>{
  if(!active())return;
  if(celebrating&&event.key==='Tab'){event.preventDefault();document.querySelector('[data-ax=finish-win]')?.focus();return;}
  if(celebrating&&(event.key==='Escape'||event.key==='Enter'||event.key===' ')){event.preventDefault();fx.finish();return;}
  const dialog=document.getElementById('ax-dialog');if(!dialog)return;
  if(event.key==='Escape'){event.preventDefault();close();}
  if(event.key==='Tab'){const buttons=[...dialog.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled)')];if(event.shiftKey&&document.activeElement===buttons[0]){event.preventDefault();buttons.at(-1)?.focus();}else if(!event.shiftKey&&document.activeElement===buttons.at(-1)){event.preventDefault();buttons[0]?.focus();}}
 });
 document.addEventListener('visibilitychange',()=>{if(document.hidden){sound.stop();running=false;entering=false;clearTimeout(timer);timer=0;if(active())render(false);}});
 return {prepare,stop,render,receive,spin,paint,isGame:id=>Object.hasOwn(FeatureSlotRules,id)};
})();
