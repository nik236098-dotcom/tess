'use strict';
// Network actions use confirmed revisions; their independent flights overlap on screen.
const DartsGame=(()=>{
 let queue=[],inflight=null,flights=[],history=[],visible=null,raf=null,serial=0,batch=false,generation=0;
 let totals={bet:0,payout:0,count:0};
 const active=()=>flights.filter(f=>!f.done).length;
 const waiting=()=>queue.length+(inflight?1:0);
 function stop(){generation++;cancelAnimationFrame(raf);raf=null;queue=[];inflight=null;flights=[];DartsAudio.stop();if(state.ag.game==='darts')state.ag.animating=false;}
 function reset(){stop();history=[];visible=null;batch=false;totals={bet:0,payout:0,count:0};}
 function enqueue(){
  const a=state.ag,info=a.info;
  if(a.game!=='darts'||!state.connected||!info||a.pending?.action==='open'||(info.phase==='done'&&!info.settled))return true;
  if(active()+waiting()>=16){toast('Дождись попадания одного из дротиков');return true;}
  const amount=toCents($('ag-amount').value);
  if(!Number.isSafeInteger(amount)||amount<info.config.minBet||amount>info.config.maxBet){toast(`Ставка от ${money(info.config.minBet)} до ${money(info.config.maxBet)}`);return true;}
  const reserved=queue.reduce((sum,q)=>sum+q.amount,0)+(inflight?.amount||0);
  if(amount>state.balance-reserved){toast('Недостаточно средств на ещё один дротик');return true;}
  if(!active()&&!waiting()){flights=[];batch=true;visible=null;totals={bet:0,payout:0,count:0};}
  DartsAudio.unlock();$('ag-overlay').classList.add('hidden');
  queue.push({id:`dart-${Date.now()}-${++serial}`,amount});pump();renderArcade();return true;
 }
 function pump(){
  const a=state.ag;if(a.game!=='darts'||!state.connected||inflight||a.pending||!queue.length)return;
  if(a.info.phase==='done'&&!a.info.settled){queue=[];return;}
  const next=queue.shift();
  if(next.amount>state.balance){queue=[];toast('Оставшиеся броски отменены: недостаточно средств');return;}
  inflight={...next,revision:a.info.revision};a.pending={id:next.id,action:'start'};
  send({type:'ag_start',game:'darts',revision:a.info.revision,requestId:next.id,amount:next.amount,options:{}});haptic('light');
 }
 function receive(message){
  const a=state.ag;if(a.game!=='darts')return false;
  if(a.info&&message.revision<a.info.revision)return true;
  const isReply=inflight&&inflight.id===message.requestId,isOpen=a.pending?.action==='open'&&a.pending.id===message.requestId;
  a.info=message;
  if(isReply){
   const sent=inflight;inflight=null;a.pending=null;
   if(message.accepted===true&&message.phase==='done'&&message.revision>sent.revision){
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    flights.push({id:++serial,info:message,started:performance.now(),duration:reduced?0:CasinoMotion.duration('darts',message),t:0,done:false,revealed:false,sound:DartsAudio.channel(reduced)});
   }else queue=[]; // Never reinterpret a rejected action's current state as a new throw.
   if(!message.settled)queue=[];
  }else if(isOpen||!inflight&&!batch){
   if(isOpen)a.pending=null;
   history=[...(message.history||[])];visible=message.phase==='done'?message:null;
  }
  a.animating=Boolean(active());renderArcade();pump();controls();schedule();return true;
 }
 function schedule(){if(raf===null&&active()){const token=generation;raf=requestAnimationFrame(now=>{if(token===generation)tick(now);});state.ag.raf=raf;}}
 function tick(now){
  raf=null;const a=state.ag;if(a.game!=='darts')return;
  for(const flight of flights){
   if(flight.done)continue;
   flight.t=flight.duration?Math.min(1,Math.max(0,(now-flight.started)/flight.duration)):1;
   flight.sound.frame(flight.t);
   if(!flight.revealed&&flight.t>=CasinoMotion.dartsTiming.impact){
    flight.revealed=true;visible=flight.info;
    history=[{multiplier:visible.multiplier,payout:visible.payout,result:visible.result},...history].slice(0,15);
    totals.bet+=visible.bet;totals.payout+=visible.payout;totals.count++;
   }
   flight.done=flight.t===1;
  }
  const keep=flights.filter(f=>f.done).slice(-4);flights=flights.filter(f=>!f.done||keep.includes(f));
  a.animating=Boolean(active());paint();controls();
  if(active())schedule();else renderArcade();
 }
 function board(){
  const info={history,phase:visible?'done':'bet',multiplier:visible?.multiplier};
  const poses=flights.length?flights.map(f=>DartsScene.flightMarkup(f.id)).join(''):visible?.detail?.rules===DartsRules.version?DartsScene.flightMarkup('saved'):'';
  return DartsScene.board(info,DartsAudio.isEnabled()).replace(DartsScene.flightMarkup(),poses);
 }
 function paint(){
  const stage=$('ag-stage');
  for(const flight of flights){const layer=stage.querySelector(`[data-dt-flight="${flight.id}"]`);if(layer)DartsScene.paint(layer,CasinoMotion.frame('darts',flight.info,null,flight.t),flight.info);}
  if(!flights.length&&visible?.detail?.rules===DartsRules.version){const layer=stage.querySelector('[data-dt-flight="saved"]');if(layer)DartsScene.paint(layer,CasinoMotion.frame('darts',visible,null,1),visible);}
  const panel=stage.querySelector('.dt-panel'),key=String(visible?.revision||0);
  if(panel&&panel.dataset.paintKey!==key){
   const h=stage.querySelector('[data-dt-history]'),l=stage.querySelector('[data-dt-legends]');
   if(h)h.innerHTML=DartsScene.history({history});if(l)l.innerHTML=DartsScene.legends(visible?.multiplier);
   panel.dataset.paintKey=key;
  }
 }
 function controls(){
  const a=state.ag;if(a.game!=='darts')return;
  const pending=a.info?.phase==='done'&&!a.info.settled,open=a.pending?.action==='open',busy=Boolean(active()||waiting());
  const main=$('ag-main');main.disabled=!state.connected||!a.info||open||(pending?Boolean(a.pending)||a.animating:active()+waiting()>=16);
  main.textContent=pending?'Получить сохранённую выплату':'Бросить дротик';
  $('ag-amount').disabled=!state.connected||!a.info||open||busy||pending;
  for(const el of document.querySelectorAll('[data-ag-amount]'))el.disabled=$('ag-amount').disabled;
  $('ag-status').textContent=!state.connected?'Восстанавливаем связь…':open?'Загрузка…':busy?`В полёте: ${active()} · Ожидают: ${waiting()}`:batch?`Бросков: ${totals.count}`:'Готов к броску';
  $('ag-multiplier').textContent=agNumber(batch?(totals.bet?totals.payout/totals.bet:0):visible?.multiplier)+'×';
  $('ag-payout').textContent=money(batch?totals.payout:visible?.payout||0);
  if(!pending)$('ag-note').textContent='Каждое нажатие — отдельная ставка.';
  if(!busy){
   const result=batch&&totals.count?{...totals,settled:a.info?.settled,description:totals.count>1?`Завершено бросков: ${totals.count}`:''}:visible;
   GameResult.show($('ag-overlay'),result,'darts:'+generation+':'+serial+':'+(visible?.revision||0));
  }
 }
 return {reset,stop,enqueue,receive,board,paint,controls};
})();
