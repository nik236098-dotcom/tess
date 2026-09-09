'use strict';
const CasinoUI=(()=>{
const definitions=CasinoRules.games,colors=['#65d7a2','#b183ed','#f0cc69','#e47593','#72d7e5','#ec9eda','#81a2ef'];
const symbols=['♣','♦','♥','♠','✦','♛'];
const isGame=game=>Object.hasOwn(definitions,game);
const current=()=>definitions[state.ag.game];
const button=(label,index,disabled=false,cls='')=>`<button type="button" class="cg-action ${cls}" data-cg-pick="${index}" ${disabled?'disabled':''}>${label}</button>`;
function prepare(game){if(!isGame(game))return;state.ag.options[game]??=structuredClone(definitions[game].defaults);state.ag.held=[];state.ag.cgTime=0;state.ag.cgPrevious=null;}
function setup(){
 const host=$('casino-catalog');if(!host)return;
 host.innerHTML=CasinoRules.ids.map(id=>{const g=definitions[id];return `<button type="button" data-arcade="${id}" class="cg-launch"><span class="cg-launch-art">${CasinoArt.cover(id)}</span><span class="cg-launch-name">${g.name}</span><small>${g.tag}</small></button>`;}).join('');
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
 if(!pending)$('ag-note').textContent=g.series?'Раунд сохранён. Можно продолжить или забрать.':'Раунд сохранён: можно выйти и вернуться.';
}
function main(){
 const a=state.ag;if(!isGame(a.game))return false;
 if(a.info?.phase==='play'&&a.game==='videopoker'){agRequest('pick',{index:[...(a.held||[])]});return true;}
 return false;
}
const art=(key,cls='')=>CasinoArt.sprite(key,cls);
function card(c){
 if(!c)return '<div class="cg-card-back"></div>';
 const rank=c.rank===14?'A':c.rank===13?'K':c.rank===12?'Q':c.rank===11?'J':c.rank,suit={s:'♠',c:'♣',h:'♥',d:'♦'}[c.suit];
 return `<div class="cg-card-face ${c.suit==='h'||c.suit==='d'?'is-red':''}" data-rank="${rank}"><b>${rank}<small>${suit}</small></b>${c.rank>=11&&c.rank<=13?'<i class="cg-court"></i>':`<span>${suit}</span>`}<b class="cg-bottom">${rank}<small>${suit}</small></b></div>`;
}
function turnCard(c,angle=180){return `<div class="cg-card-turn" style="transform:rotateY(${angle}deg)"><div class="cg-card-back"></div>${card(c)}</div>`;}
function gem(n,i=0){return `<span class="cg-gem" data-cg-gem="${i}" style="--hue:${[95,0,195,290,140,325,35][n%7]}deg">${art('gem')}<i></i></span>`;}
function dice(n,i=0){return `<div class="cg-die" data-cg-die="${i}"><div class="cg-die-face" data-value="${n}">${Array.from({length:9},(_,j)=>`<i class="${({1:[4],2:[0,8],3:[0,4,8],4:[0,2,6,8],5:[0,2,4,6,8],6:[0,2,3,5,6,8]}[n]).includes(j)?'is-dot':''}"></i>`).join('')}</div></div>`;}
const caption=text=>`<p class="cg-caption">${text}</p>`;
const plaque=text=>`<div class="cg-scene-plaque">${text}</div>`;
const particles=()=>`<div class="cg-particles" aria-hidden="true">${Array.from({length:12},(_,i)=>`<i style="--n:${i};--a:${i*30}deg"></i>`).join('')}</div>`;
function board(){
 const a=state.ag,g=current(),info=a.info,live=info?.phase==='play',locked=agLocked(),d=info?.detail,done=info?.phase==='done'&&!a.animating,step=info?.step||0;
 const visual=a.animating?a.cgPrevious:info,last=visual?.last,visibleStep=visual?.step||0;
 let html='';
 if(a.game==='diamonds')html=`<div class="cg-scene cg-jewel-scene">${plaque('DIAMONDS')}<div class="cg-gems">${(d?.gems||[1,5,2,4,0]).map(gem).join('')}</div><div class="cg-jewel-tray"></div>${particles()}</div>${caption(done?`Комбинация · ${agNumber(info.multiplier)}×`:'Пять кристаллов · семь цветов')}`;
 else if(a.game==='videopoker')html=`<div class="cg-scene cg-card-table">${plaque('JACKS OR BETTER')}<div class="cg-cards">${Array.from({length:5},(_,i)=>{const held=(a.held||[]).includes(i);return `<button type="button" class="cg-card ${held?'is-held':''}" data-cg-hold="${i}" ${!live||locked?'disabled':''} aria-pressed="${held}" aria-label="Оставить карту ${i+1}">${turnCard(info?.cards?.[i],info?.cards&&!a.animating?180:0)}<small>${live?held?'ОСТАВИТЬ':'ВЫБРАТЬ':info?.held?.includes(i)?'ОСТАВЛЕНА':''}</small></button>`;}).join('')}</div></div>${caption(done?d?.combination||'Раздача завершена':'Отметь карты для сохранения · один обмен')}`;
 else if(a.game==='limbo')html=`<div class="cg-scene cg-limbo"><div class="cg-starfield"></div><div class="cg-limbo-readout"><small>ТЕКУЩИЙ КОЭФФИЦИЕНТ</small><b id="cg-limbo-value">${done?agNumber(d.value):'1.00'}×</b><span>Цель ${agNumber(a.options.limbo.target)}×</span></div><div id="cg-rocket" class="cg-rocket">${art('orbit')}<i class="cg-exhaust"></i></div><div class="cg-orbit-line"></div>${particles()}</div>`;
 else if(a.game==='sicbo')html=`<div class="cg-scene cg-dice-scene">${plaque('SIC BO')}<div class="cg-dice">${(done?d.dice:[1,3,5]).map(dice).join('')}</div><div class="cg-dice-tray"></div></div>${caption(done?`Сумма ${d.sum}${d.triple?' · Тройка':''}`:'Три кубика · выбери исход перед броском')}`;
 else if(a.game==='chicken')html=`<div class="cg-scene cg-road"><div class="cg-road-ground"></div><div class="cg-road-markers">${Array.from({length:4},(_,i)=>`<span>${visibleStep+i+1}</span>`).join('')}</div><div id="cg-chicken" class="cg-chicken">${art('chicken')}</div><div id="cg-road-car" class="cg-road-car">${art('race')}</div><div class="cg-road-start"></div>${plaque(`ШАГ ${visibleStep} · ${agNumber(visual?.multiplier||1)}×`)}${particles()}</div>${caption(info?.last?.safe===false&&!a.animating?'Столкновение · раунд завершён':`Пройдено ${visibleStep} участков`)}${live?button('Следующий шаг →',0,locked):''}`;
 else if(a.game==='coin')html=`<div class="cg-scene cg-coin-scene">${plaque('ОРЁЛ ИЛИ РЕШКА')}<div id="cg-coin-shadow" class="cg-coin-shadow"></div><div class="cg-coin-lift" id="cg-coin-lift"><div class="cg-coin" id="cg-coin" style="transform:rotateY(${last?.opponent===1?180:0}deg)"><div class="cg-coin-side cg-coin-front">${art('coin')}</div><div class="cg-coin-side cg-coin-reverse"><span>♠</span><small>POKERGENA</small></div></div></div></div>${caption(last?(last.opponent===0?'Выпал орёл':'Выпала решка'):'Выбери сторону следующего броска')}${live?`<div class="cg-choices">${button('Орёл',0,locked)}${button('Решка',1,locked)}</div>`:''}`;
 else if(a.game==='rps')html=`<div class="cg-scene cg-rps-scene">${plaque('ТВОЙ ХОД')}<div class="cg-rps"><div><span id="cg-hand-you">${art(['rock','paper','scissors'][last?.choice??0])}</span><small>ТЫ</small></div><b>VS</b><div><span id="cg-hand-house">${art(['rock','paper','scissors'][last?.opponent??0])}</span><small>СОПЕРНИК</small></div></div></div>${caption(last?.tie?'Ничья — серия сохранена':'Камень · бумага · ножницы')}${live?`<div class="cg-choices">${['Камень','Бумага','Ножницы'].map((n,i)=>button(n,i,locked)).join('')}</div>`:''}`;
 else if(a.game==='slots'){
  const grid=d?.grid||[0,1,2,3,4,5,2,1,0];
  html=`<div class="cg-scene cg-slots-scene"><div class="cg-slot-crown">CROC <b>SLOTS</b></div><div class="cg-slot-machine">${[0,1,2].map(col=>{const result=[grid[col],grid[col+3],grid[col+6]],strip=a.animating?[...Array.from({length:18},(_,i)=>(i*5+col)%6),...result]:result;return `<div class="cg-reel"><div class="cg-reel-strip" data-cg-reel="${col}" style="--symbols:${strip.length}">${strip.map((n,i)=>`<div class="cg-slot-cell ${done&&d?.lines?.[i]?.payout?'is-line-win':''}">${n===5?art('seven'):n===4?art('coin'):gem(n)}</div>`).join('')}</div></div>`;}).join('')}<div class="cg-reel-shade"></div></div><div class="cg-slot-footer"><i></i><span>3 ЛИНИИ</span><i></i></div></div>${caption('Ставка делится на три горизонтальные линии')}`;
 }
 else if(a.game==='andar')html=`<div class="cg-scene cg-andar cg-card-table">${plaque('ANDAR BAHAR')}<div class="cg-center-card">${card(d?.center)}</div><div class="cg-andar-sides">${['andar','bahar'].map((side,i)=>{const pile=done?d.dealt.filter((_,n)=>n%2===i):[];return `<div class="${done&&d.winner===side?'is-winner':''}" data-cg-side="${i}"><b>${i?'Бахар':'Андар'}</b><div class="cg-small-card" id="cg-andar-${i}">${card(pile.at(-1))}</div><small id="cg-andar-count-${i}">${pile.length} карт</small></div>`;}).join('')}</div><div class="cg-flying-card" id="cg-flying-card"></div></div>${caption(done?`Совпадение: ${d.winner==='andar'?'Андар':'Бахар'}`:'Раздача до первого совпадения по достоинству')}`;
 else if(a.game==='penalty')html=`<div class="cg-scene cg-goal">${plaque(`ПЕНАЛЬТИ · ${visibleStep} / 5`)}<div class="cg-net">${Array.from({length:5},(_,i)=>`<button type="button" data-cg-pick="${i}" ${!live||locked?'disabled':''} class="cg-goal-zone ${last?.choice===i?'is-shot':''}" aria-label="Удар в зону ${i+1}">${i+1}</button>`).join('')}</div><div class="cg-keeper" id="cg-keeper">${art('paper')}${art('paper')}</div><div class="cg-football" id="cg-football">${art('ball')}</div>${particles()}</div>${caption(live?'Выбери одну из пяти зон ворот':last?last.safe?'Гол!':'Вратарь отбил удар':'Пять зон · один удар')}`;
 else if(a.game==='darts')html=`<div class="cg-scene cg-darts-scene">${plaque('DARTS')}<div class="cg-dartboard"><div class="cg-dart-ring cg-ring-outer"></div><div class="cg-dart-ring cg-ring-mid"></div><div class="cg-dart-ring cg-ring-inner"></div><div class="cg-dart-ring cg-ring-bull"></div><span class="cg-target-label">20×</span><div id="cg-dart" class="cg-dart">${art('target')}</div></div></div>${caption(done?`Результат броска: ${agNumber(info.multiplier)}×`:'Бросок в мишень · зоны выплат в таблице')}`;
 else if(a.game==='bowling')html=`<div class="cg-scene cg-bowling">${plaque('BOWLING')}<div class="cg-pins">${Array.from({length:10},(_,i)=>`<div class="cg-pin" data-cg-pin="${i}" style="left:${[36,45,54,63,41,50,59,45,54,50][i]}%;top:${[22,22,22,22,28,28,28,34,34,40][i]}%">${art('pin')}</div>`).join('')}</div><div id="cg-bowling-ball" class="cg-bowling-ball">${art('bowling')}</div></div>${caption(done?`Сбито ${d.count} из 10${d.count===10?' · СТРАЙК':''}`:'Шар · дорожка · десять кеглей')}`;
 else if(a.game==='balloon')html=`<div class="cg-scene cg-balloon-scene">${plaque('PUMP')}<div class="cg-balloon" id="cg-balloon">${art('balloon')}<i class="cg-balloon-string"></i></div><div class="cg-pump"><i id="cg-pump-handle"></i><b></b><span></span></div><div class="cg-balloon-value">${agNumber(visual?.multiplier||1)}×</div>${particles()}</div>${caption(last?.safe===false?'Шар лопнул':`Успешных качков: ${visibleStep}`)}${live?button('Надуть ещё',0,locked):''}`;
 else if(a.game==='race')html=`<div class="cg-scene cg-race">${plaque('NIGHT RACE')}<div class="cg-race-finish"></div>${Array.from({length:4},(_,i)=>`<div class="cg-race-lane ${done&&d.winner===i?'is-winner':''}" style="--lane:${i}"><div class="cg-racer" data-cg-racer="${i}">${art('race')}<small>${i+1}</small></div></div>`).join('')}</div>${caption(done?`Первым финишировал №${d.winner+1}`:'Четыре участника · один финиш')}`;
 else if(a.game==='pinball')html=`<div class="cg-scene cg-pinball-scene"><div class="cg-pinball">${plaque('AMETHYST')}<div class="cg-pinball-rail"></div>${CasinoMotion.bumpers.map(([x,y],i)=>`<div class="cg-bumper" data-cg-bumper="${i}" style="left:${x}%;top:${y}%">${art('pinball')}</div>`).join('')}<i class="cg-flipper cg-flipper-left"></i><i class="cg-flipper cg-flipper-right"></i><div class="cg-pinball-ball" id="cg-pinball-ball"></div><div class="cg-drain"></div></div></div>${caption(`Отскоков: ${visibleStep}`)}${live?`<div class="cg-choices">${button('Левая лопатка',0,locked)}${button('Правая лопатка',1,locked)}</div>`:''}`;
 else if(a.game==='fishing')html=`<div class="cg-scene cg-fishing">${plaque('DEEP WATER')}<div class="cg-fishing-line" id="cg-fishing-line"><i></i></div><div id="cg-fish" class="cg-fish">${art('fish')}</div><div class="cg-bubbles"><i></i><i></i><i></i></div><b class="cg-fishing-prize">${done?d.prize?agNumber(d.prize)+'×':'Пусто':''}</b></div>${caption(done?'Улов поднят':'Забрось удочку и открой свой улов')}`;
 $('ag-stage').innerHTML=`<div class="cg-board cg-game-${g.kind} ${a.animating?'is-animating':''}">${html}</div>`;
 if(!a.animating&&info&&info.phase!=='bet'&&(info.last||done))paint(info,1);
 else if(a.animating)paint(info,a.cgTime||0);
}
function paint(info,t){
 const a=state.ag,game=a.game,f=CasinoMotion.frame(game,info,a.cgPrevious,t),d=info.detail||{},last=info.last||{},stage=$('ag-stage');
 const el=selector=>stage.querySelector(selector),style=(selector,key,value)=>{const node=el(selector);if(node)node.style[key]=value;};
 const transform=(selector,value)=>style(selector,'transform',value);
 const toggle=(selector,name,value)=>el(selector)?.classList.toggle(name,value);
 if(game==='diamonds')f.items.forEach((v,i)=>{transform(`[data-cg-gem="${i}"]`,`translateY(${v.y}px) rotate(${v.rotation}deg)`);style(`[data-cg-gem="${i}"]`,'opacity',v.opacity);});
 if(game==='videopoker')f.cards.forEach((v,i)=>{transform(`[data-cg-hold="${i}"] .cg-card-turn`,`translateY(${v.y}px) rotateY(${v.flip}deg)`);});
 if(game==='limbo'){const node=el('#cg-limbo-value');if(node)node.textContent=agNumber(f.value)+'×';style('#cg-rocket','left',f.x+'%');style('#cg-rocket','top',f.y+'%');toggle('.cg-limbo','is-flying',t<1);}
 if(game==='sicbo')f.dice.forEach((v,i)=>{transform(`[data-cg-die="${i}"]`,`translateY(${v.y}px) rotate(${v.angle}deg) scale(${v.scale})`);const face=el(`[data-cg-die="${i}"] .cg-die-face`),value=v.settled?d.dice?.[i]||1:1+(Math.floor(t*22)+i*2)%6;if(face&&face.dataset.value!==String(value)){face.dataset.value=String(value);face.innerHTML=dice(value).match(/<div class="cg-die-face"[^>]*>(.*?)<\/div>/)[1];}});
 if(game==='chicken'){style('#cg-chicken','left',f.x+'%');transform('#cg-chicken',`translate(-50%,${f.y}px) ${f.impact?'rotate(-75deg) scale(.7)':''}`);style('#cg-road-car','top',f.carY+'%');style('#cg-road-car','left',(last.safe===false?32:70)+'%');toggle('.cg-road','is-impact',f.impact);}
 if(game==='coin'){transform('#cg-coin',`rotateY(${f.angle}deg)`);transform('#cg-coin-lift',`translateY(${f.y}px)`);transform('#cg-coin-shadow',`scale(${f.shadow})`);}
 if(game==='rps'){for(const [id,index] of [['you',last.choice],['house',last.opponent]]){const node=el('#cg-hand-'+id);if(node){const key=f.reveal?['rock','paper','scissors'][index??0]:'rock';if(node.dataset.hand!==key){node.innerHTML=art(key);node.dataset.hand=key;}node.style.transform=`translateY(${f.y}px) scale(${f.scale})`;}}}
 if(game==='slots'&&a.animating)f.reels.forEach((r,i)=>{transform(`[data-cg-reel="${i}"]`,`translateY(${-r.position/21*100}%)`);toggle(`[data-cg-reel="${i}"]`,'is-spinning',!r.settled);});
 if(game==='andar'){
  const count=t===1?d.dealt?.length||0:f.count;
  for(let side=0;side<2;side++){const pile=(d.dealt||[]).slice(0,count).filter((_,i)=>i%2===side),node=el('#cg-andar-'+side),label=el('#cg-andar-count-'+side);if(node&&node.dataset.count!==String(pile.length)){node.innerHTML=card(pile.at(-1));node.dataset.count=String(pile.length);}if(label)label.textContent=pile.length+' карт';}
  const moving=el('#cg-flying-card');if(moving){const c=d.dealt?.[f.index];if(moving.dataset.index!==String(f.index)){moving.innerHTML=card(c);moving.dataset.index=String(f.index);}moving.style.opacity=t<.15||f.complete?0:1;moving.style.left=(50+(f.index%2?28:-28)*f.flight)+'%';moving.style.top=(29+42*f.flight)+'%';moving.style.transform=`translate(-50%,-50%) rotate(${(f.index%2?1:-1)*Math.sin(f.flight*Math.PI)*12}deg)`;}
 }
 if(game==='penalty'){style('#cg-football','left',f.x+'%');style('#cg-football','top',f.y+'%');transform('#cg-football',`translate(-50%,-50%) scale(${f.scale}) rotate(${f.rotation}deg)`);style('#cg-keeper','left',f.keeperX+'%');transform('#cg-keeper',`translateX(-50%) rotate(${(f.keeperX-50)*.7}deg)`);toggle('.cg-goal','is-goal',f.hit&&last.safe);}
 if(game==='darts'){style('#cg-dart','left',f.x+'%');style('#cg-dart','top',f.y+'%');style('#cg-dart','opacity',f.opacity);transform('#cg-dart',`translate(-18%,-82%) scale(${f.scale})`);toggle('.cg-dartboard','is-hit',f.hit);}
 if(game==='bowling'){style('#cg-bowling-ball','top',f.y+'%');transform('#cg-bowling-ball',`translate(-50%,-50%) scale(${f.scale}) rotate(${f.rotation}deg)`);style('#cg-bowling-ball','opacity',t>.85?Math.max(0,(1-t)/.15):1);f.pins.forEach((p,i)=>{transform(`[data-cg-pin="${i}"]`,`translate(-50%,-100%) translate(${(i%2?1:-1)*p.fall*20}px,${-p.fall*15}px) rotate(${p.angle}deg)`);style(`[data-cg-pin="${i}"]`,'opacity',1-p.fall*.9);});}
 if(game==='balloon'){transform('#cg-balloon',`translateX(-50%) scale(${f.scale})`);style('#cg-balloon','opacity',f.burst?0:1);transform('#cg-pump-handle',`translateY(${f.pump*16}px)`);toggle('.cg-balloon-scene','is-burst',f.burst);style('.cg-particles','--burst',f.burstProgress);}
 if(game==='race')f.cars.forEach((c,i)=>{style(`[data-cg-racer="${i}"]`,'top',c.y+'%');transform(`[data-cg-racer="${i}"]`,`translate(-50%,-50%) rotate(${t<1?Math.sin(t*20+i)*1.2:0}deg)`);});
 if(game==='pinball'){style('#cg-pinball-ball','left',f.x+'%');style('#cg-pinball-ball','top',f.y+'%');CasinoMotion.bumpers.forEach((_,i)=>toggle(`[data-cg-bumper="${i}"]`,'is-impact',f.impact&&i===last.bumper));transform(last.choice?'.cg-flipper-right':'.cg-flipper-left',`rotate(${t<.25?(last.choice?-1:1)*28*Math.sin(t/.25*Math.PI):0}deg)`);}
 if(game==='fishing'){style('#cg-fishing-line','height',f.hookY+'%');style('#cg-fish','left',f.fishX+'%');style('#cg-fish','top',f.fishY+'%');style('#cg-fish','opacity',f.reveal?1:0);transform('#cg-fish',`translate(-50%,-50%) rotate(${f.caught?-30:Math.sin(t*16)*5}deg)`);}
}
function animate(info){
 const a=state.ag,game=a.game,token=++a.token,reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 cancelAnimationFrame(a.raf);
 const duration=reduced?0:CasinoMotion.duration(game,info),start=performance.now();a.cgTime=0;
 const tick=now=>{
  if(token!==a.token||a.game!==game)return;
  const t=duration?Math.min(1,(now-start)/duration):1;a.cgTime=t;paint(info,t);
  if(t<1)a.raf=requestAnimationFrame(tick);else{a.animating=false;a.cgTime=0;renderArcade();agResult();}
 };
 a.raf=requestAnimationFrame(tick);
}
function changed(){state.ag.held=[];state.ag.cgTime=0;}
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

}
function bind(){
 $('ag-settings').addEventListener('click',settingEvent);$('ag-settings').addEventListener('change',targetChange);
 $('ag-stage').addEventListener('click',boardEvent);

}
return {isGame,prepare,setup,settings,paytable,afterRender,main,board,animate,changed,bind,seriesTable,paint};
})();
