'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm');
const {games,ids}=require('../public/casino-rules'),game=require('../server/arcade/game');
function harness(id){
 const elements=new Map(),frames=new Map(),sent=[];let next=0;
 const element=()=>{const classes=new Set();return {innerHTML:'',textContent:'',value:'1,00',disabled:false,hidden:false,dataset:{},style:{},attributes:{},listeners:{},classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),toggle(c,on){if(on??!classes.has(c))classes.add(c);else classes.delete(c);}},setAttribute(k,v){this.attributes[k]=v;},querySelector(){return element();},querySelectorAll(){return [];},addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);},dispatch(type,target){for(const fn of this.listeners[type]||[])fn({target});}};};
 const $=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
 // Retain card/face identities between clicks; replacing stage.innerHTML destroys them.
 const stage=$('ag-stage');let stageHtml='',cardNodes=[];stage.writes=0;
 Object.defineProperty(stage,'innerHTML',{get:()=>stageHtml,set(html){
  stageHtml=html;stage.writes++;cardNodes=[...html.matchAll(/<button\b([^>]*data-cg-hold="(\d+)"[^>]*)>([\s\S]*?)<\/button>/g)].map(([,attrs,index,body])=>{
   const node=element();node.dataset.cgHold=index;node.disabled=/\bdisabled\b/.test(attrs);
   for(const [,key,value] of attrs.matchAll(/(aria-[\w-]+)="([^"]*)"/g))node.setAttribute(key,value);
   if(/\bis-held\b/.test(attrs))node.classList.add('is-held');
   const parts=new Map();for(const cls of ['vp-card-motion','vp-card-front','vp-card-back','vp-card-art','vp-held-check','vp-hold-label']){
    const part=element(),tag=body.match(new RegExp(`<[^>]*class="${cls}(?: [^"]*)?"[^>]*>`));
    part.hidden=Boolean(tag&&/\bhidden\b/.test(tag[0]));parts.set('.'+cls,part);
   }
   parts.get('.vp-card-art').innerHTML=body.match(/<span class="vp-card-art[\s\S]*?<\/span><\/span>/)?.[0]||'';
   parts.get('.vp-hold-label').textContent=body.match(/<small class="vp-hold-label">([^<]*)/)?.[1]||'';
   node.querySelector=s=>parts.get(s)||null;node.closest=s=>s==='[data-cg-hold]'?node:null;return node;
  });
 }});
 stage.querySelector=s=>{const match=s.match(/^\[data-cg-hold="(\d+)"\](?: (.*))?$/);if(!match)return element();const node=cardNodes[Number(match[1])];return match[2]?node?.querySelector(match[2]):node;};
 stage.querySelectorAll=s=>s==='button'?cardNodes:[];
 const state={connected:true,balance:100000,ag:{game:id,info:null,pending:null,animating:false,token:0,raf:null,options:{}}};
 const ctx=vm.createContext({state,$,document:{querySelectorAll:()=>[]},window:{matchMedia:()=>({matches:false})},performance:{now:()=>0},structuredClone,
 send:m=>sent.push(m),money:n=>'$'+((n||0)/100).toFixed(2),toCents:v=>Math.round(Number(v.replace(',','.'))*100),haptic(){},toast(){},
 requestAnimationFrame:f=>{const id=++next;frames.set(id,f);return id;},cancelAnimationFrame:id=>frames.delete(id)});
 for(const file of ['casino-rules','casino-art','casino-motion','sicbo-scene','chicken-scene','darts-rules','darts-scene','darts-audio','darts-game','bowling-scene','casino-ui','arcade'])vm.runInContext(fs.readFileSync(`public/${file}.js`,'utf8'),ctx);
 // DOM harness has no graphics context; GPU rendering is checked separately.
 vm.runInContext('BowlingScene.render=()=>true;BowlingScene.ready=()=>true;',ctx);
 vm.runInContext(`CasinoUI.prepare('${id}');`,ctx);ctx.bindArcade();
 const deliver=round=>ctx.onArcadeState({game:id,accepted:true,config:game.config(id),balance:100000,...game.publicState(id,round),requestId:state.ag.pending?.id});
 const advance=(now=10000)=>{const list=[...frames.values()];frames.clear();for(const f of list)f(now);};
 const click=(container,key,value)=>{const target=key==='cgHold'&&cardNodes[Number(value)]||{dataset:{[key]:value},disabled:false,closest:selector=>selector===`[data-${key.replace(/[A-Z]/g,c=>'-'+c.toLowerCase())}]`?target:null};$(container).dispatch('click',target);};
 return {ctx,state,$,sent,deliver,advance,frames,click};
}
for(const id of ids)test(`${id}: every board renders, actions send once, animations finish, reconnect state stays playable`,()=>{
 const h=harness(id);h.deliver(game.initial());
 assert.match(h.$('ag-stage').innerHTML,/class="cg-board cg-game-/,'board wrapper must not inherit scene grid/flex sizing');
 assert.ok(!h.$('ag-stage').innerHTML.includes('undefined'));assert.equal(h.$('ag-main').disabled,false);
 h.$('ag-main').dispatch('click',{});h.$('ag-main').dispatch('click',{});assert.equal(h.sent.length,1);assert.equal(h.sent[0].type,'ag_start');
 let r=game.start(id,game.initial(),100,structuredClone(games[id].defaults),0,n=>n-1);r.settled=r.phase==='done';h.deliver(r);h.advance();
 if(r.phase==='play'){
  if(id==='videopoker'){h.click('ag-stage','cgHold','0');h.click('ag-stage','cgHold','4');h.$('ag-main').dispatch('click',{});assert.equal(JSON.stringify(h.sent.at(-1).index),'[0,4]');r=game.actGame(id,r,'ag_pick',[0,4],r.revision);}
  else if(id==='scratch'){for(let i=0;i<9;i++){h.click('ag-stage','cgScratch',String(i));assert.equal(h.sent.at(-1).index,i);r=game.actGame(id,r,'ag_pick',i,r.revision);r.settled=r.phase==='done';h.deliver(r);} }
  else {h.$('ag-main').dispatch('click',{});assert.equal(h.sent.at(-1).type,'ag_cashout');r=game.actGame(id,r,'ag_cashout',null,r.revision);}
  r.settled=true;h.deliver(r);h.advance();
 }
 assert.equal(h.state.ag.animating,false);assert.equal(h.frames.size,0);assert.equal(h.$('ag-main').disabled,false);
 assert.equal(h.$('ag-payout').textContent,'$'+(r.payout/100).toFixed(2));assert.ok(!h.$('ag-stage').innerHTML.includes('undefined'));
 h.state.connected=false;h.ctx.renderArcade();assert.equal(h.$('ag-main').disabled,true);
});
test('series board buttons are usable while cashout and stake controls keep their own states',()=>{
 for(const id of ids.filter(id=>games[id].series)){
  const h=harness(id);h.deliver(game.initial());h.ctx.agRequest('start');const r=game.start(id,game.initial(),100,structuredClone(games[id].defaults),0,n=>n-1);h.deliver(r);
  assert.equal(h.$('ag-main').disabled,false);assert.equal(h.$('ag-amount').disabled,true);
  const before=h.sent.length;h.click('ag-stage','cgPick','0');assert.equal(h.sent.length,before+1,id);assert.equal(h.sent.at(-1).type,'ag_pick');
 }
});
test('game choices preserve native inputs and map numeric values to numbers',()=>{
 for(const id of ids.filter(id=>games[id].choices)){
  const h=harness(id);h.deliver(game.initial());const [label,value]=games[id].choices.at(-1),key=id==='chicken'||id==='balloon'?'level':'side';
  const target={dataset:{cgOption:String(value),cgKey:key},closest:selector=>selector==='[data-cg-option]'?target:null};h.$('ag-settings').dispatch('click',target);
  h.ctx.agRequest('start');assert.equal(h.sent.at(-1).options[key],value);
 }
});
test('catalog launchers contain all 14 distinct games and no baccarat duplicate',()=>{
 const h=harness('diamonds'),html=h.$('casino-catalog').innerHTML;
 const idsInHtml=[...html.matchAll(/data-arcade="([^"]+)"/g)].map(m=>m[1]);assert.deepEqual(idsInHtml,ids);assert.equal(new Set(idsInHtml).size,14);assert.ok(!html.includes('data-arcade="baccarat"'));
});
test('Chicken step and cashout controls lock duplicate requests and restore a saved round',()=>{
 const h=harness('chicken');h.deliver(game.initial());
 assert.equal(h.$('ag-chicken-step').hidden,true);
 h.$('ag-main').dispatch('click',{});
 let r=game.start('chicken',game.initial(),100,{level:'easy'},0,n=>n-1);r.order=[...Array(20).fill(1),0];h.deliver(r);
 assert.equal(h.$('ag-chicken-step').hidden,false);assert.equal(h.$('ag-chicken-step').disabled,false);
 assert.equal(h.$('ag-amount').disabled,true);
 assert.match(h.$('ag-stage').innerHTML,/ch-road-svg/);assert.ok(!h.$('ag-stage').innerHTML.includes('cg-road-ground'));
 assert.equal(h.$('ag-chicken-step').textContent,'Следующий шаг →');
 h.$('ag-chicken-step').dispatch('click',{});h.$('ag-chicken-step').dispatch('click',{});h.$('ag-main').dispatch('click',{});
 assert.equal(h.sent.filter(m=>m.type==='ag_pick').length,1);assert.equal(h.sent.filter(m=>m.type==='ag_cashout').length,0);
 r=game.actGame('chicken',r,'ag_pick',0,r.revision);h.deliver(r);
 assert.equal(h.$('ag-chicken-step').disabled,true);assert.equal(h.$('ag-main').disabled,true);
 assert.ok(!h.$('ag-stage').innerHTML.includes('1.02×</b>'),'future payout stays hidden until the step finishes');
 h.advance();assert.match(h.$('ag-stage').innerHTML,/1.02×<\/b>/);assert.equal(h.$('ag-main').textContent,'Забрать $1.02');
 const resume=harness('chicken');resume.deliver(r);assert.equal(resume.state.ag.animating,false);assert.equal(resume.$('ag-main').textContent,'Забрать $1.02');
 h.$('ag-main').dispatch('click',{});h.$('ag-main').dispatch('click',{});
 assert.equal(h.sent.filter(m=>m.type==='ag_cashout').length,1);
 r=game.actGame('chicken',r,'ag_cashout',null,r.revision);r.settled=true;h.deliver(r);
 assert.equal(h.$('ag-chicken-step').hidden,true);assert.equal(h.$('ag-amount').disabled,false);
 assert.match(h.$('ag-stage').innerHTML,/Выплата/);assert.equal(h.$('ag-main').textContent,'Сделать ставку');
});
test('Chicken loss appears only after collision and reduced motion completes without a hanging lock',()=>{
 for(const reduced of [false,true]){
  const h=harness('chicken');h.ctx.window.matchMedia=()=>({matches:reduced});h.deliver(game.initial());h.ctx.agRequest('start');
  let r=game.start('chicken',game.initial(),100,{level:'hard'},0,n=>n-1);r.order[0]=0;h.deliver(r);
  h.$('ag-chicken-step').dispatch('click',{});r=game.actGame('chicken',r,'ag_pick',0,r.revision);r.settled=true;h.deliver(r);
  assert.ok(!h.$('ag-stage').innerHTML.includes('Столкновение'));
  h.advance();assert.match(h.$('ag-stage').innerHTML,/Столкновение/);assert.match(h.$('ag-stage').innerHTML,/\$0.00/);
  assert.equal(h.state.ag.animating,false);assert.equal(h.frames.size,0);assert.equal(h.$('ag-main').disabled,false);
 }
});

test('active animations lock clicks and stop permanently when leaving any game',()=>{
 for(const id of ids){
  const h=harness(id);h.deliver(game.initial());h.ctx.agRequest('start');
  let r=game.start(id,game.initial(),100,structuredClone(games[id].defaults),0,n=>n-1);r.settled=r.phase==='done';h.deliver(r);
  if(games[id].series){h.ctx.agRequest('pick',{index:0});r=game.actGame(id,r,'ag_pick',0,r.revision,n=>n-1);r.settled=r.phase==='done';h.deliver(r);}
  h.advance(100);assert.equal(h.state.ag.animating,true,id);assert.equal(h.$('ag-main').disabled,id!=='darts',id);assert.equal(h.frames.size,1,id);
  const count=h.sent.length;h.$('ag-main').dispatch('click',{});h.click('ag-stage','cgPick','0');assert.equal(h.sent.length,count+(id==='darts'?1:0),id);
  h.ctx.stopArcade();h.advance(10000);assert.equal(h.state.ag.animating,false,id);assert.equal(h.frames.size,0,id);
 }
});
test('scene markup uses project textures and generated assets rather than placeholder drawings',()=>{
 const h=harness('diamonds');h.deliver(game.initial());
 assert.match(h.$('casino-catalog').innerHTML,/cg-sprite/);
 for(const id of ['cases','collection','scratch','limbo'])assert.ok(!h.$('casino-catalog').innerHTML.includes(`data-arcade="${id}"`));
 assert.match(fs.readFileSync('public/casino-ui.css','utf8'),/img\/catalog\/objects.webp/);
 for(const asset of ['objects','environments'])assert.ok(fs.statSync(`public/img/catalog/${asset}.webp`).size>10000);
});

test('Diamonds matches the approved table and highlights only the actual combination after revealing',()=>{
 const fixtures=[[[0,0,0,0,0],'Пять одинаковых',5],[[0,0,0,0,1],'Четыре одинаковых',4],[[0,0,0,1,1],'Фулл-хаус',5],[[0,0,0,1,2],'Три одинаковых',3],[[0,0,1,1,2],'Две пары',4],[[0,0,1,2,3],'Пара',2],[[0,1,2,3,4],'Нет совпадений',0]];
 for(const [gems,label,matches] of fixtures){
  const h=harness('diamonds');h.deliver(game.initial());h.ctx.agRequest('start');let i=0;
  const r=game.start('diamonds',game.initial(),100,{},0,()=>gems[i++]);r.settled=true;h.deliver(r);
  assert.ok(!h.$('ag-stage').innerHTML.includes('is-selected'),'no outcome highlight before reveal');
  h.advance();const html=h.$('ag-stage').innerHTML;
  assert.equal((html.match(/class="dm-tile is-match"/g)||[]).length,matches,label);
  assert.equal((html.match(/class="dm-pay-row is-selected"/g)||[]).length,1,label);
  assert.equal((html.match(/role="row"/g)||[]).length,7);
  assert.ok(html.includes(label));assert.ok(!html.includes('cg-jewel-tray'));assert.ok(!html.includes('cg-sprite'));
  assert.equal(h.$('ag-overlay').innerHTML,'','inline result should not be covered by an overlay');
 }
});

test('videopoker keeps zero to five selected cards, shows the exact exchange count and locks the stake',()=>{
 const h=harness('videopoker');h.deliver(game.initial());h.ctx.agRequest('start');
 const r=game.start('videopoker',game.initial(),100,{},0,n=>n-1);h.deliver(r);h.advance();
 assert.equal(h.$('ag-amount').disabled,true);
 const labels=['Заменить 5 карт','Заменить 4 карты','Заменить 3 карты','Заменить 2 карты','Заменить 1 карту','Оставить все карты'];
 for(let held=0;held<=5;held++){
  assert.equal(h.$('ag-main').textContent,labels[held]);
  const cards=h.$('ag-stage').querySelectorAll('button');
  assert.equal(cards.filter(c=>c.attributes['aria-pressed']==='true').length,held);
  assert.equal(cards.filter(c=>!c.querySelector('.vp-held-check').hidden).length,held);
  if(held<5)h.click('ag-stage','cgHold',String(held));
 }
 h.click('ag-stage','cgHold','2');assert.equal(h.$('ag-main').textContent,'Заменить 1 карту');
 h.$('ag-main').dispatch('click',{});h.$('ag-main').dispatch('click',{});
 assert.equal(h.sent.filter(m=>m.type==='ag_pick').length,1);
 assert.equal(JSON.stringify(h.sent.at(-1).index),'[0,1,3,4]');
 assert.equal(h.$('ag-main').disabled,true);
});

test('videopoker shows all nine payouts, previews the hand and reveals the final payment after animation',()=>{
 const h=harness('videopoker');h.deliver(game.initial());
 assert.ok(!h.$('ag-stage').innerHTML.includes('aria-current="true"'));
 const r=game.start('videopoker',game.initial(),100,{},0,n=>n-1);
 r.cards=[{rank:12,suit:'h'},{rank:11,suit:'s'},{rank:11,suit:'d'},{rank:7,suit:'c'},{rank:2,suit:'s'}];
 h.deliver(r);h.advance();
 let html=h.$('ag-stage').innerHTML;
 assert.match(html,/Пара валетов/);assert.match(html,/Текущая комбинация/);
 assert.equal((html.match(/role="listitem"/g)||[]).length,9);
 assert.equal((html.match(/aria-current="true"/g)||[]).length,1);
 assert.match(html,/vp-pay-tile is-selected[^>]*><span>Валеты и старше<\/span><b>1×/);
 for(let i=0;i<5;i++)h.click('ag-stage','cgHold',String(i));
 h.$('ag-main').dispatch('click',{});
 const done=game.actGame('videopoker',r,'ag_pick',[0,1,2,3,4],r.revision);done.settled=true;h.deliver(done);
 assert.ok(!h.$('ag-stage').innerHTML.includes('aria-current="true"'),'no final result before animation completes');
 h.advance();html=h.$('ag-stage').innerHTML;
 assert.match(html,/Выплата \$1.00/);assert.match(html,/Пара валетов/);
 assert.equal(h.$('ag-overlay').innerHTML,'');
 assert.equal(h.$('ag-amount').disabled,false);
 assert.equal(h.$('ag-main').textContent,'Сделать ставку');
});

test('all 52 videopoker cards show readable Baccarat-style ranks and suits without external face assets',()=>{
 const h=harness('videopoker'),faces=new Set();
 for(const suit of ['s','c','h','d'])for(let rank=2;rank<=14;rank++){
  const r=game.start('videopoker',game.initial(),100,{},0,n=>n-1);
  r.cards[0]={rank,suit};h.state.ag.info=null;h.deliver(r);h.advance();
  const html=h.$('ag-stage').innerHTML,face=html.match(/class="vp-card-art([^"]*)"[^>]*><span class="vp-rank">([^<]+)<\/span><span class="vp-suit-sm">([^<]+)<\/span><span class="vp-suit">([^<]+)<\/span>/);
  assert.ok(face,`${rank} ${suit} is inline and readable`);
  assert.equal(face[2],({14:'A',13:'K',12:'Q',11:'J'})[rank]||String(rank));
  assert.equal(face[3],{s:'♠',c:'♣',h:'♥',d:'♦'}[suit]);assert.equal(face[4],face[3]);
  assert.equal(face[1].includes('is-red'),suit==='h'||suit==='d');
  assert.ok(!html.includes('<use ')&&!html.includes('<img '));faces.add(face[0]);
 }
 assert.equal(faces.size,52);
});

