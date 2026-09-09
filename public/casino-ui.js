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
 host.innerHTML=CasinoRules.ids.map(id=>{const g=definitions[id];return `<button type="button" data-arcade="${id}" class="cg-launch"><span class="cg-launch-art">${id==='diamonds'?`<span class="dm-cover">${flatDiamond(1)}${flatDiamond(0)}${flatDiamond(2)}</span>`:id==='videopoker'?videoCover():CasinoArt.cover(id)}</span><span class="cg-launch-name">${g.name}</span><small>${g.tag}</small></button>`;}).join('');
}
function settings(){
 const a=state.ag,g=current(),options=a.options[a.game],disabled=agLocked()||a.info?.phase==='play',attr=disabled?'disabled':'';
 if(g.choices){const key=a.game==='chicken'||a.game==='balloon'?'level':'side';return `<span class="mn-label">${key==='level'?'Сложность':'Выбор до ставки'}</span><div class="cg-choices">${g.choices.map(([name,value])=>`<button type="button" class="ag-choice ${options[key]===value?'is-selected':''}" data-cg-option="${value}" data-cg-key="${key}" ${attr} aria-pressed="${options[key]===value}">${name}</button>`).join('')}</div>`;}
 return `<p class="ag-note">${g.tag}</p>`;
}
function seriesTable(game,options){
 let size,bad,max,p=1;const level=options.level;
 if(game==='chicken'||game==='balloon'){size=game==='chicken'?21:25;bad={easy:1,medium:3,hard:5}[level];max=size-bad;}
 else max=game==='penalty'?5:game==='pinball'?10:20;
 return Array.from({length:max},(_,i)=>{p*=size?(size-bad-i)/(size-i):game==='coin'||game==='rps'?.5:.8;return Math.floor((.98/p+1e-10)*100)/100;});
}
function paytable(){const a=state.ag,g=current();const table=g.series?seriesTable(a.game,a.options[a.game]).map((n,i)=>[`${i+1} шаг`,n]):g.table;return (table||[]).map(([label,value])=>`<span class="ag-pay is-positive"><small>${label}</small><b>${agNumber(value)}×</b></span>`).join('');}
function afterRender(){
 const a=state.ag,g=current(),info=a.info,live=info?.phase==='play',pending=info?.phase==='done'&&!info.settled,main=$('ag-main');
 $('ag-title').classList.toggle('ag-long-title',g.name.length>15);
 $('screen-ag').classList.toggle('is-diamonds',a.game==='diamonds');
 $('screen-ag').classList.toggle('is-videopoker',a.game==='videopoker');
 $('screen-ag').classList.toggle('is-sicbo',a.game==='sicbo');
 $('screen-ag').classList.toggle('vp-is-live',a.game==='videopoker'&&live);
 if(a.game==='videopoker')$('ag-subtitle').textContent='Jacks or Better';
 if(a.game==='diamonds')$('ag-subtitle').textContent='Собери одинаковые кристаллы';
 if(a.game==='sicbo'){
  $('ag-subtitle').textContent='Три кубика — один бросок';
  if(!pending)main.textContent=a.animating?'Кубики брошены…':a.pending?'Подождите…':'Бросить кубики';
 }
 if(!live)return;
 const locked=agLocked();
 main.disabled=locked;main.classList.toggle('is-cash',Boolean(g.series));
 if(g.series){main.textContent=info.step?'Забрать '+money(info.available):'Вернуть ставку';$('ag-status').textContent=locked?'Подождите…':info.last?.tie?'Ничья · серия сохранена':`Успешных ходов: ${info.step||0}`;}
 else if(a.game==='videopoker'){const n=5-(a.held||[]).length;main.textContent=a.animating?'Раздаём карты…':a.pending?'Подождите…':n?`Заменить ${n} ${n===1?'карту':n===5?'карт':'карты'}`:'Оставить все карты';$('ag-status').textContent='Отметь карты, которые оставляешь';}
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
const caption=text=>`<p class="cg-caption">${text}</p>`;
const plaque=text=>`<div class="cg-scene-plaque">${text}</div>`;
const particles=()=>`<div class="cg-particles" aria-hidden="true">${Array.from({length:12},(_,i)=>`<i style="--n:${i};--a:${i*30}deg"></i>`).join('')}</div>`;
const diamondPatterns=[[0,0,0,0,0],[0,0,0,0,1],[0,0,0,1,1],[0,0,0,1,2],[0,0,1,1,2],[0,0,1,2,3],[0,1,2,3,4]];
const diamondLabels=['Пять одинаковых','Четыре одинаковых','Фулл-хаус','Три одинаковых','Две пары','Пара','Нет совпадений'];
const diamondPays=[50,5,4,3,2,.1,0];
function flatDiamond(n){
 if(n==null)return '<svg class="dm-gem dm-gem-empty" viewBox="0 0 100 88" aria-hidden="true"><path d="M22 8H78L98 37 50 86 2 37Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/></svg>';
 const palette=['#a547f5','#32d5ca','#f5c840','#ef456b','#71d841','#528ff3','#ee85d3'];
 return `<svg class="dm-gem" viewBox="0 0 100 88" aria-hidden="true" style="color:${palette[n%7]}"><path d="M22 8H78L98 37 50 86 2 37Z" fill="currentColor"/><path d="M22 8L32 37H2Z" fill="#fff" opacity=".22"/><path d="M22 8H50L32 37Z" fill="#fff" opacity=".55"/><path d="M50 8H78L68 37Z" fill="#fff" opacity=".24"/><path d="M50 8L68 37H32Z" fill="#fff" opacity=".1"/><path d="M78 8L98 37H68Z" fill="#180632" opacity=".19"/><path d="M2 37H32L50 86Z" fill="#17052c" opacity=".25"/><path d="M68 37H98L50 86Z" fill="#18052f" opacity=".35"/><path d="M32 37H68L50 86Z" fill="#fff" opacity=".08"/></svg>`;
}
function diamondResult(info){
 const gems=info?.detail?.gems||[];
 const counts=new Map();for(const n of gems)counts.set(n,(counts.get(n)||0)+1);
 const example=[...counts.entries()].sort((a,b)=>b[1]-a[1]).flatMap(([color,count])=>Array(count).fill(count>1?color:null));
 return {row:diamondPays.indexOf(info?.multiplier),matched:gems.map(n=>(counts.get(n)||0)>1),example};
}
function diamondBoard(info,animating){
 const done=info?.phase==='done'&&!animating,result=diamondResult(info),gems=info?.detail?.gems;
 return `<div class="dm-panel"><div class="dm-gems">${Array.from({length:5},(_,i)=>`<div class="dm-tile ${done&&result.matched[i]?'is-match':''}"><div class="dm-gem-motion" data-cg-gem="${i}">${flatDiamond(gems?.[i]??i)}</div></div>`).join('')}</div><div class="dm-result" role="status" aria-live="polite"><span class="dm-combination">${done?`${diamondLabels[result.row]} · ${agNumber(info.multiplier)}×`:animating?'Открываем кристаллы…':'Собери одинаковые кристаллы'}</span><b>${done?money(info.payout):'—'}</b><small>${done?'Выплата':'Результат раунда'}</small></div><div class="dm-paytable" role="table" aria-label="Комбинации и коэффициенты">${diamondPatterns.map((pattern,i)=>`<div class="dm-pay-row ${done&&result.row===i?'is-selected':''}" role="row" ${done&&result.row===i?'aria-current="true"':''}><span role="cell">${diamondLabels[i]}</span><span class="dm-example" role="cell" aria-label="Пример комбинации">${pattern.map((_,j)=>flatDiamond(done&&result.row===i?result.example[j]:null)).join('')}</span><b role="cell">${diamondPays[i]}×</b></div>`).join('')}</div></div>`;
}
function classicCard(c){
 if(!c)return '<div class="vp-card-back"></div>';
 const suit={s:'spade',c:'club',h:'heart',d:'diamond'}[c.suit];
 const rank=({14:'1',13:'king',12:'queen',11:'jack'})[c.rank]||String(c.rank);
 return `<svg class="vp-card-art" viewBox="0 0 169.075 244.640" aria-hidden="true"><use href="/img/classic/deck.svg#${suit}_${rank}"/></svg>`;
}
function videoCover(){return `<span class="vp-cover">${classicCard({rank:14,suit:'s'})}${classicCard({rank:13,suit:'h'})}</span>`;}
function videoHandName(info){
 const hand=info?.hand;if(!hand)return '';
 if(hand.multiplier!==1)return hand.name;
 const pair=info.cards.find(c=>c.rank>=11&&info.cards.filter(other=>other.rank===c.rank).length===2);
 return pair?`Пара ${{11:'валетов',12:'дам',13:'королей',14:'тузов'}[pair.rank]}`:hand.name;
}
function videoBoard(info,animating,locked){
 const a=state.ag,live=info?.phase==='play',done=info?.phase==='done'&&!animating;
 const hand=animating?null:info?.hand,selected=hand?.multiplier||0;
 const heading=done?'Раздача завершена':live?'Выберите карты':'Ваша следующая раздача';
 const status=animating?'Раздаём карты…':!state.connected?'Восстанавливаем связь…':hand?videoHandName(info):'Сделайте ставку';
 const note=done?`Выплата ${money(info.payout)}`:live?'Текущая комбинация':'Можно заменить до 5 карт';
 const cards=Array.from({length:5},(_,i)=>{
  const kept=info?.phase==='done'?info.held?.includes(i):(a.held||[]).includes(i),c=info?.cards?.[i];
  const name=c?`${({14:'Туз',13:'Король',12:'Дама',11:'Валет'})[c.rank]||c.rank} ${{s:'пик',c:'треф',h:'червей',d:'бубен'}[c.suit]}`:`Карта ${i+1}`;
  return `<button type="button" class="vp-card ${kept?'is-held':''}" data-cg-hold="${i}" ${!live||locked?'disabled':''} aria-pressed="${Boolean(kept)}" aria-label="${name}${live?kept?', оставить':', заменить':''}"><span class="cg-card-turn" style="transform:rotateY(${c&&(!animating||kept&&info.phase==='done')?180:0}deg)"><span class="vp-card-back"></span><span class="vp-card-front">${classicCard(c)}</span></span>${kept?'<span class="vp-held-check" aria-hidden="true"><svg viewBox="0 0 16 16"><path d="m4 8 3 3 5-6"/></svg></span>':''}<small>${live?kept?'ОСТАВИТЬ':'ЗАМЕНИТЬ':info?.phase==='done'?kept?'ОСТАВЛЕНА':'НОВАЯ':'—'}</small></button>`;
 }).join('');
 const crown='<svg class="vp-crown" viewBox="0 0 24 24" aria-hidden="true"><path d="m3 7 5 4 4-7 4 7 5-4-3 12H6ZM6 21h12"/></svg>';
 const table=[...definitions.videopoker.table].reverse().map(([label,value])=>`<div class="vp-pay-tile${value===800?' is-royal':''}${selected===value?' is-selected':''}" role="listitem" ${selected===value?'aria-current="true"':''}>${value===800?crown:''}<span>${label}</span><b>${value}×</b></div>`).join('');
 return `<div class="vp-hand-panel"><h2>${heading}</h2><div class="vp-cards">${cards}</div><div class="vp-hand-status" role="status" aria-live="polite"><span><b>${status}</b><small>${note}</small></span><strong>${hand?`${hand.multiplier}×`:'—'}</strong></div></div><div class="vp-paytable"><h2>Комбинации</h2><div class="vp-pay-grid" role="list" aria-label="Комбинации и коэффициенты Jacks or Better">${table}</div></div>`;
}
const sbPips={1:[4],2:[0,8],3:[0,4,8],4:[0,2,6,8],5:[0,2,4,6,8],6:[0,2,3,5,6,8]};
function sicboCube(value,index){
 // Rigid six-face die: opposite faces always add to seven.
 const adjacent={1:[2,3],2:[3,1],3:[1,2],4:[2,1],5:[1,3],6:[3,2]}[value];
 const faces=[adjacent[0],7-adjacent[0],adjacent[1],7-adjacent[1],value,7-value];
 return `<div class="sb-die sb-die-${index}" data-sb-die="${index}" role="img" aria-label="Кубик ${index+1}: ${value}"><span class="sb-shadow"></span><div class="sb-lift"><div class="sb-cube" style="transform:rotateX(-58deg) rotateY(26deg) rotateZ(${[-10,12,-8][index]}deg)">${faces.map((n,f)=>`<span class="sb-face sb-face-${f}" data-face-value="${n}">${Array.from({length:9},(_,j)=>`<i class="${sbPips[n].includes(j)?'is-pip':''}"></i>`).join('')}</span>`).join('')}</div></div></div>`;
}
function sicboBoard(info,animating,locked){
 const done=info?.phase==='done'&&!animating,d=info?.detail,chosen=state.ag.options.sicbo.side;
 const result=done?(d.triple?'Тройка':d.sum<=10?'Малое':'Большое'):animating?'Бросаем…':'Выберите исход';
 const history=(animating?state.ag.cgPrevious?.history:info?.history)||[];
 const rolls=history.filter(r=>Number.isInteger(r.sum)).slice(0,5).reverse();
 return `<div class="sb-play"><div class="sb-tray"><div class="sb-rim"></div><div class="sb-felt"></div><div class="sb-dice" ${animating?'aria-hidden="true"':''}>${(d?.dice||[3,4,5]).map(sicboCube).join('')}</div></div><div class="sb-result ${done&&info.payout?'is-paid':''}" role="status" aria-live="polite"><div><small>Сумма</small><b>${done?d.sum:'—'}</b></div><strong>${result}</strong><div><small>Выплата</small><b>${done?money(info.payout):'—'}</b></div></div></div><section class="sb-outcomes"><h2>Выберите исход</h2><div class="sb-choices">${[['small','Малое','4–10',2],['big','Большое','11–17',2],['triple','Любая тройка','Три одинаковых',31]].map(([id,label,range,pay])=>`<button type="button" data-sb-side="${id}" class="sb-choice ${chosen===id?'is-selected':''}" aria-pressed="${chosen===id}" ${locked||info?.phase==='done'&&!info.settled?'disabled':''}><span>${label}</span><small>${range}</small><b>${pay}×</b></button>`).join('')}</div><p>Тройка не выигрывает в малом и большом</p></section><section class="sb-history"><h2>Последние броски</h2><div>${rolls.length?rolls.map((r,i)=>`<span class="${i===rolls.length-1?'is-latest':''}" aria-label="Сумма ${r.sum}${r.triple?', тройка':''}">${r.sum}${r.triple?'<small>×3</small>':''}</span>`).join(''):'<p>Здесь появятся результаты бросков</p>'}</div></section>`;
}
function board(){
 const a=state.ag,g=current(),info=a.info,live=info?.phase==='play',locked=agLocked(),d=info?.detail,done=info?.phase==='done'&&!a.animating,step=info?.step||0;
 const visual=a.animating?a.cgPrevious:info,last=visual?.last,visibleStep=visual?.step||0;
 let html='';
 if(a.game==='diamonds')html=diamondBoard(info,a.animating);
 else if(a.game==='videopoker')html=videoBoard(info,a.animating,locked);
 else if(a.game==='sicbo')html=sicboBoard(info,a.animating,locked);
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
 if(game==='sicbo')f.dice.forEach((v,i)=>{transform(`[data-sb-die="${i}"]`,`translate(${v.x}%,${v.y}%)`);transform(`[data-sb-die="${i}"] .sb-lift`,`translateY(${-v.height}px)`);transform(`[data-sb-die="${i}"] .sb-cube`,`rotateX(${v.rx}deg) rotateY(${v.ry}deg) rotateZ(${v.rz}deg)`);transform(`[data-sb-die="${i}"] .sb-shadow`,`scale(${v.shadow})`);});
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
function boardEvent(event){
 const a=state.ag;
 if(a.game==='sicbo'){
  const choice=event.target.closest('[data-sb-side]');
  if(choice&&!choice.disabled&&!agLocked()&&!(a.info.phase==='done'&&!a.info.settled)&&['small','big','triple'].includes(choice.dataset.sbSide)){a.options.sicbo.side=choice.dataset.sbSide;renderArcade();}
  return;
 }
 if(!isGame(a.game)||agLocked()||a.info?.phase!=='play')return;
 const hold=event.target.closest('[data-cg-hold]');if(hold){a.held??=[];const n=Number(hold.dataset.cgHold),i=a.held.indexOf(n);if(i<0)a.held.push(n);else a.held.splice(i,1);renderArcade();return;}
 const pick=event.target.closest('[data-cg-pick]');if(pick&&!pick.disabled)agRequest('pick',{index:Number(pick.dataset.cgPick)});

}
function bind(){
 $('ag-settings').addEventListener('click',settingEvent);
 $('ag-stage').addEventListener('click',boardEvent);

}
return {isGame,prepare,setup,settings,paytable,afterRender,main,board,animate,changed,bind,seriesTable,paint,diamondResult};
})();
