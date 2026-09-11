'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const C=require('../public/croco-lobby');
const money=n=>'$'+(n/100).toFixed(2);
function storage(){const map=new Map();return {getItem:k=>map.get(k),setItem:(k,v)=>map.set(k,v)};}
test('recent games are isolated by account, validated, unique, bounded and resilient to blocked storage',()=>{
 const s=storage(),names={holdem:'Poker',mines:'Mines',nvuti:'Nvuti'};
 assert.deepEqual(C.recent(s,'new',names),[]);
 C.remember(s,'one','holdem',names);C.remember(s,'one','nvuti',names);C.remember(s,'one','holdem',names);C.remember(s,'one','removed',names);
 assert.deepEqual(C.recent(s,'one',names),['holdem','nvuti']);assert.deepEqual(C.recent(s,'two',names),[]);
 s.setItem('croco:recent:one','{"bad":1}');assert.deepEqual(C.recent(s,'one',names),[]);
 assert.doesNotThrow(()=>C.remember({getItem(){throw Error();},setItem(){throw Error();}},'one','nvuti',names));
});
test('first visit shows no fabricated transactions; preview shows only the latest three real records',()=>{
 assert.match(C.historyHtml([],money),/Пока нет транзакций/);assert.doesNotMatch(C.historyHtml([],money),/\$/);
 const records=Array.from({length:5},(_,i)=>({kind:'topup',status:'paid',cents:100+i,createdAt:0}));
 const html=C.historyHtml(records,money);assert.equal((html.match(/class="croco-tx"/g)||[]).length,3);assert.match(html,/\+\$1.00/);
});
test('pending and failed operations are not presented as completed money movements, credited amount zero is respected',()=>{
 const r={kind:'topup',status:'pending',cents:500,createdAt:0};
 assert.doesNotMatch(C.transaction(r,money),/is-in|\+\$/);assert.match(C.transaction(r,money),/Ожидает оплаты/);
 assert.match(C.transaction({...r,status:'paid',creditedCents:0},money),/\+\$0.00/);
 assert.doesNotMatch(C.transaction({...r,kind:'payout',status:'failed'},money),/is-out|−\$/);
 assert.match(C.transaction({...r,kind:'payout',status:'done'},money),/−\$5.00/);
});
test('provider text cannot inject markup into the account transaction feed',()=>{
 assert.doesNotMatch(C.transaction({kind:'topup',status:'paid',cents:100,providerTitle:'<img src=x onerror=alert(1)>',createdAt:0},money),/<img/);
});
function loading(){const nodes=new Map(),timers=new Map();let index=0;const node=()=>({textContent:'',attributes:{},classes:new Set(),listeners:{},setAttribute(k,v){this.attributes[k]=v;},addEventListener(k,v){this.listeners[k]=v;},get classList(){return {add:k=>this.classes.add(k),remove:k=>this.classes.delete(k)};}});
 const document={getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);}};
 let reloads=0;const ctx={document,setTimeout:(f,ms)=>{timers.set(++index,{f,ms});return index;},clearTimeout:id=>timers.delete(id),location:{reload(){reloads++;}}};
 vm.runInNewContext(fs.readFileSync('public/croco-lobby.js','utf8'),ctx);return {ctx,nodes,timers,reloads:()=>reloads};}
test('connection overlay clears its timer after auth and does not reappear over a live game',()=>{const h=loading();h.ctx.CrocoLobby.loading.dismiss();assert.equal(h.timers.size,0);assert.ok(h.nodes.get('croco-loading').classes.has('hidden'));h.ctx.CrocoLobby.loading.message('reconnecting');assert.equal(h.nodes.get('croco-loading-status').textContent,'');});
test('slow connection offers retry; terminal auth errors stop the animated waiting state',()=>{const h=loading();[...h.timers.values()][0].f();assert.match(h.nodes.get('croco-loading-status').textContent,/больше времени/);h.ctx.CrocoLobby.loading.message('Откройте Croco через Telegram',true);assert.ok(h.nodes.get('croco-loading').classes.has('is-error'));assert.equal(h.nodes.get('croco-loading').attributes['aria-busy'],'false');h.nodes.get('croco-retry').listeners.click();assert.equal(h.reloads(),1);});
test('deploy checks include all new production assets',()=>{
 const script=fs.readFileSync('scripts/crash-update.sh','utf8');for(const p of ['public/croco-lobby.css','public/img/croco/mascot.webp','public/img/croco/nvuti-banner.webp']){assert.ok(script.includes(p));assert.ok(fs.statSync(p).size>0);}
});

test('catalog search filters every tile, reports no matches and restores all games when cleared',()=>{
 const nodes=new Map();const node=()=>({value:'',textContent:'',listeners:{},hidden:false,classList:{add(){},remove(){},toggle(k,v){this[k]=v;}},addEventListener(k,f){this.listeners[k]=f;}});
 const get=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);};
 const tiles=['Nvuti','Keno','Cryo Vault'].map(text=>Object.assign(node(),{textContent:text}));
 const doc={body:{dataset:{tab:'games'}},getElementById:get,querySelector:()=>null,querySelectorAll:()=>tiles};
 vm.runInNewContext(fs.readFileSync('public/croco-lobby.js','utf8'),{document:doc,setTimeout(){},clearTimeout(){},location:{reload(){}}});
 const input=get('games-search');input.value='  KENO ';input.listeners.input();assert.deepEqual(tiles.map(t=>t.classList.hidden),[true,false,true]);
 input.value='missing';input.listeners.input();assert.equal(get('games-empty').classList.hidden,false);
 input.value='';input.listeners.input();assert.deepEqual(tiles.map(t=>t.classList.hidden),[false,false,false]);assert.equal(get('games-empty').classList.hidden,true);
});
test('Live shows real payout and multiplier, escapes nicknames and handles unknown ratios',()=>{
 const catalog=require('../public/game-catalog');
 assert.match(C.liveHtml([],money,catalog),/Пока нет выигрышей/);
 const html=C.liveHtml([{name:'<img onerror=x>',game:'mines',amount:100,payout:250,multiplier:2.5},{name:'Poker player',game:'holdem',amount:900}],money,catalog);
 assert.ok(!html.includes('<img onerror'));assert.match(html,/&lt;img onerror=x&gt;/);
 assert.match(html,/2,50×/);assert.match(html,/\$2.50/);assert.match(html,/mines.webp/);assert.match(html,/—/);
});
