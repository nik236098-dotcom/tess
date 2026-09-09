'use strict';
function openCrash() {
  showLobby(); state.cr.open=true; state.cr.busy=true;
  $('screen-lobby').classList.add('hidden'); $('screen-cr').classList.remove('hidden'); $('screen-cr').scrollTop=0;
  stopRoomsPolling(); if(tg?.BackButton) tg.BackButton.show();
  renderCrash(); send({type:'cr_open'});
}
function closeCrash() { showLobby(); }
function crSend() {
  const cr=state.cr; if(cr.busy||!state.connected||!cr.info) return;
  const live=cr.info.phase==='play';
  const amount=toCents($('cr-amount').value);
  const autoStop=$('cr-auto').checked?Number($('cr-target').value.replace(',','.')):null;
  if(!live) {
    if(amount===null||amount<10||amount>10000000) { toast('Ставка от $0.10 до $100 000'); return; }
    if(amount>state.balance) { toast('Недостаточно средств'); return; }
    if(autoStop!==null&&(!Number.isFinite(autoStop)||autoStop<1.01||autoStop>1000000||Math.abs(autoStop*100-Math.round(autoStop*100))>1e-6)) {toast('Автостоп: от 1.01× до 1 000 000×, не более двух знаков');return;}
  }
  if(!live)GameResult.hide($('cr-overlay'));
  cr.busy=true; renderCrash(); haptic('light');
  send({type:live?'cr_cashout':'cr_start',revision:cr.info.revision,amount,autoStop});
}
function onCrashState(message) {
  const cr=state.cr; const previous=cr.info;
  cr.info=message; cr.receivedAt=performance.now(); cr.busy=false; state.balance=message.balance;
  if(previous?.phase==='play'&&message.phase==='done'&&cr.open) haptic(message.result==='win'?'success':'error');
  renderCrash();
}
function crDisplayed() {
  const cr=state.cr, info=cr.info;
  if(!info) return 1;
  if(info.phase!=='play') return info.multiplier;
  const extra=state.connected?Math.min(250,Math.max(0,performance.now()-cr.receivedAt)):0;
  const n=Math.min(1000000,Math.exp(info.rate*Math.max(0,info.serverNow-info.startedAt+extra)/1000));
  return info.autoStop===null?n:Math.min(n,info.autoStop);
}
function crDraw() {
  const cr=state.cr; if(!cr.open) return;
  const info=cr.info; const live=info?.phase==='play'; const n=crDisplayed();
  $('cr-number').textContent=n.toFixed(2)+'×';
  const x=22+Math.min(272,Math.log(Math.max(1,n))*130);
  const y=218-Math.min(165,Math.log(Math.max(1,n))*90);
  const curve=`M22 218 C ${22+(x-22)*.42} 218 ${22+(x-22)*.78} ${y+20} ${x} ${y}`;
  $('cr-curve').setAttribute('d',curve); $('cr-fill').setAttribute('d',curve+` L${x} 218 Z`);
  $('cr-dot').setAttribute('cx',x);$('cr-dot').setAttribute('cy',y);
  if(live) $('cr-main').textContent='Забрать '+money(Math.floor(info.bet*Math.floor(n*100)/100));
}
function renderCrash() {
  const cr=state.cr; if(!cr.open) return;
  const info=cr.info, live=info?.phase==='play', locked=cr.busy||!state.connected||!info;
  $('cr-balance').textContent=money(state.balance);
  const pending=info?.phase==='done'&&!info.settled;
  $('cr-main').disabled=locked||pending;
  $('cr-main').classList.toggle('is-cash',Boolean(live));
  $('cr-main').textContent=pending?'Выплата сохранена':live?'Забрать '+money(info.available):'Сделать ставку';
  $('cr-status').textContent=!state.connected?'Восстанавливаем связь…':live?'Раунд идёт':info?.result==='lose'?'Краш':info?.result==='win'?'Выигрыш получен':'Готов к запуску';
  $('cr-game').classList.toggle('is-crashed',info?.result==='lose');
  for(const el of document.querySelectorAll('#cr-panel input, #cr-panel .mn-mod, #cr-panel .cr-preset, #cr-panel .cr-step')) el.disabled=Boolean(locked||live);
  const auto=live?info.autoStop!==null:$('cr-auto').checked;
  if(live) { $('cr-auto').checked=auto; if(auto) $('cr-target').value=info.autoStop.toFixed(2); }
  for(const el of document.querySelectorAll('#cr-target, .cr-step, .cr-preset')) el.disabled=Boolean(locked||live||!auto);
  const target=live?info.autoStop:Number($('cr-target').value.replace(',','.'));
  $('cr-auto-caption').textContent=auto&&Number.isFinite(target)?`Автостоп на ${target.toFixed(2)}×`:'Автостоп выключен';
  for(const el of document.querySelectorAll('.cr-preset')) el.classList.toggle('is-selected',auto&&Number(el.dataset.crTarget)===target);
  const history=$('cr-history'); const historyKey=JSON.stringify(info?.history||[]);
  if(history.dataset.key!==historyKey) {
    history.dataset.key=historyKey;
    history.innerHTML=(info?.history||[]).map(item=>`<span class="cr-history-item ${item.result==='win'?'is-win':''}">${item.multiplier.toFixed(2)}×</span>`).join('')||'<span class="cr-history-empty">История раундов</span>';
  }
  GameResult.show($('cr-overlay'),info?.phase==='done'&&!cr.busy?info:null,info?.revision);
  $('cr-note').textContent=pending?'Выплата ожидает свободного места на балансе. Откройте игру повторно после уменьшения баланса.':live?'Ставка и автостоп зафиксированы до конца раунда.':'Раунд начнётся сразу после ставки.';
  $('cr-note').hidden=!pending;
  crDraw();
  cancelAnimationFrame(cr.raf);
  if(live) { const tick=()=>{if(!cr.open||cr.info?.phase!=='play')return;crDraw();cr.raf=requestAnimationFrame(tick);};cr.raf=requestAnimationFrame(tick); }
}
function bindCrash() {
  $('play-crash').addEventListener('click',openCrash);$('cr-back').addEventListener('click',closeCrash);$('cr-main').addEventListener('click',crSend);
  $('cr-auto').addEventListener('change',renderCrash);$('cr-target').addEventListener('input',renderCrash);
  for(const el of document.querySelectorAll('[data-cr-amount]')) el.addEventListener('click',()=>{
    const max=Math.min(state.balance,10000000), n=toCents($('cr-amount').value)??100;
    const amount=Math.max(10,Math.min(max,Math.round(el.dataset.crAmount==='max'?max:n*Number(el.dataset.crAmount))));
    $('cr-amount').value=(amount/100).toFixed(2).replace('.',',');
  });
  for(const el of document.querySelectorAll('[data-cr-target]')) el.addEventListener('click',()=>{$('cr-target').value=Number(el.dataset.crTarget).toFixed(2);renderCrash();});
  for(const el of document.querySelectorAll('[data-cr-step]')) el.addEventListener('click',()=>{
    const n=Number($('cr-target').value.replace(',','.'));$('cr-target').value=Math.max(1.01,Math.min(1000000,(Number.isFinite(n)?n:2)+Number(el.dataset.crStep))).toFixed(2);renderCrash();
  });
}