test('repeated hold/unhold preserves all five visible face nodes and only updates selection',()=>{
 const h=harness('videopoker');h.deliver(game.start('videopoker',game.initial(),100,{},0,n=>n-1));h.advance();
 const stage=h.$('ag-stage'),cards=stage.querySelectorAll('button'),faces=cards.map(c=>c.querySelector('.vp-card-art')),writes=stage.writes;
 const content=faces.map(c=>c.innerHTML);
 for(let cycle=0;cycle<4;cycle++)for(let i=0;i<5;i++){
  h.click('ag-stage','cgHold',String(i));const kept=cycle%2===0;
  assert.equal(stage.writes,writes,'selection must not rebuild the board');
  assert.equal(stage.querySelector(`[data-cg-hold="${i}"]`),cards[i]);
  assert.equal(cards[i].classList.contains('is-held'),kept);
  assert.equal(cards[i].attributes['aria-pressed'],String(kept));
  assert.ok(cards[i].attributes['aria-label'].endsWith(kept?', оставить':', заменить'));
  assert.equal(cards[i].querySelector('.vp-held-check').hidden,!kept);
  assert.equal(cards[i].querySelector('.vp-hold-label').textContent,kept?'ОСТАВИТЬ':'ЗАМЕНИТЬ');
  cards.forEach((c,n)=>{assert.equal(c.querySelector('.vp-card-art'),faces[n]);assert.equal(faces[n].innerHTML,content[n]);assert.equal(c.querySelector('.vp-card-front').hidden,false);assert.equal(c.querySelector('.vp-card-back').hidden,true);});
 }
 assert.equal(h.sent.length,0,'selecting cards never sends a draw or a bet');
});

