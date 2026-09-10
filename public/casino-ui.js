'use strict';
const CasinoUI=(()=>{
const definitions=CasinoRules.games,colors=['#65d7a2','#b183ed','#f0cc69','#e47593','#72d7e5','#ec9eda','#81a2ef'];
const symbols=['♣','♦','♥','♠','✦','♛'];
const isGame=game=>Object.hasOwn(definitions,game);
const current=()=>definitions[state.ag.game];
const button=(label,index,disabled=false,cls='')=>`<button type="button" class="cg-action ${cls}" data-cg-pick="${index}" ${disabled?'disabled':''}>${label}</button>`;
function prepare(game){if(!isGame(game))return;if(game==='darts')DartsGame.reset();state.ag.options[game]??=structuredClone(definitions[game].defaults);state.ag.held=[];state.ag.cgTime=0;state.ag.cgPrevious=null;}
function setup(){
 const host=$('casino-catalog');if(!host)return;
 host.innerHTML=['abyss','midnight','cryo'].map(id=>GameCatalog.tile(id)).join('')+CasinoRules.ids.map(id=>GameCatalog.tile(id)).join('');
}
function settings(){
 const a=state.ag,g=current(),options=a.options[a.game],disabled=agLocked()||a.info?.phase==='play',attr=disabled?'disabled':'';
 const artLabel=(name,value,prefix)=>a.game==='coin'?coinFace(value,prefix)+`<span>${name}</span>`:a.game==='rps'?DuelArt.hand(value,prefix)+`<span>${name}</span>`:a.game==='race'?`<i class="rc-choice-mark" style="--car-color:${RaceScene.carColors[value]}" aria-hidden="true"></i><span>№${Number(value)+1}</span>`:a.game==='andar'?`<span>${value==='andar'?'Andar':'Bahar'}</span><small>${agNumber(g.table[value==='andar'?0:1][1])}×</small>`:name;
 if(a.info?.phase==='play'&&['coin','rps'].includes(a.game)){
  return `<div class="cg-choices g-live-choices">${g.choices.map(([label,i])=>button(artLabel(label,i,'live-'+a.game+'-'+i),i,agLocked())).join('')}</div>`;
 }
 if(g.choices){const key=a.game==='chicken'||a.game==='balloon'?'level':'side';return `<span class="mn-label">${key==='level'?'Сложность':'Выбор до ставки'}</span><div class="cg-choices">${g.choices.map(([name,value])=>`<button type="button" class="ag-choice ${options[key]===value?'is-selected':''}" data-cg-option="${value}" data-cg-key="${key}" ${attr} aria-pressed="${options[key]===value}">${artLabel(name,value,'choice-'+a.game+'-'+value)}</button>`).join('')}</div>`;}
 return '';
}
function seriesTable(game,options){
 let size,bad,max,p=1;const level=options.level;
 if(game==='chicken'||game==='balloon'){size=game==='chicken'?21:25;bad={easy:1,medium:3,hard:5}[level];max=size-bad;}
 else max=20;
 return Array.from({length:max},(_,i)=>{p*=size?(size-bad-i)/(size-i):game==='coin'||game==='rps'?.5:.8;return Math.floor((.98/p+1e-10)*100)/100;});
}
function paytable(){const a=state.ag,g=current();if(['race','fishing','andar'].includes(a.game))return '';const table=g.series?seriesTable(a.game,a.options[a.game]).map((n,i)=>[`${i+1} шаг`,n]):g.table;const step=(a.animating?a.cgPrevious:a.info)?.step||0;return (table||[]).map(([label,value],i)=>`<span class="ag-pay is-positive" ${g.series&&i===Math.max(0,step-1)?'aria-current="step"':''}><small>${label}</small><b>${agNumber(value)}×</b></span>`).join('');}
function afterRender(){
 const a=state.ag,g=current(),info=a.info,live=info?.phase==='play',pending=info?.phase==='done'&&!info.settled,main=$('ag-main');
 $('ag-title').classList.toggle('ag-long-title',g.name.length>15);
 $('screen-ag').classList.toggle('is-diamonds',a.game==='diamonds');
 $('screen-ag').classList.toggle('is-videopoker',a.game==='videopoker');
 $('screen-ag').classList.toggle('is-sicbo',a.game==='sicbo');
 $('screen-ag').classList.toggle('is-chicken',a.game==='chicken');
 $('screen-ag').classList.toggle('is-coin',a.game==='coin');
 $('screen-ag').classList.toggle('is-slots',a.game==='slots');
 $('screen-ag').classList.toggle('is-andar',a.game==='andar');
 $('screen-ag').classList.toggle('is-darts',a.game==='darts');
 $('screen-ag').classList.toggle('is-bowling',a.game==='bowling');
 $('screen-ag').classList.toggle('is-balloon',a.game==='balloon');
 $('screen-ag').classList.toggle('is-race',a.game==='race');
 $('screen-ag').classList.toggle('is-rps',a.game==='rps');
 $('screen-ag').classList.toggle('is-fishing',a.game==='fishing');
 $('screen-ag').classList.toggle('g-live',Boolean(live));
 $('ag-balloon-pump').hidden=a.game!=='balloon';
 $('ag-chicken-step').hidden=a.game!=='chicken'||!live;
 $('screen-ag').classList.toggle('vp-is-live',a.game==='videopoker'&&live);
 if(a.game==='videopoker')$('ag-subtitle').textContent='Jacks or Better';
 if(a.game==='diamonds')$('ag-subtitle').textContent='Собери одинаковые кристаллы';
 if(a.game==='chicken'){
  $('ag-subtitle').textContent='Каждый шаг — новый коэффициент';
  $('ag-chicken-step').disabled=agLocked();
  $('ag-chicken-step').textContent=a.animating?'Курица идёт…':'Следующий шаг →';
 }
 if(a.game==='sicbo'){
  $('ag-subtitle').textContent='Три кубика — один бросок';
  if(!pending)main.textContent=a.animating?'Кубики брошены…':a.pending?'Подождите…':'Бросить кубики';
 }
 if(a.game==='andar'&&!pending)main.textContent=a.animating?'Раздаём карты…':'Раздать карты';
 if(a.game==='darts')DartsGame.controls();
 if(a.game==='bowling'&&!pending){main.disabled=agLocked()||!BowlingScene.ready();main.textContent=a.animating?'Шар на дорожке…':a.pending?'Подождите…':BowlingScene.ready()?'Бросить шар':'Загружаем 3D…';}
 if(a.game==='balloon'){
  const pump=$('ag-balloon-pump');pump.disabled=agLocked()||Boolean(pending);
  pump.textContent=a.animating?'Надуваем…':a.pending?'Подождите…':live?'Надуть ещё':'Надуть шар';
  main.disabled=agLocked()||(!live&&!pending);main.classList.toggle('is-cash',live);
  main.textContent=pending?'Получить выплату':live?'Забрать '+money(info.available):'Забрать';
  $('ag-note').textContent=pending?'Выплата сохранена. Нажми «Получить выплату».':'Надувай шар или забирай выигрыш';
  return;
 }
 if(a.game==='race'&&!pending){main.disabled=agLocked()||!RaceScene.ready();main.textContent=a.animating?'Заезд идёт…':a.pending?'Подождите…':RaceScene.ready()?'Начать гонку ⚑':RaceScene.loadingLabel();}
 if(a.game==='slots'&&!pending)main.textContent=a.animating?'Барабаны крутятся…':'Крутить';
 if(a.game==='coin'&&!live&&!pending)main.textContent=a.animating?'Монета в воздухе…':a.pending?'Подождите…':'Бросить монету';
 if(a.game==='rps'&&!live&&!pending)main.textContent=a.animating?'Раскрываем жесты…':a.pending?'Подождите…':'Сделать ход';
 if(a.game==='fishing'&&!pending)main.textContent=a.animating?'Ловим рыбу…':a.pending?'Подождите…':'Забросить удочку';
 if(!live)return;
 const locked=agLocked();
 main.disabled=locked;main.classList.toggle('is-cash',Boolean(g.series));
 if(g.series){main.textContent=info.step?'Забрать '+money(info.available):'Вернуть ставку';$('ag-status').textContent=locked?'Подождите…':info.last?.tie?'Ничья · серия сохранена':`Успешных ходов: ${info.step||0}`;}
 else if(a.game==='videopoker'){const n=5-(a.held||[]).length;main.textContent=a.animating?'Раздаём карты…':a.pending?'Подождите…':n?`Заменить ${n} ${n===1?'карту':n===5?'карт':'карты'}`:'Оставить все карты';$('ag-status').textContent='Отметь карты, которые оставляешь';}
 if(!pending)$('ag-note').textContent=g.series?'Раунд сохранён. Можно продолжить или забрать.':'Раунд сохранён: можно выйти и вернуться.';
}
function main(){
 const a=state.ag;if(!isGame(a.game))return false;
 if(a.game==='race'&&!RaceScene.ready())return true;
 if(a.game==='balloon'&&a.info?.phase!=='play')return true;
 if(a.game==='darts')return DartsGame.enqueue();
 if(a.game==='bowling'&&!BowlingScene.ready()&&!(a.info?.phase==='done'&&!a.info.settled)){toast('Дождись загрузки 3D-сцены');return true;}
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
function videoCard(c){
 if(!c)return '';
 const suit={s:'♠',c:'♣',h:'♥',d:'♦'}[c.suit],rank=({14:'A',13:'K',12:'Q',11:'J'})[c.rank]||String(c.rank);
 return `<span class="vp-card-art${c.suit==='h'||c.suit==='d'?' is-red':''}" aria-hidden="true"><span class="vp-rank">${rank}</span><span class="vp-suit-sm">${suit}</span><span class="vp-suit">${suit}</span></span>`;
}
function videoCover(){return `<span class="vp-cover">${videoCard({rank:14,suit:'s'})}${videoCard({rank:13,suit:'h'})}</span>`;}
function videoCardName(c,i){return c?`${({14:'Туз',13:'Король',12:'Дама',11:'Валет'})[c.rank]||c.rank} ${{s:'пик',c:'треф',h:'червей',d:'бубен'}[c.suit]}`:`Карта ${i+1}`;}
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
  const name=videoCardName(c,i),face=Boolean(c&&(!animating||kept&&info.phase==='done'));
  return `<button type="button" class="vp-card ${kept?'is-held':''}" data-cg-hold="${i}" ${!live||locked?'disabled':''} aria-pressed="${Boolean(kept)}" aria-label="${name}${live?kept?', оставить':', заменить':''}"><span class="vp-card-motion"><span class="vp-card-back" ${face?'hidden':''}></span><span class="vp-card-front" ${face?'':'hidden'}>${videoCard(c)}</span></span><span class="vp-held-check" aria-hidden="true" ${kept?'':'hidden'}><svg viewBox="0 0 16 16"><path d="m4 8 3 3 5-6"/></svg></span><small class="vp-hold-label">${live?kept?'ОСТАВИТЬ':'ЗАМЕНИТЬ':info?.phase==='done'?kept?'ОСТАВЛЕНА':'НОВАЯ':'—'}</small></button>`;
 }).join('');
 const crown='<svg class="vp-crown" viewBox="0 0 24 24" aria-hidden="true"><path d="m3 7 5 4 4-7 4 7 5-4-3 12H6ZM6 21h12"/></svg>';
 const table=[...definitions.videopoker.table].reverse().map(([label,value])=>`<div class="vp-pay-tile${value===800?' is-royal':''}${selected===value?' is-selected':''}" role="listitem" ${selected===value?'aria-current="true"':''}>${value===800?crown:''}<span>${label}</span><b>${value}×</b></div>`).join('');
 return `<div class="vp-hand-panel"><h2>${heading}</h2><div class="vp-cards">${cards}</div><div class="vp-hand-status" role="status" aria-live="polite"><span><b>${status}</b><small>${note}</small></span><strong>${hand?`${hand.multiplier}×`:'—'}</strong></div></div><div class="vp-paytable"><h2>Комбинации</h2><div class="vp-pay-grid" role="list" aria-label="Комбинации и коэффициенты Jacks or Better">${table}</div></div>`;
}
function chickenBoard(info,animating){
 const a=state.ag,visual=animating?(a.cgPrevious||{}):(info||{}),step=visual.step||0;
 const coefficients=info?.coefficients||seriesTable('chicken',a.options.chicken);
 const failed=!animating&&info?.last?.safe===false,done=visual.phase==='done';
 const value=failed?0:step?visual.multiplier:1,payout=visual.available??visual.payout??0;
 return `<div class="ch-panel">${ChickenScene.scene({...visual,coefficients},animating?a.cgPrevious:null,animating)}<div class="ch-result${failed?' is-loss':done&&payout?' is-paid':''}" role="status" aria-live="polite"><div><small>${failed?'Раунд завершён':'Множитель'}</small><b>${failed?'Столкновение':Number(value).toFixed(2)+'×'}</b></div><div><small>${done?'Выплата':'Можно забрать'}</small><b>${money(payout)}</b></div></div></div>`;
}
function sicboBoard(info,animating,locked){
 const done=info?.phase==='done'&&!animating,d=info?.detail,chosen=state.ag.options.sicbo.side;
 const result=done?(d.triple?'Тройка':d.sum<=10?'Малое':'Большое'):animating?'Бросаем…':'Выберите исход';
 const history=(animating?state.ag.cgPrevious?.history:info?.history)||[];
 const rolls=history.filter(r=>Number.isInteger(r.sum)).slice(0,5).reverse();
 return `<div class="sb-play"><div class="sb-tray" id="sb-scene" role="img" aria-label="${animating?'Бросаем кубики':done?`Кубики ${d.dice.join(', ')}`:'Три кубика в лотке'}"><div class="sb-fallback" aria-hidden="true">${animating?'Бросаем кубики…':(d?.dice||[3,4,5]).map(n=>`<span>${['⚀','⚁','⚂','⚃','⚄','⚅'][n-1]}</span>`).join('')}</div></div><div class="sb-result ${done&&info.payout?'is-paid':''}" role="status" aria-live="polite"><div><small>Сумма</small><b>${done?d.sum:'—'}</b></div><strong>${result}</strong><div><small>Выплата</small><b>${done?money(info.payout):'—'}</b></div></div></div><section class="sb-outcomes"><h2>Выберите исход</h2><div class="sb-choices">${[['small','Малое','4–10',2],['big','Большое','11–17',2],['triple','Любая тройка','Три одинаковых',31]].map(([id,label,range,pay])=>`<button type="button" data-sb-side="${id}" class="sb-choice ${chosen===id?'is-selected':''}" aria-pressed="${chosen===id}" ${locked||info?.phase==='done'&&!info.settled?'disabled':''}><span>${label}</span><small>${range}</small><b>${pay}×</b></button>`).join('')}</div><p>Тройка не выигрывает в малом и большом</p></section><section class="sb-history"><h2>Последние броски</h2><div>${rolls.length?rolls.map((r,i)=>`<span class="${i===rolls.length-1?'is-latest':''}" aria-label="Сумма ${r.sum}${r.triple?', тройка':''}">${r.sum}${r.triple?'<small>×3</small>':''}</span>`).join(''):'<p>Здесь появятся результаты бросков</p>'}</div></section>`;
}
function coinFace(side,prefix){
 const emblem=side===1?'<path d="m100 48 15 32 35 5-25 25 6 36-31-17-31 17 6-36-25-25 35-5Z"/>':'<path d="M54 71Q84 36 116 57L108 66Q139 59 149 82L158 99Q139 88 121 99L138 106Q129 126 106 130L111 150Q90 139 83 119L69 136 72 113 52 122 62 98 44 105 58 82 44 86Z"/><path d="M103 78L124 75 116 84Z" fill="#684019"/><circle cx="116" cy="78" r="2" fill="#fff3b0"/>';
 return `<svg viewBox="0 0 200 200" aria-hidden="true"><defs><linearGradient id="${prefix}" x2=".8" y2="1"><stop stop-color="#fff3a4"/><stop offset=".38" stop-color="#f7ca59"/><stop offset=".7" stop-color="#ce8825"/><stop offset="1" stop-color="#ffdb70"/></linearGradient></defs><circle cx="100" cy="103" r="94" fill="#996019"/><circle cx="100" cy="98" r="92" fill="url(#${prefix})" stroke="#ffe9a0" stroke-width="3"/><circle cx="100" cy="98" r="80" fill="none" stroke="#a86b20" stroke-width="3"/><circle cx="100" cy="100" r="77" fill="none" stroke="#ffe39b" stroke-width="2"/><g fill="#e6ad40" stroke="#fff0ac" stroke-width="2" stroke-linejoin="round">${emblem}</g><path d="M29 69A77 77 0 0 1 111 23" fill="none" stroke="#fff9d7" stroke-width="4" stroke-linecap="round" opacity=".7"/></svg>`;
}
function coinBoard(info,animating){
 const a=state.ag,v=animating?a.cgPrevious:info,last=v?.last,side=last?.opponent??a.options.coin.side??0;
 const picks=['Орёл','Решка'];
 return `<div class="cf-panel"><div class="cg-coin-scene"><div id="cg-coin-shadow" class="cg-coin-shadow"></div><div class="cg-coin-lift" id="cg-coin-lift"><i class="cf-coin-edge" aria-hidden="true"></i><div class="cg-coin" id="cg-coin"><div class="cg-coin-side cg-coin-front" ${side===1?'hidden':''}>${coinFace(0,'cf-front')}</div><div class="cg-coin-side cg-coin-reverse" ${side===0?'hidden':''}>${coinFace(1,'cf-back')}</div></div></div></div><div class="cf-result" role="status" aria-live="polite"><div><b>${animating?'Монета в воздухе…':last?picks[side]:'Ваш выбор: '+picks[side]}</b></div></div></div>`;
}
function rpsBoard(info,animating){
 const v=animating?state.ag.cgPrevious:info,last=v?.last,choice=last?.choice??state.ag.options.rps.side??0,opponent=last?.opponent??0;
 const status=animating?'Камень, ножницы, бумага…':last?.tie?'Ничья':last?last.safe?'Ваш ход выиграл':'Соперник выиграл':'Выберите свой жест';
 const note=last?.tie?'Серия сохранена — сделайте следующий ход':!last?'Камень бьёт ножницы · ножницы бьют бумагу · бумага бьёт камень':v?.phase==='play'?'Продолжайте серию или заберите выигрыш':'';
 return `<div class="rps-scene"><div class="rps-duel"><div class="rps-player${last?.safe?' is-winner':''}"><span id="cg-hand-you" class="rps-hand">${DuelArt.hand(choice,'rps-you')}</span><small>ВЫ</small></div><b class="rps-versus">VS</b><div class="rps-player is-house${last&&!last.tie&&!last.safe?' is-winner':''}"><span id="cg-hand-house" class="rps-hand">${DuelArt.hand(opponent,'rps-house','rose')}</span><small>СОПЕРНИК</small></div></div><div class="rps-caption" role="status" aria-live="polite"><b>${status}</b><small>${note}</small></div></div>`;
}
const slotSymbol=n=>`<span class="cs-symbol cs-symbol-${n}" role="img" aria-label="${['Рубин','Колокол','Виноград','Звезда','Семёрка','Крокодил'][n]}"></span>`;
function andarCard(c){
 if(!c)return `<span class="ab-card-back" role="img" aria-label="Рубашка карты"><svg viewBox="0 0 100 144" aria-hidden="true"><rect x="6" y="6" width="88" height="132" rx="3" fill="none" stroke="#d2bee9"/><rect x="10" y="10" width="80" height="124" rx="2" fill="none" stroke="#a78cc4"/><path d="M50 16Q18 29 16 72Q18 115 50 128Q82 115 84 72Q82 29 50 16ZM50 26 76 72 50 118 24 72ZM16 16 84 128M84 16 16 128" fill="none" stroke="#bda4d8" stroke-width=".8"/><g fill="none" stroke="#bda4d8" stroke-width=".8">${Array.from({length:8},(_,i)=>`<ellipse cx="50" cy="72" rx="12" ry="40" transform="rotate(${i*22.5} 50 72)"/>`).join('')}</g><path d="m50 59 9 13-9 13-9-13Z" fill="#d6beed"/></svg></span>`;
 const rank=({14:'A',13:'K',12:'Q',11:'J'})[c.rank]||String(c.rank),suit={s:'♠',c:'♣',h:'♥',d:'♦'}[c.suit];
 return `<span class="ab-card-art${c.suit==='h'||c.suit==='d'?' is-red':''}" role="img" aria-label="${videoCardName(c,0)}"><span class="ab-rank">${rank}</span><span class="ab-suit-sm">${suit}</span><span class="ab-suit">${suit}</span><span class="ab-corner-bottom">${rank}<i>${suit}</i></span></span>`;
}
function andarPile(pile){return pile.length?`<span class="ab-pile-card${pile.length>1?' is-stacked':''}${pile.length>2?' is-deep':''}">${andarCard(pile.at(-1))}</span>`:'';}
function andarBoard(info,animating){
 const d=info?.detail,done=info?.phase==='done'&&!animating;
 return `<div class="ab-panel"><div class="cg-andar"><span class="ab-center-label">Главная карта</span><div class="cg-center-card">${andarCard(d?.center)}</div><div class="ab-deck">${andarCard(null)}</div><div class="cg-andar-sides">${['andar','bahar'].map((side,i)=>{const pile=done?d.dealt.filter((_,n)=>n%2===i):[];return `<div class="${done&&d.winner===side?'is-winner':''}" data-cg-side="${i}"><b>${i?'BAHAR':'ANDAR'}</b><div class="cg-small-card" id="cg-andar-${i}">${andarPile(pile)}</div><small id="cg-andar-count-${i}">${done&&d.winner===side?'✓ Совпадение':pile.length?pile.length+' карт':'Ждём раздачу'}</small></div>`;}).join('')}</div><div class="cg-flying-card" id="cg-flying-card"></div></div><div class="ab-result" role="status" aria-live="polite"><div><small>Результат</small><b>${done?d.winner==='andar'?'Андар':'Бахар':animating?'Раздача…':'На какой стороне совпадёт ранг?'}</b></div><div><small>Выплата</small><b>${done?money(info.payout):'—'}</b></div></div></div>`;
}
function board(){
 const a=state.ag,g=current(),info=a.info,live=info?.phase==='play',locked=agLocked(),d=info?.detail,done=info?.phase==='done'&&!a.animating,step=info?.step||0;
 const visual=a.animating?a.cgPrevious:info,last=visual?.last,visibleStep=visual?.step||0;
 let html='';
 if(a.game==='diamonds')html=diamondBoard(info,a.animating);
 else if(a.game==='videopoker')html=videoBoard(info,a.animating,locked);
 else if(a.game==='sicbo')html=sicboBoard(info,a.animating,locked);
 else if(a.game==='chicken')html=chickenBoard(info,a.animating);
 else if(a.game==='coin')html=coinBoard(info,a.animating,locked);
 else if(a.game==='rps')html=rpsBoard(info,a.animating);
 else if(a.game==='slots'){
  const grid=d?.grid||[0,1,2,5,5,3,4,0,1],old=a.cgPrevious?.detail?.grid||[0,1,2,5,5,3,4,0,1];
  html=`<div class="cg-scene cg-slots-scene"><div class="cg-slot-machine">${[0,1,2].map(col=>{const result=[grid[col],grid[col+3],grid[col+6]],strip=a.animating?[...result,...Array.from({length:15},(_,i)=>(i*5+col)%6),old[col],old[col+3],old[col+6]]:result;return `<div class="cg-reel"><div class="cg-reel-strip" data-cg-reel="${col}" style="--symbols:${strip.length};transform:translateY(${a.animating?-18/21*100:0}%)">${strip.map((n,i)=>`<div class="cg-slot-cell ${done&&d?.lines?.[i]?.payout?'is-line-win':''}">${slotSymbol(n)}</div>`).join('')}</div></div>`;}).join('')}<div class="cg-reel-shade"></div></div><div class="cg-slot-footer"><i></i><span>3 ЛИНИИ</span><i></i></div><div class="cs-result" role="status" aria-live="polite"><div><small>Ставка</small><b>${info?.bet?money(info.bet):'—'}</b></div><div><small>Выигрыш</small><b>${done?money(info.payout):'—'}</b></div></div></div>`;
 }
 else if(a.game==='andar')html=andarBoard(info,a.animating);
 else if(a.game==='darts')html=DartsGame.board();
 else if(a.game==='bowling')html=BowlingScene.board(info,a.animating);
 else if(a.game==='balloon')html=BalloonScene.board(info,a.animating,locked,seriesTable('balloon',a.options.balloon),a.cgPrevious);
 else if(a.game==='race')html=RaceScene.board(info,a.animating,a.options.race.side);
 else if(a.game==='fishing')html=FishingScene.board(info,a.animating);
 $('ag-stage').innerHTML=`<div class="cg-board cg-game-${g.kind} ${a.animating?'is-animating':''}">${html}</div>`;
 if(a.game==='darts'){DartsGame.paint();return;}
 if(a.game==='race'){paint(info||{},a.animating?a.cgTime||0:done?1:0);return;}
 if(a.game==='balloon'){paint(info||{},a.animating?a.cgTime||0:1);const track=$('ag-stage').querySelector('.bl-steps'),active=track?.querySelector('.is-lost,.is-current');if(active)track.scrollLeft=Math.max(0,active.offsetLeft-track.offsetLeft-(track.clientWidth-active.clientWidth)/2);return;}
 if(a.game==='bowling'){paint(info||{},a.animating?a.cgTime||0:done?1:0);return;}
 if(a.game==='sicbo'||a.game==='chicken')paint(info||{},a.animating?a.cgTime||0:1);
 else if(!a.animating&&info&&info.phase!=='bet'&&(info.last||done))paint(info,1);
 else if(a.animating)paint(info,a.cgTime||0);
}
function paint(info,t){
 const a=state.ag,game=a.game,f=CasinoMotion.frame(game,info,a.cgPrevious,t),d=info.detail||{},last=info.last||{},stage=$('ag-stage');
 const el=selector=>stage.querySelector(selector),style=(selector,key,value)=>{const node=el(selector);if(node)node.style[key]=value;};
 const transform=(selector,value)=>style(selector,'transform',value);
 const toggle=(selector,name,value)=>el(selector)?.classList.toggle(name,value);
 if(game==='diamonds')f.items.forEach((v,i)=>{transform(`[data-cg-gem="${i}"]`,`translateY(${v.y}px) rotate(${v.rotation}deg)`);style(`[data-cg-gem="${i}"]`,'opacity',v.opacity);});
 if(game==='videopoker')f.cards.forEach((v,i)=>{
  const selector=`[data-cg-hold="${i}"]`,front=el(selector+' .vp-card-front'),back=el(selector+' .vp-card-back');
  // A 2D flip keeps the resting face out of WebKit's backface/compositing path.
  transform(selector+' .vp-card-motion',v.flip===180&&v.y===0?'none':`translateY(${v.y}px) scaleX(${Math.max(.025,Math.abs(Math.cos(v.flip*Math.PI/180)))})`);
  if(front)front.hidden=v.flip<90;if(back)back.hidden=v.flip>=90;
 });
 if(game==='sicbo'&&typeof SicboScene!=='undefined'){const host=el('#sb-scene');if(host){const rendered=SicboScene.render(host,d.dice||[3,4,5],a.animating?f.dice:null);host.classList.toggle('is-rendered',rendered);}}
 if(game==='chicken')ChickenScene.paint(stage,info,a.cgPrevious,t,a.animating);
 if(game==='coin'){const cos=Math.cos(f.angle*Math.PI/180),front=el('.cg-coin-front'),back=el('.cg-coin-reverse');if(front)front.hidden=cos<0;if(back)back.hidden=cos>=0;transform('#cg-coin',`scaleX(${Math.max(.018,Math.abs(cos))})`);transform('#cg-coin-lift',`translateY(${f.y}px)`);transform('#cg-coin-shadow',`scale(${f.shadow})`);}
 if(game==='rps'){for(const [id,index] of [['you',last.choice],['house',last.opponent]]){const node=el('#cg-hand-'+id);if(node){const hand=f.reveal?index??0:0;if(node.dataset.hand!==String(hand)){node.innerHTML=DuelArt.hand(hand,'rps-'+id,id==='house'?'rose':'violet');node.dataset.hand=String(hand);}node.style.transform=`translateY(${f.y}px) rotate(${f.reveal?0:(id==='house'?-1:1)*Math.sin(t*28)*5}deg) scale(${f.scale})`;}}}
 if(game==='slots'&&a.animating)f.reels.forEach((r,i)=>{transform(`[data-cg-reel="${i}"]`,`translateY(${(r.position-18)/21*100}%)`);toggle(`[data-cg-reel="${i}"]`,'is-spinning',!r.settled);});
 if(game==='andar'){
  const count=t===1?d.dealt?.length||0:f.count;
  for(let side=0;side<2;side++){const pile=(d.dealt||[]).slice(0,count).filter((_,i)=>i%2===side),node=el('#cg-andar-'+side),label=el('#cg-andar-count-'+side);if(node&&node.dataset.count!==String(pile.length)){node.innerHTML=andarPile(pile);node.dataset.count=String(pile.length);}if(label)label.textContent=t===1&&d.winner===['andar','bahar'][side]?'✓ Совпадение · '+pile.length:pile.length+' карт';}
  const moving=el('#cg-flying-card');if(moving){const c=d.dealt?.[f.index];if(moving.dataset.index!==String(f.index)){moving.innerHTML=andarCard(c);moving.dataset.index=String(f.index);}moving.style.opacity=t<.15||f.complete?0:1;const u=f.flight*f.flight*(3-2*f.flight);moving.style.left=(86+((f.index%2?75:25)-86)*u)+'%';moving.style.top=(25+50*u-5*Math.sin(u*Math.PI))+'%';moving.style.transform=`translate(-50%,-50%) rotate(0deg)`;}
 }

 if(game==='darts')DartsScene.paint(stage,f,info);
 if(game==='bowling')BowlingScene.render(el('.bw-viewport'),info,t);
 if(game==='balloon')BalloonScene.paint(stage,info,a.cgPrevious,t);
 if(game==='race')RaceScene.paint(stage,info,t);
 if(game==='fishing')FishingScene.paint(stage,info,t);
}
function animate(info){
 const a=state.ag,game=a.game,token=++a.token,reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 cancelAnimationFrame(a.raf);
 const duration=reduced?0:CasinoMotion.duration(game,info),start=performance.now();a.cgTime=0;
 if(game==='darts')DartsAudio.begin(info.revision,reduced);
 const tick=now=>{
  if(token!==a.token||a.game!==game)return;
  const t=duration?Math.min(1,(now-start)/duration):1;a.cgTime=t;paint(info,t);
  if(game==='darts')DartsAudio.frame(t);
  if(t<1)a.raf=requestAnimationFrame(tick);else{a.animating=false;a.cgTime=0;renderArcade();agResult();}
 };
 a.raf=requestAnimationFrame(tick);
}
function changed(){state.ag.held=[];state.ag.cgTime=0;}
function settingEvent(event){
 if(event.target.closest('[data-cg-pick]'))return boardEvent(event);
 const a=state.ag;if(!isGame(a.game)||agLocked()||a.info?.phase==='play')return;
 const el=event.target.closest('[data-cg-option]');if(el){const g=current(),pair=g.choices.find(([,v])=>String(v)===el.dataset.cgOption);if(!pair)return;a.options[a.game][el.dataset.cgKey]=pair[1];renderArcade();}
}
function boardEvent(event){
 const a=state.ag;
 if(a.game==='darts'){
  const sound=event.target.closest('[data-dt-sound]');
  if(sound){const enabled=DartsAudio.toggle();sound.setAttribute('aria-pressed',String(enabled));sound.setAttribute('aria-label',`${enabled?'Выключить':'Включить'} звук`);}
  return;
 }
 if(a.game==='sicbo'){
  const choice=event.target.closest('[data-sb-side]');
  if(choice&&!choice.disabled&&!agLocked()&&!(a.info.phase==='done'&&!a.info.settled)&&['small','big','triple'].includes(choice.dataset.sbSide)){a.options.sicbo.side=choice.dataset.sbSide;renderArcade();}
  return;
 }
 if(!isGame(a.game)||agLocked()||a.info?.phase!=='play')return;
 const hold=event.target.closest('[data-cg-hold]');if(hold){
  const n=Number(hold.dataset.cgHold);if(a.game!=='videopoker'||hold.disabled||!Number.isInteger(n)||n<0||n>=5)return;
  a.held??=[];const i=a.held.indexOf(n),kept=i<0;if(kept)a.held.push(n);else a.held.splice(i,1);
  // Preserve every face node and its paint state when selecting a card.
  hold.classList.toggle('is-held',kept);hold.setAttribute('aria-pressed',String(kept));
  hold.setAttribute('aria-label',videoCardName(a.info.cards[n],n)+(kept?', оставить':', заменить'));
  hold.querySelector('.vp-held-check').hidden=!kept;
  hold.querySelector('.vp-hold-label').textContent=kept?'ОСТАВИТЬ':'ЗАМЕНИТЬ';
  renderArcade(false);return;
 }
 const pick=event.target.closest('[data-cg-pick]');if(pick&&!pick.disabled)agRequest('pick',{index:Number(pick.dataset.cgPick)});

}
function bind(){
 $('ag-stage').addEventListener('raceready',()=>{if(state.ag.game==='race')afterRender();});
 $('ag-balloon-pump').addEventListener('click',()=>{
  const a=state.ag;if(a.game!=='balloon'||!a.info||agLocked()||(a.info.phase==='done'&&!a.info.settled))return;
  agRequest(a.info.phase==='play'?'pick':'start',a.info.phase==='play'?{index:0}:{});
 });
 $('ag-stage').addEventListener('bowlingready',()=>{if(state.ag.game==='bowling')afterRender();});
 $('ag-chicken-step').addEventListener('click',()=>{if(state.ag.game==='chicken'&&state.ag.info?.phase==='play'&&!agLocked())agRequest('pick',{index:0});});
 $('ag-settings').addEventListener('click',settingEvent);
 $('ag-stage').addEventListener('click',boardEvent);

}
return {isGame,prepare,setup,settings,paytable,afterRender,main,board,animate,changed,bind,seriesTable,paint,diamondResult};
})();
