'use strict';
const AG_NAMES = { plinko: 'Plinko', tower: 'Башня', keno: 'Кено', dragon: 'Дракон и Тигр' };
const AG_SUBTITLES = { plinko: 'Пусть шарик найдёт свой путь', tower: 'Выбирай безопасные плитки и поднимайся выше', keno: 'Выбери числа — проверь совпадения', dragon: 'На чьей стороне старшая карта?' };
const AG_RULES = {
  plinko: 'Шарик проходит 10 рядов: на каждом шанс поворота влево или вправо равен 50%. Выплата — ставка × коэффициент ячейки. Уровень риска меняет таблицу выплат. Один запуск — один шарик. Результат определяет сервер, анимация показывает его путь.',
  tower: 'В Башне 9 этажей. Лёгкий: 3 безопасные плитки из 4; средний: 2 из 3; сложный: 1 из 2; эксперт: 1 из 3; мастер: 1 из 4. Выбирай плитку подсвеченного этажа. После первого успеха можно забрать выплату. Ловушка обнуляет ставку; на последнем этаже выплата автоматическая. Выход из приложения сохраняет текущую Башню.',
  keno: 'Режим Classic. Выбери от 1 до 10 разных чисел из 40. Сервер случайно вытянет 10 разных чисел. Выплата зависит от количества совпадений и выбранных чисел. Таблица показана до ставки; коэффициент включает возврат ставки.',
  dragon: 'Из восьми колод (416 карт), перемешанных перед раундом, открывается по одной карте Дракону и Тигру. Старшая побеждает: A — младшая, K — старшая; масть не влияет. Победа стороны: 2×. Ничья: 12× при ставке на ничью. Если поставил на сторону, а вышла ничья — возвращается половина ставки. Выплата включает ставку.',
};
function agNumber(n) { return Number(n || 0).toFixed(2).replace(/\.00$/, ''); }
function agLocked() { const a=state.ag; return !state.connected || !a.info || Boolean(a.pending) || a.animating; }
function stopArcade() {
  const a=state.ag; a.token++; cancelAnimationFrame(a.raf); a.animating=false; a.game=null; a.info=null; a.pending=null;
  $('screen-ag').classList.add('hidden');
}
function openArcade(game) {
  if(!Object.hasOwn(AG_NAMES,game)) return;
  showLobby(); const a=state.ag; a.game=game;
  $('screen-lobby').classList.add('hidden'); $('screen-ag').classList.remove('hidden'); $('screen-ag').scrollTop=0;
  stopRoomsPolling(); tg?.BackButton?.show();
  $('ag-title').textContent=AG_NAMES[game]; $('ag-subtitle').textContent=AG_SUBTITLES[game]; $('ag-rules-text').textContent=AG_RULES[game];
  $('ag-title').classList.toggle('ag-long-title',game==='dragon');
  $('ag-stage').className='ag-stage ag-'+game;
  $('ag-stage').innerHTML=''; $('ag-settings').innerHTML=''; $('ag-paytable').innerHTML='';
  $('ag-overlay').classList.add('hidden'); delete $('ag-overlay').dataset.revision;
  agOpenRequest(); renderArcade();
}
function closeArcade() { showLobby(); }
function agOpenRequest() {
  const a=state.ag; if(!a.game) return;
  a.pending={id:String(Date.now())+'-'+Math.random().toString(36).slice(2),action:'open'};
  send({type:'ag_open',game:a.game,requestId:a.pending.id});
}
function agRequest(action, extra={}) {
  const a=state.ag; if(agLocked()) return;
  const info=a.info, message={type:'ag_'+action,game:a.game,revision:info.revision,...extra};
  if(action==='start') {
    const amount=toCents($('ag-amount').value);
    if(!Number.isSafeInteger(amount)||amount<info.config.minBet||amount>info.config.maxBet) {toast(`Ставка от ${money(info.config.minBet)} до ${money(info.config.maxBet)}`);return;}
    if(amount>state.balance) {toast('Недостаточно средств');return;}
    if(a.game==='keno'&&!a.options.keno.picks.length) {toast('Выбери хотя бы одно число');return;}
    message.amount=amount; message.options=structuredClone(a.options[a.game]);
    $('ag-overlay').classList.add('hidden');
  }
  a.pending={id:String(Date.now())+'-'+Math.random().toString(36).slice(2),action}; message.requestId=a.pending.id;
  renderArcade(false); send(message); haptic('light');
}
function onArcadeState(message) {
  const a=state.ag; state.balance=message.balance;
  if(a.game!==message.game) return;
  if(a.info && message.revision<a.info.revision) return;
  const previous=a.info;
  const action=a.pending && a.pending.id===message.requestId?a.pending.action:null;
  if(action) a.pending=null;
  a.info=message;
  if(action==='open'&&message.options) a.options[a.game]=structuredClone(message.options);
  const changed=!previous||previous.revision!==message.revision;
  if(action==='start'&&message.phase==='done'&&changed) {
    a.animating=true; renderArcade(); agAnimateResult(message); return;
  }
  renderArcade();
  if(message.phase==='done'&&changed) agResult();
  if(a.game==='tower'&&message.phase==='play'&&(changed||action==='open')) agScrollTower();
}
function agSettings() {
  const a=state.ag, info=a.info, disabled=agLocked()||info?.phase==='play';
  const attr=disabled?'disabled':'';
  const button=(label,value,selected)=>`<button type="button" class="ag-choice ${selected?'is-selected':''}" data-ag-option="${value}" ${attr} aria-pressed="${Boolean(selected)}">${label}</button>`;
  if(a.game==='plinko') return `<label class="mn-label">Риск</label><div class="ag-choices">${[['Низкий','low'],['Средний','medium'],['Высокий','high']].map(([n,v])=>button(n,v,a.options.plinko.risk===v)).join('')}</div>`;
  if(a.game==='tower') return `<label class="mn-label" for="ag-difficulty">Сложность</label><select id="ag-difficulty" class="ag-select" ${attr}>${[['Лёгкая · 3 из 4','easy'],['Средняя · 2 из 3','medium'],['Сложная · 1 из 2','hard'],['Эксперт · 1 из 3','expert'],['Мастер · 1 из 4','master']].map(([n,v])=>`<option value="${v}" ${a.options.tower.level===v?'selected':''}>${n}</option>`).join('')}</select>`;
  if(a.game==='keno') return `<div class="ag-keno-tools"><span>Выбрано: <b>${a.options.keno.picks.length}/10</b></span><button type="button" data-ag-quick ${attr}>Случайные 5</button><button type="button" data-ag-clear ${attr}>Сбросить</button></div>`;
  return `<div class="ag-choices ag-sides">${[['Дракон','dragon',2],['Ничья','tie',12],['Тигр','tiger',2]].map(([n,v,m])=>button(`${n}<small>${m}×</small>`,v,a.options.dragon.side===v)).join('')}</div>`;
}
function agPayoutTable() {
  const a=state.ag, cfg=a.info?.config; if(!cfg) return '';
  let values=[];
  if(a.game==='plinko') values=cfg.tables[a.options.plinko.risk].map((n,i)=>[String(i+1),n]);
  else if(a.game==='tower') values=cfg.tables[a.options.tower.level].map((n,i)=>[`${i+1} этаж`,n]);
  else if(a.game==='keno') values=(cfg.tables[a.options.keno.picks.length]||[]).map((n,i)=>[`${i} совп.`,n]);
  else return '<span class="ag-table-note">A &lt; 2 &lt; … &lt; Q &lt; K · при ничьей возврат стороне ½ ставки</span>';
  if(!values.length) return '<span class="ag-table-note">Выбери числа — здесь появятся коэффициенты</span>';
  return values.map(([name,n])=>`<span class="ag-pay ${n>=1?'is-positive':''}"><small>${name}</small><b>${agNumber(n)}×</b></span>`).join('');
}
function renderArcade(board=true) {
  const a=state.ag;if(!a.game)return;
  const info=a.info, locked=agLocked(), live=info?.phase==='play', pending=info?.phase==='done'&&!info.settled;
  $('ag-balance').textContent=money(state.balance);
  $('ag-status').textContent=!state.connected?'Восстанавливаем связь…':a.pending?'Подождите…':a.animating?'Раунд идёт…':pending?'Выплата сохранена':live?`Этаж ${Math.min(9,(info.floor||0)+1)} из 9`:info?.phase==='done'?(info.result==='win'?'Выигрыш':info.result==='push'?'Ставка возвращена':info.payout?'Частичный возврат':'Без выигрыша'):'Готов к игре';
  $('ag-multiplier').textContent=agNumber(a.animating?0:info?.multiplier)+'×';
  $('ag-payout').textContent=money(a.animating?0:live?info.available:info?.payout||0);
  const main=$('ag-main');
  main.disabled=locked||Boolean(live&&!info.floor)||Boolean(a.game==='keno'&&!live&&!a.options.keno.picks.length);
  main.classList.toggle('is-cash',Boolean(live&&info.floor));
  main.textContent=pending?'Получить сохранённую выплату':a.animating?'Раунд идёт…':live?(info.floor?'Забрать '+money(info.available):'Выбери плитку первого этажа'):a.game==='plinko'?'Запустить шарик':a.game==='tower'?'Начать подъём':'Сделать ставку';
  $('ag-amount').disabled=Boolean(locked||live||pending);
  for(const el of document.querySelectorAll('[data-ag-amount]')) el.disabled=Boolean(locked||live||pending);
  $('ag-limit').textContent=info?`Ставка ${money(info.config.minBet)}–${money(info.config.maxBet)}`:'';
  $('ag-note').textContent=pending?'Выплата ждёт свободного места на балансе. Освободи место и нажми кнопку получения.':live?'Можно выйти: текущий этаж и ставка сохранятся.':'Коэффициенты включают ставку. Выплата округляется вниз до цента.';
  $('ag-settings').innerHTML=agSettings();
  $('ag-paytable').innerHTML=agPayoutTable();
  if(board) agBoard();
  else for(const el of $('ag-stage').querySelectorAll('button')) el.disabled=locked||el.dataset.locked==='true';
}
function agBoard() {
  const a=state.ag, info=a.info, stage=$('ag-stage');
  if(a.game==='plinko') {
    const risk=a.options.plinko.risk, table=info?.config.tables[risk]||Array(11).fill(0);
    let pins='';for(let r=0;r<10;r++)for(let j=0;j<=r;j++)pins+=`<circle cx="${180+(j-r/2)*28}" cy="${40+r*23}" r="3" class="ag-pin"/>`;
    const slot=!a.animating&&info?.phase==='done'?info.slot:-1;
    stage.innerHTML=`<svg viewBox="0 0 360 316" class="ag-plinko-svg" role="img" aria-label="Поле Plinko, 10 рядов"><defs><radialGradient id="ag-ball-glow"><stop stop-color="#fff"/><stop offset=".4" stop-color="#e8d1ff"/><stop offset="1" stop-color="#a477ff"/></radialGradient></defs>${pins}${table.map((n,i)=>`<g class="ag-slot ${i===slot?'is-landed':''}"><rect x="${26+i*28}" y="282" width="26" height="24" rx="5"/><text x="${39+i*28}" y="298" text-anchor="middle">${agNumber(n)}×</text></g>`).join('')}<circle id="ag-ball" cx="${slot>=0?180+(slot-5)*28:180}" cy="${slot>=0?273:18}" r="7" fill="url(#ag-ball-glow)"/></svg>`;
  } else if(a.game==='tower') {
    const old=stage.querySelector('.ag-tower-scroll')?.scrollTop;
    const table=info?.config.tables[a.options.tower.level]||Array(9).fill(0), columns=info?.config.levels[a.options.tower.level].columns||4, floor=info?.floor||0;
    stage.innerHTML=`<div class="ag-tower-scroll"><div class="ag-tower-rows">${Array.from({length:9},(_,i)=>8-i).map(row=>{
      const step=info?.steps?.[row], current=info?.phase==='play'&&row===floor;
      return `<div class="ag-floor ${current?'is-current':''}" data-floor="${row}" style="--ag-columns:${columns}"><span class="ag-floor-label">${row===8?'♛':row+1}</span>${Array.from({length:columns},(_,i)=>i).map(col=>{
        const trap=info?.revealed?.[row]?.includes(col), picked=step?.index===col, disabled=agLocked()||!current;
        return `<button type="button" data-ag-tile="${col}" data-locked="${!current}" ${disabled?'disabled':''} class="ag-tile ${step?(trap?'is-trap':'is-safe'):''} ${picked?'is-picked':''}" aria-label="Этаж ${row+1}, плитка ${col+1}">${step?(trap?'×':'✦'):'◇'}</button>`;
      }).join('')}<b class="ag-floor-pay">${agNumber(table[row])}×</b></div>`;
    }).join('')}</div></div>`;
    stage.querySelector('.ag-tower-scroll').scrollTop=old??10000;
  } else if(a.game==='keno') {
    const picks=a.options.keno.picks, drawn=a.animating?[]:info?.drawn||[];
    stage.innerHTML=`<div class="ag-keno-grid">${Array.from({length:40},(_,i)=>i+1).map(n=>`<button type="button" data-ag-number="${n}" aria-pressed="${picks.includes(n)}" ${agLocked()?'disabled':''} class="ag-keno-number ${picks.includes(n)?'is-selected':''} ${drawn.includes(n)?'is-drawn':''} ${drawn.includes(n)&&info.options?.picks.includes(n)?'is-hit':''}">${n}</button>`).join('')}</div><div class="ag-drawn-balls" aria-label="Выпавшие числа">${Array.from({length:10},(_,i)=>`<span class="ag-drawn-ball ${drawn[i]&&info.hits.includes(drawn[i])?'is-hit':''}" data-ag-ball="${i}">${drawn[i]||'·'}</span>`).join('')}</div>`;
  } else {
    stage.innerHTML=`<div class="ag-duel"><div class="ag-duelist">${agDuelCard('dragon',0)}<b>Дракон</b><small>Сила и выдержка</small></div><span class="ag-versus">VS</span><div class="ag-duelist">${agDuelCard('tiger',1)}<b>Тигр</b><small>Скорость и характер</small></div></div><div class="ag-duel-result">${!a.animating&&info?.winner?(info.winner==='tie'?'Ничья':info.winner==='dragon'?'Победил Дракон':'Победил Тигр'):'Какая карта окажется старше?'}</div>`;
  }
}
function agDuelCard(side,index) {
  const a=state.ag, info=a.info, card=info?.cards?.[index];
  return `<div class="ag-duel-card ${!a.animating&&card?'is-revealed':''} ${!a.animating&&info?.winner===side?'is-winner':''}" data-ag-card="${index}"><div class="ag-card-turn"><div class="ag-card-back"><svg class="icon"><use href="#i-${side==='dragon'?'spade':'club'}"/></svg></div><div class="ag-card-front">${card?hlCard(card):''}</div></div></div>`;
}
function agScrollTower() {
  const box=$('ag-stage').querySelector('.ag-tower-scroll'), row=$('ag-stage').querySelector('.is-current');
  if(box&&row)box.scrollTo({top:Math.max(0,row.offsetTop-box.offsetTop-box.clientHeight*.58),behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
}
function agAnimateResult(info) {
  const a=state.ag, token=++a.token, game=a.game, reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const duration=reduced?0:game==='plinko'?2100:game==='keno'?2400:1400;
  const started=performance.now(); let last=-1;
  const tick=now=>{
    if(token!==a.token||game!==a.game)return;
    const progress=duration?Math.min(1,(now-started)/duration):1;
    if(game==='plinko') {
      const points=[{x:180,y:18},{x:180,y:40}];let x=180;
      for(let i=0;i<info.path.length;i++){x+=(info.path[i]?14:-14);points.push({x,y:40+(i+1)*23});}
      const position=progress*(points.length-1), i=Math.min(points.length-2,Math.floor(position)), f=position-i;
      const ball=$('ag-ball');if(ball){ball.setAttribute('cx',points[i].x+(points[i+1].x-points[i].x)*f);ball.setAttribute('cy',points[i].y+(points[i+1].y-points[i].y)*f-5*Math.sin(f*Math.PI));}
    } else if(game==='keno') {
      const count=Math.min(10,Math.floor(progress*11));
      if(count!==last){for(let i=last<0?0:last;i<count;i++){
        const n=info.drawn[i], cell=$('ag-stage').querySelector(`[data-ag-number="${n}"]`), ball=$('ag-stage').querySelector(`[data-ag-ball="${i}"]`);
        cell?.classList.add('is-drawn'); if(info.hits.includes(n))cell?.classList.add('is-hit');
        if(ball){ball.textContent=n;ball.classList.toggle('is-hit',info.hits.includes(n));}
      }last=count;}
    } else {
      for(let i=0;i<2;i++)if(progress>(i? .52:.14))$('ag-stage').querySelector(`[data-ag-card="${i}"]`)?.classList.add('is-revealed');
    }
    if(progress<1)a.raf=requestAnimationFrame(tick);
    else {a.animating=false;renderArcade();agResult();}
  };
  a.raf=requestAnimationFrame(tick);
}
function agResult() {
  const a=state.ag, info=a.info, overlay=$('ag-overlay');
  if(!info||info.phase!=='done')return;
  haptic(info.result==='win'?'success':info.result==='push'?'light':'error');
  if(info.result!=='win'||!info.settled)return;
  const key=a.game+':'+info.revision;if(overlay.dataset.revision===key)return;
  overlay.dataset.revision=key;overlay.className='mn-overlay is-win ag-overlay';
  overlay.innerHTML=`<svg class="icon mn-suit-l" aria-hidden="true"><use href="#i-spade"/></svg><svg class="icon mn-suit-r" aria-hidden="true"><use href="#i-club"/></svg><i class="mn-spark mn-spark-1">✦</i><i class="mn-spark mn-spark-2">✦</i><b>×${agNumber(info.multiplier)}</b><span><i class="mn-coin">$</i>${money(info.payout).slice(1)}</span><button type="button" data-ag-dismiss aria-label="Закрыть выигрыш">×</button>`;
}
function bindArcade() {
  for(const el of document.querySelectorAll('[data-arcade]'))el.addEventListener('click',()=>openArcade(el.dataset.arcade));
  $('ag-back').addEventListener('click',closeArcade);
  $('ag-main').addEventListener('click',()=>{
    const info=state.ag.info;if(!info)return;
    if(info.phase==='done'&&!info.settled){agOpenRequest();renderArcade(false);return;}
    agRequest(info.phase==='play'?'cashout':'start');
  });
  $('ag-overlay').addEventListener('click',()=>{$('ag-overlay').classList.add('hidden');});
  $('ag-settings').addEventListener('change',event=>{if(event.target.id==='ag-difficulty'&&!agLocked()&&state.ag.info?.phase!=='play'){state.ag.options.tower.level=event.target.value;renderArcade();}});
  $('ag-settings').addEventListener('click',event=>{
    if(agLocked()||state.ag.info?.phase==='play')return;
    const a=state.ag, option=event.target.closest('[data-ag-option]');
    if(option){a.options[a.game][a.game==='plinko'?'risk':a.game==='tower'?'level':'side']=option.dataset.agOption;}
    if(event.target.closest('[data-ag-clear]'))a.options.keno.picks=[];
    if(event.target.closest('[data-ag-quick]')){const pool=Array.from({length:40},(_,i)=>i+1);for(let i=0;i<5;i++){const j=i+Math.floor(Math.random()*(40-i));[pool[i],pool[j]]=[pool[j],pool[i]];}a.options.keno.picks=pool.slice(0,5);}
    renderArcade();
  });
  $('ag-stage').addEventListener('click',event=>{
    if(agLocked())return;
    const tile=event.target.closest('[data-ag-tile]'), cell=event.target.closest('[data-ag-number]');
    if(tile&&!tile.disabled)agRequest('pick',{index:Number(tile.dataset.agTile)});
    if(cell){const picks=state.ag.options.keno.picks, n=Number(cell.dataset.agNumber), i=picks.indexOf(n);if(i>=0)picks.splice(i,1);else if(picks.length<10)picks.push(n);else{toast('Можно выбрать до 10 чисел');return;}renderArcade();}
  });
  for(const el of document.querySelectorAll('[data-ag-amount]'))el.addEventListener('click',()=>{
    if(agLocked())return;
    const max=Math.min(state.balance,state.ag.info.config.maxBet), value=toCents($('ag-amount').value)??100;
    const amount=Math.max(10,Math.min(max,Math.floor(el.dataset.agAmount==='max'?max:value*Number(el.dataset.agAmount))));
    $('ag-amount').value=(amount/100).toFixed(2).replace('.',',');
  });
}