test('videopoker reveals 2D faces and never flips held cards during an exchange',()=>{
 const h=harness('videopoker');h.deliver(game.initial());h.ctx.agRequest('start');
 const r=game.start('videopoker',game.initial(),100,{},0,n=>n-1);h.deliver(r);
 let cards=h.$('ag-stage').querySelectorAll('button');
 assert.ok(cards.every(c=>c.querySelector('.vp-card-front').hidden));
 h.click('ag-stage','cgHold','0');assert.equal(h.state.ag.held.length,0,'no selection during deal');
 h.advance();cards=h.$('ag-stage').querySelectorAll('button');
 assert.ok(cards.every(c=>!c.querySelector('.vp-card-front').hidden));
 h.click('ag-stage','cgHold','0');h.$('ag-main').dispatch('click',{});
 const done=game.actGame('videopoker',r,'ag_pick',[0],r.revision);done.settled=true;h.deliver(done);
 cards=h.$('ag-stage').querySelectorAll('button');
 assert.equal(cards[0].querySelector('.vp-card-front').hidden,false);
 assert.equal(cards[0].querySelector('.vp-card-motion').style.transform,'none');
 assert.ok(cards.slice(1).every(c=>c.querySelector('.vp-card-front').hidden));
 h.advance();cards=h.$('ag-stage').querySelectorAll('button');
 assert.ok(cards.every(c=>!c.querySelector('.vp-card-front').hidden&&c.querySelector('.vp-card-back').hidden));
 assert.ok(cards.every(c=>c.querySelector('.vp-card-motion').style.transform==='none'));
});

