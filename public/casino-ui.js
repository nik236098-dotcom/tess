'use strict';
const CasinoUI=(()=>{
const definitions=CasinoRules.games,colors=['#65d7a2','#b183ed','#f0cc69','#e47593','#72d7e5','#ec9eda','#81a2ef'];
const symbols=['♣','♦','♥','♠','✦','♛'];
const isGame=game=>Object.hasOwn(definitions,game);
const current=()=>definitions[state.ag.game];
const button=(label,index,disabled=false,cls='')=>`<button type="button" class="cg-action ${cls}" data-cg-pick="${index}" ${disabled?'disabled':''}>${label}</button>`;
function prepare(game){if(!isGame(game))return;state.ag.options[game]??=structuredClone(definitions[game].defaults);state.ag.held=[];state.ag.cgProgress=null;}
function setup(){
 const host=$('casino-catalog');if(!host)return;
 host.innerHTML=CasinoRules.ids.map(id=>{const g=definitions[id];return `<button type="button" data-arcade="${id}" class="cg-launch"><span class="cg-launch-art">${CasinoArt.svg(g.icon)}</span><span class="cg-launch-name">${g.name}</span><small>${g.tag}</small></button>`;}).join('');
}
function settings(){
 const a=state.ag,g=current(),options=a.options[a.game],disabled=agLocked()||a.info?.phase==='play',attr=disabled?'disabled':'';
 if(a.game==='limbo')return `<label class="mn-label" for="cg-target">Целевой коэффициент</label><input id="cg-target" class="ag-select" inputmode="decimal" value="${options.target}" ${attr} autocomplete="off"><p class="ag-note">Шанс: ${agNumber(99/options.target)}% · выплата при успехе ${agNumber(options.target)}×</p>`;
 if(g.choices){const key=a.game==='chicken'||a.game==='balloon'?'level':'side';return `<span class="mn-label">${key==='level'?'Сложность':'Выбор до ставки'}</span><div class="cg-choices">${g.choices.map(([name,value])=>`<button type="button" class="ag-choice ${options[key]===value?'is-selected':''}" data-cg-option="${value}" data-cg-key="${key}" ${attr} aria-pressed="${options[key]===value}">${name}</button>`).join('')}</div>`;}
 return `<p class="ag-note">${g.tag}</p>`;
}
function seriesTable(game,options){
 let size,bad,max,p=1;const level=options.level;
 if(game==='chicken'||game==='balloon'){size=game==='chicken'?21:25;bad={easy:1,medium:3,hard:5}[level];max=size-bad;}
 else if(game==='collection'){size=12;bad=3;max=9;}
 else max=game==='penalty'?5:game==='pinball'?10:20;
 return Array.from({length:max},(_,i)=>{p*=size?(size-bad-i)/(size-i):game==='coin'||game==='rps'?.5:.8;return Math.floor((.98/p+1e-10)*100)/100;});
}
function paytable(){const a=state.ag,g=current();const table=g.series?seriesTable(a.game,a.options[a.game]).map((n,i)=>[`${i+1} шаг`,n]):a.game==='limbo'?[['Цель',a.options.limbo.target]]:g.table;return (table||[]).map(([label,value])=>`<span class="ag-pay is-positive"><small>${label}</small><b>${agNumber(value)}×</b></span>`).join('');}
function afterRender(){
 const a=state.ag,g=current(),info=a.info,live=info?.phase==='play',pending=info?.phase==='done'&&!info.settled,main=$('ag-main');
 $('ag-title').classList.toggle('ag-long-title',g.name.length>15);
 if(!live)return;
 const locked=agLocked();
 main.disabled=locked;main.classList.toggle('is-cash',Boolean(g.series));
 if(g.series){main.textContent=info.step?'Забрать '+money(info.available):'Вернуть ставку';$('ag-status').textContent=locked?'Подождите…':info.last?.tie?'Ничья · серия сохранена':`Успешных ходов: ${info.step||0}`;}
 else if(a.game==='videopoker'){main.textContent=(state.ag.held||[]).length===5?'Оставить все карты':'Заменить неотмеченные';$('ag-status').textContent='Отметь карты, которые оставляешь';}
 else {main.textContent='Сотри ячейки билета';main.disabled=true;$('ag-status').textContent=`Открыто: ${info.revealed?.length||0} из 9`;}
 if(!pending)$('ag-note').textContent=g.series?'Раунд сохранён. Можно продолжить или забрать.':'Раунд сохранён: можно выйти и вернуться.';
}
function main(){
 const a=state.ag;if(!isGame(a.game))return false;
 if(a.info?.phase==='play'&&a.game==='videopoker'){agRequest('pick',{index:[...(a.held||[])]});return true;}
 return false;
}
function card(c){if(!c)return '<div class="cg-card-back">♠</div>';const rank=c.rank===14?'A':c.rank===13?'K':c.rank===12?'Q':c.rank===11?'J':c.rank,suit={s:'♠',c:'♣',h:'♥',d:'♦'}[c.suit];return `<div class="cg-card-face ${c.suit==='h'||c.suit==='d'?'is-red':''}"><b>${rank}<small>${suit}</small></b><span>${suit}</span></div>`;}
function gem(n,i=0){return `<span class="cg-gem" style="--gem:${colors[n%7]};--delay:${i*90}ms"><svg viewBox="0 0 80 90"><path d="M7 28L23 9H57L73 28 40 81Z"/><path d="M7 28H73M23 9L27 28 40 81 53 28 57 9M27 28H53" fill="none" stroke="#fff8" stroke-width="1.5"/></svg></span>`;}
function dice(n){const dots={1:[[50,50]],2:[[25,25],[75,75]],3:[[25,25],[50,50],[75,75]],4:[[25,25],[75,25],[25,75],[75,75]],5:[[25,25],[75,25],[50,50],[25,75],[75,75]],6:[[25,25],[75,25],[25,50],[75,50],[25,75],[75,75]]}[n];return `<svg viewBox="0 0 100 100" class="cg-die"><rect x="3" y="3" width="94" height="94" rx="19"/>${dots.map(([x,y])=>`<circle cx="${x}" cy="${y}" r="7"/>`).join('')}</svg>`;}
function caption(text){return `<p class="cg-caption">${text}</p>`;}
function board(){
 const a=state.ag,g=current(),info=a.info,live=info?.phase==='play',locked=agLocked(),d=info?.detail,done=info?.phase==='done'&&!a.animating,step=info?.step||0;
 let html='';
 if(a.game==='diamonds')html=`<div class="cg-gems ${a.animating?'cg-tumble':''}">${(done?d.gems:[1,5,2,4,0]).map(gem).join('')}</div>${caption(done?'Комбинация кристаллов':'Пять независимых кристаллов')}`;
 else if(a.game==='videopoker')html=`<div class="cg-cards">${Array.from({length:5},(_,i)=>`<button type="button" class="cg-card ${(a.held||[]).includes(i)?'is-held':''} ${a.animating&&!info.held?.includes(i)?'cg-deal':''}" data-cg-hold="${i}" ${!live||locked?'disabled':''} aria-pressed="${(a.held||[]).includes(i)}" aria-label="Оставить карту ${i+1}">${card(info?.cards?.[i])}<small>${(a.held||[]).includes(i)?'ОСТАВИТЬ':'ВЫБРАТЬ'}</small></button>`).join('')}</div>${caption(done?d?.combination||'Раздача завершена':'Один обмен · можно оставить от 0 до 5 карт')}`;
 else if(a.game==='limbo')html=`<div class="cg-limbo ${a.animating?'is-running':''}"><i></i><b id="cg-limbo-value">${done?agNumber(d.value):'1.00'}×</b><small>Цель ${agNumber(a.options.limbo.target)}×</small></div>`;
 else if(a.game==='sicbo')html=`<div class="cg-dice ${a.animating?'cg-shake':''}">${(done?d.dice:[1,3,5]).map(dice).join('')}</div>${caption(done?`Сумма ${d.sum}${d.triple?' · Тройка':''}`:'Малое · большое · любая тройка')}`;
 else if(a.game==='chicken')html=`<div class="cg-road ${a.animating?'is-walking':''}"><div class="cg-road-strip">${Array.from({length:7},(_,i)=>`<span class="${i<Math.min(step,6)?'is-passed':''}">${Math.max(0,step-5)+i+1}</span>`).join('')}</div><div class="cg-chicken ${info?.last?.safe===false?'cg-fallen':''}">${CasinoArt.svg('chicken')}</div><i class="cg-road-car"></i></div>${caption(`Пройдено ${step} участков`)}${live?button('Следующий шаг →',0,locked):''}`;
 else if(a.game==='coin')html=`<div class="cg-coin ${a.animating?'cg-flip':''}">${info?.last?(info.last.opponent===0?'♛':'♠'):'♛'}</div>${caption(info?.last?(info.last.opponent===0?'Выпал орёл':'Выпала решка'):'Выбери сторону следующего броска')}${live?`<div class="cg-choices">${button('Орёл',0,locked)}${button('Решка',1,locked)}</div>`:''}`;
 else if(a.game==='rps'){const hands=['✊','✋','✌'];html=`<div class="cg-rps"><span>${info?.last?hands[info.last.choice]:'✊'}</span><b>VS</b><span>${info?.last?hands[info.last.opponent]:'✋'}</span></div>${caption(info?.last?.tie?'Ничья — серия сохранена':'Камень · бумага · ножницы')}${live?`<div class="cg-choices">${['Камень','Бумага','Ножницы'].map((n,i)=>button(n,i,locked)).join('')}</div>`:''}`;}
 else if(a.game==='scratch')html=`<div class="cg-scratch-grid">${Array.from({length:9},(_,i)=>{const value=info?.grid?.[i];return `<button type="button" data-cg-scratch="${i}" class="cg-scratch-cell ${value?'is-open':''}" ${!live||locked||value?'disabled':''} aria-label="Стереть ячейку ${i+1}"><span>${value?(value==='win'?'✦':{a:'♠',b:'♣',c:'♥',d:'♦',e:'●'}[value]):'✧'}</span><i>${value?'':'СОТРИ'}</i></button>`;}).join('')}</div>${caption(done?`Приз билета: ${agNumber(info.prize)}×`:'Проведи пальцем или нажми на ячейку')}`;
 else if(a.game==='slots')html=`<div class="cg-slot-machine ${a.animating?'cg-spinning':''}">${Array.from({length:9},(_,i)=>`<div class="cg-slot-cell ${done&&d.lines[Math.floor(i/3)].payout?'is-line-win':''}" style="--delay:${i%3*150}ms">${done?symbols[d.grid[i]]:symbols[i%6]}</div>`).join('')}</div>${caption('Три горизонтальные линии · ставка делится на три')}`;
 else if(a.game==='andar'){const dealt=done?d.dealt:[],center=d?.center;html=`<div class="cg-andar"><div class="cg-center-card">${card(center)}</div><div class="cg-andar-sides">${['andar','bahar'].map((side,i)=>{const pile=dealt.filter((_,n)=>n%2===i),c=pile.at(-1);return `<div class="${done&&d.winner===side?'is-winner':''}"><b>${i?'Бахар':'Андар'}</b><div class="cg-small-card">${card(c)}</div><small>${pile.length} карт</small></div>`;}).join('')}</div></div>${caption(done?`Совпадение на стороне ${d.winner==='andar'?'Андар':'Бахар'}`:'До первого совпадения с центральной картой')}`;}
 else if(a.game==='penalty')html=`<div class="cg-goal"><div class="cg-net">${Array.from({length:5},(_,i)=>`<button type="button" data-cg-pick="${i}" ${!live||locked?'disabled':''} class="cg-goal-zone ${info?.last?.opponent===i?'is-keeper':''} ${info?.last?.choice===i?'is-shot':''}" aria-label="Удар в зону ${i+1}">${info?.last?.choice===i?'⚽':info?.last?.opponent===i?'🧤':i+1}</button>`).join('')}</div><div class="cg-pitch-ball">${CasinoArt.svg('ball')}</div></div>${caption(live?'Нажми на один из пяти углов ворот':`Голов: ${step}`)}`;
 else if(a.game==='darts')html=`<svg viewBox="0 0 320 260" class="cg-dartboard"><circle cx="160" cy="125" r="110" fill="#35204e"/><circle cx="160" cy="125" r="66" fill="#6b438a"/><circle cx="160" cy="125" r="33" fill="#b787d1"/><circle cx="160" cy="125" r="11" fill="#f0ce8e"/><g id="cg-dart" opacity="${done?1:0}" transform="translate(${done?160+110*d.radius*Math.sin(d.angle):160} ${done?125-110*d.radius*Math.cos(d.angle):125})"><path d="M0 0L20 -30 29 -35 25 -22Z" fill="#f8e1ff" stroke="#fff"/><circle r="3" fill="#fff"/></g></svg>${caption('Случайный бросок · равномерно по площади')}`;
 else if(a.game==='bowling')html=`<div class="cg-bowling"><div class="cg-pins">${Array.from({length:10},(_,i)=>`<span class="cg-pin ${done&&d.fallen[i]?'is-down':''}" data-cg-pin="${i}" style="--pin-x:${[15,38,61,84,27,50,73,38,61,50][i]}%;--pin-y:${[0,0,0,0,30,30,30,60,60,90][i]}px"></span>`).join('')}</div><i id="cg-bowling-ball"></i></div>${caption(done?`Сбито ${d.count} из 10${d.count===10?' · СТРАЙК':''}`:'Один бросок · десять кеглей')}`;
 else if(a.game==='balloon')html=`<div class="cg-balloon-scene ${info?.last?.safe===false?'is-popped':''}"><div class="cg-balloon" style="--inflate:${1+Math.min(step,20)*.025}">${CasinoArt.svg('balloon')}</div><b>${agNumber(info?.multiplier||1)}×</b></div>${live?button('Надуть ещё',0,locked):caption(info?.last?.safe===false?'Шар лопнул':'Каждый качок — следующий шаг')}`;
 else if(a.game==='cases')html=`<div class="cg-case ${a.animating?'cg-shake':''}">${CasinoArt.svg('case')}<span class="cg-case-prize">${done?agNumber(d.prize)+'×':'?'}</span></div>${caption(done?(d.prize?'Приз из контейнера':'Пустой контейнер'):'Обычный · редкий · эпический · легендарный')}`;
 else if(a.game==='race')html=`<div class="cg-race">${Array.from({length:4},(_,i)=>`<div class="cg-race-lane ${done&&d.winner===i?'is-winner':''}"><b>${i+1}</b><div class="cg-racer" data-cg-racer="${i}" style="left:${done?65-d.order.indexOf(i)*10:3}%">${CasinoArt.svg('race')}</div><i></i></div>`).join('')}</div>${caption(done?`Победил участник №${d.winner+1}`:'Все четыре участника равновероятны')}`;
 else if(a.game==='pinball')html=`<div class="cg-pinball"><svg viewBox="0 0 240 240"><rect x="20" y="5" width="200" height="222" rx="36" fill="#261833" stroke="#b28de0"/><g fill="#bc83eb" stroke="#f4dcff">${[[80,60],[160,88],[100,132]].map(([x,y],i)=>`<circle cx="${x}" cy="${y}" r="16" class="${info?.last?.bumper===i?'cg-lit':''}"/>`).join('')}</g><path d="M45 197L95 208M195 197L145 208" stroke="#e5be7e" stroke-width="10" stroke-linecap="round"/><circle id="cg-pinball-ball" cx="${info?.last?[80,160,100][info.last.bumper]:170}" cy="${info?.last?.safe===false?221:info?.last?[39,67,111][info.last.bumper]:164}" r="6" fill="#fff"/></svg></div>${live?`<div class="cg-choices">${button('Левая лопатка',0,locked)}${button('Правая лопатка',1,locked)}</div>`:caption(`Отскоков: ${step}`)}`;
 else if(a.game==='fishing')html=`<div class="cg-fishing"><svg viewBox="0 0 320 240"><path d="M0 70Q40 57 80 70T160 70T240 70T320 70V240H0Z" fill="#243952"/><path d="M0 70Q40 57 80 70T160 70T240 70T320 70" fill="none" stroke="#94caeb"/><path d="M15 40L150 13 167 130Q168 148 156 146Q147 145 150 136" fill="none" stroke="#dbb477" stroke-width="3"/><g id="cg-fish" transform="translate(92 120) scale(.65)" opacity="${done&&d.prize?1:0}"><path d="M110 30Q65 -20 20 30Q65 80 110 30L139 6V54Z" fill="#a8c7ef"/><circle cx="42" cy="26" r="4" fill="#152039"/></g></svg><b>${done?d.prize?agNumber(d.prize)+'×':'Пусто':'Забрось удочку'}</b></div>`;
 else if(a.game==='collection')html=`<div class="cg-collection">${Array.from({length:9},(_,i)=>`<div class="${i<step?'is-collected':''}">${i<step?gem(i):'<span>?</span>'}</div>`).join('')}</div>${caption(info?.last?.safe===false?'Опасный символ · коллекция потеряна':`Собрано ${step} из 9`)}${live?button('Открыть следующий символ',0,locked):''}`;
 $('ag-stage').innerHTML=`<div class="cg-board cg-game-${g.kind}">${html}</div>`;
}
function animate(info){
 const a=state.ag,game=a.game,token=++a.token,reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 const duration=reduced?0:info.phase==='play'?900:game==='race'?3200:game==='andar'?2200:game==='bowling'?2100:1500,start=performance.now();
 const tick=now=>{
  if(token!==a.token||a.game!==game)return;
  const t=duration?Math.min(1,(now-start)/duration):1,d=info.detail;
  if(game==='limbo')$('cg-limbo-value').textContent=agNumber(1+(d.value-1)*(1-(1-t)**3))+'×';
  if(game==='darts'){const el=$('cg-dart');el?.setAttribute('opacity',t>.5?1:0);if(el)el.setAttribute('transform',`translate(${160+110*d.radius*Math.sin(d.angle)} ${125-110*d.radius*Math.cos(d.angle)-(1-t)*150})`);}
  if(game==='race')for(let i=0;i<4;i++){const car=$('ag-stage').querySelector(`[data-cg-racer="${i}"]`);if(car)car.style.left=(3+(62-d.order.indexOf(i)*10)*t+Math.sin(t*Math.PI*2+i)*8*Math.sin(t*Math.PI))+'%';}
  if(game==='bowling'){const ball=$('cg-bowling-ball');if(ball)ball.style.transform=`translateY(${-Math.min(1,t*1.6)*125}px) scale(${1-Math.min(1,t*1.6)*.5})`;if(t>.65)d.fallen.forEach((hit,i)=>{if(hit)$('ag-stage').querySelector(`[data-cg-pin="${i}"]`)?.classList.add('is-down');});}
  if(game==='pinball'&&info.last){const b=$('cg-pinball-ball'),old=a.cgPrevious?.last,from=old?[80,160,100][old.bumper]:170,fromY=old?[39,67,111][old.bumper]:164,to=[80,160,100][info.last.bumper],toY=info.last.safe?[39,67,111][info.last.bumper]:221;if(b){b.setAttribute('cx',from+(to-from)*t);b.setAttribute('cy',fromY+(toY-fromY)*t-24*Math.sin(t*Math.PI));}}
  if(game==='fishing')$('cg-fish')?.setAttribute('opacity',t>.65&&d.prize?1:0);
  if(t<1)a.raf=requestAnimationFrame(tick);else{a.animating=false;renderArcade();agResult();}
 };
 a.raf=requestAnimationFrame(tick);
}
function changed(){state.ag.held=[];}
function settingEvent(event){
 const a=state.ag;if(!isGame(a.game)||agLocked()||a.info?.phase==='play')return;
 const el=event.target.closest('[data-cg-option]');if(el){const g=current(),pair=g.choices.find(([,v])=>String(v)===el.dataset.cgOption);if(!pair)return;a.options[a.game][el.dataset.cgKey]=pair[1];renderArcade();}
}
function targetChange(event){
 if(event.target.id!=='cg-target'||state.ag.game!=='limbo'||agLocked()||state.ag.info?.phase==='play')return;
 const n=Number(event.target.value.replace(',','.'));
 if(!Number.isFinite(n)||n<1.01||n>10000||Math.abs(n*100-Math.round(n*100))>1e-6){toast('Коэффициент от 1.01 до 10000, до двух знаков');event.target.value=state.ag.options.limbo.target;return;}
 state.ag.options.limbo.target=n;renderArcade();
}
function boardEvent(event){
 const a=state.ag;if(!isGame(a.game)||agLocked()||a.info?.phase!=='play')return;
 const hold=event.target.closest('[data-cg-hold]');if(hold){a.held??=[];const n=Number(hold.dataset.cgHold),i=a.held.indexOf(n);if(i<0)a.held.push(n);else a.held.splice(i,1);renderArcade();return;}
 const pick=event.target.closest('[data-cg-pick]');if(pick&&!pick.disabled)agRequest('pick',{index:Number(pick.dataset.cgPick)});
 const scratch=event.target.closest('[data-cg-scratch]');if(scratch&&!scratch.disabled)agRequest('pick',{index:Number(scratch.dataset.cgScratch)});
}
function bind(){
 $('ag-settings').addEventListener('click',settingEvent);$('ag-settings').addEventListener('change',targetChange);
 $('ag-stage').addEventListener('click',boardEvent);
 $('ag-stage').addEventListener('pointermove',event=>{if(state.ag.game!=='scratch'||!event.buttons)return;const cell=document.elementFromPoint(event.clientX,event.clientY);if(cell)boardEvent({target:cell});});
}
return {isGame,prepare,setup,settings,paytable,afterRender,main,board,animate,changed,bind,seriesTable};
})();