test('Sic Bo choices lock during a throw; real totals appear only after all dice settle',()=>{
 const h=harness('sicbo');h.deliver(game.initial());
 h.click('ag-stage','sbSide','big');assert.equal(h.state.ag.options.sicbo.side,'big');
 h.$('ag-main').dispatch('click',{});assert.equal(h.sent.at(-1).options.side,'big');
 h.click('ag-stage','sbSide','small');assert.equal(h.state.ag.options.sicbo.side,'big');
 let index=0;const r=game.start('sicbo',game.initial(),100,{side:'big'},0,()=>[2,3,4][index++]);r.settled=true;h.deliver(r);
 assert.match(h.$('ag-stage').innerHTML,/Бросаем…/);
 assert.ok(!h.$('ag-stage').innerHTML.includes('$2.00'));
 assert.equal(h.$('ag-amount').disabled,true);
 h.advance(1700);assert.equal(h.state.ag.animating,true);
 h.advance();let html=h.$('ag-stage').innerHTML;
 assert.match(html,/Сумма<\/small><b>12<\/b>/);assert.match(html,/Выплата<\/small><b>\$2.00/);
 assert.match(html,/aria-label="Сумма 12"/);assert.equal(h.$('ag-overlay').innerHTML,'');
 assert.equal(h.$('ag-main').textContent,'Бросить кубики');
 assert.match(html,/id="sb-scene"/);assert.match(html,/aria-label="Кубики 3, 4, 5"/);assert.ok(!html.includes('sb-face'));
 h.click('ag-stage','sbSide','triple');assert.equal(h.state.ag.options.sicbo.side,'triple');
});
test('Andar renders all 52 Baccarat-style faces inline and keeps only the top face on each stack',()=>{
 const h=harness('andar');h.deliver(game.initial());
 for(const suit of ['s','c','h','d'])for(let rank=2;rank<=14;rank++){
  const c={rank,suit};h.state.ag.info={...h.state.ag.info,phase:'done',settled:true,bet:100,payout:200,detail:{center:c,dealt:[c,c,c,c,c,c],winner:'bahar'}};
  h.ctx.renderArcade();const html=h.$('ag-stage').innerHTML;
  assert.ok(!html.includes('/img/classic/deck.svg'));
  assert.equal((html.match(/class="ab-rank"/g)||[]).length,3);
  assert.equal((html.match(/class="ab-pile-card is-stacked is-deep"/g)||[]).length,2);
  assert.ok(html.includes(`<span class="ab-rank">${({14:'A',13:'K',12:'Q',11:'J'})[rank]||rank}</span>`));
  assert.ok(html.includes(`<span class="ab-suit">${{s:'♠',c:'♣',h:'♥',d:'♦'}[suit]}</span>`));
  assert.ok(!html.includes('--offset:'));
 }
});

function dartsBridge(balance=500){
 const h=harness('darts');h.deliver(game.initial());h.state.balance=balance;
 const account={id:'qa',name:'QA',balance},messages=[],saved=[];
 const accounts={get:()=>account,flush(){saved.push(structuredClone(account));}};
 const service=require('../server/arcade/service').createArcadeService({accounts,noteWin(){},rng:n=>n-1});
 const client={user:{id:'qa'},send:m=>{messages.push(m);h.ctx.onArcadeState(m);}};
 return {h,account,messages,saved,accounts,run:i=>service.handle(client,h.sent[i]),service,client};
}
test('four rapid darts reserve four stakes, overlap and add payouts only at each impact',()=>{
 const {h,account,messages,saved,run}=dartsBridge();
 for(let i=0;i<4;i++)h.$('ag-main').dispatch('click',{});
 assert.equal(h.sent.length,1,'only one unconfirmed revision is sent');
 for(let i=0;i<4;i++){
  h.ctx.performance.now=()=>i*100;run(i);
  assert.equal(h.$('ag-main').disabled,false,'next throw remains available');
 }
 assert.equal(h.sent.length,4);assert.equal(new Set(h.sent.map(m=>m.requestId)).size,4);
 assert.deepEqual(h.sent.map(m=>m.revision),[0,2,4,6]);
 assert.equal(account.balance,260);assert.equal(saved.length,4);
 assert.equal((h.$('ag-stage').innerHTML.match(/data-dt-flight="/g)||[]).length,4);
 assert.equal(h.$('ag-payout').textContent,'$0.00');
 h.advance(950);assert.equal(h.$('ag-payout').textContent,'$0.40');
 h.advance(1300);assert.equal(h.$('ag-payout').textContent,'$1.60');
 h.advance(1800);assert.equal(h.state.ag.animating,false);assert.equal(h.frames.size,0);assert.equal(h.$('ag-multiplier').textContent,'0.40×');
 assert.equal(h.$('ag-amount').disabled,false);
 h.ctx.onArcadeState(messages[0]);assert.equal(h.state.balance,260,'late old response cannot rewind the wallet');
 assert.throws(()=>run(0),/Раунд обновился/);assert.equal(account.balance,260,'duplicate wire request cannot debit twice');
 assert.equal(messages.at(-1).accepted,false);assert.equal(h.sent.length,4);
});
test('queued darts cannot reserve more than the wallet and rejected persistence cancels the queue',()=>{
 const {h,run,account}=dartsBridge(250);
 for(let i=0;i<4;i++)h.$('ag-main').dispatch('click',{});
 run(0);run(1);assert.equal(h.sent.length,2);assert.equal(account.balance,130);
 const failing=dartsBridge();for(let i=0;i<4;i++)failing.h.$('ag-main').dispatch('click',{});
 failing.accounts.flush=()=>{throw Error('disk failure');};
 assert.throws(()=>failing.run(0),/Не удалось сохранить/);assert.equal(failing.account.balance,500);
 assert.equal(failing.messages.at(-1).accepted,false);assert.equal(failing.h.sent.length,1);assert.equal(failing.h.state.ag.animating,false);
});
test('closing or reconnecting cancels unsent darts and never replays an uncertain request',()=>{
 for(const close of [false,true]){
  const {h,run,account}=dartsBridge();for(let i=0;i<4;i++)h.$('ag-main').dispatch('click',{});
  if(close)h.ctx.stopArcade();else{h.state.connected=false;vm.runInContext('DartsGame.stop()',h.ctx);}
  run(0);assert.equal(account.balance,440);assert.equal(h.sent.length,1);
  if(!close){h.state.connected=true;h.ctx.agOpenRequest();run(1);assert.equal(account.balance,440);assert.equal(h.sent.length,2);assert.equal(h.sent[1].type,'ag_open');assert.equal(h.state.ag.animating,false);assert.equal(h.$('ag-payout').textContent,'$0.40');}
 }
});

test('Bowling blocks new stakes until 3D is ready but keeps saved payouts accessible',()=>{
 const h=harness('bowling');h.deliver(game.initial());
 vm.runInContext('BowlingScene.ready=()=>false;CasinoUI.afterRender();',h.ctx);
 assert.equal(h.$('ag-main').disabled,true);
 vm.runInContext('CasinoUI.main();',h.ctx);assert.equal(h.sent.length,0);
 vm.runInContext('BowlingScene.ready=()=>true;CasinoUI.afterRender();',h.ctx);
 assert.equal(h.$('ag-main').disabled,false);assert.equal(h.$('ag-main').textContent,'Бросить шар');
 const r=game.start('bowling',game.initial(),100,{},0,n=>n-1);r.settled=false;
 vm.runInContext('BowlingScene.ready=()=>false;',h.ctx);h.deliver(r);h.advance();
 assert.equal(h.$('ag-main').disabled,false);
});
