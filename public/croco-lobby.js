'use strict';
(function(root){
 const defaults=['nvuti','mines','crash','hilo'];
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function recent(storage,userId,catalog){try{const value=JSON.parse(storage.getItem('croco:recent:'+userId)||'[]');return Array.isArray(value)?[...new Set(value.filter(id=>Object.hasOwn(catalog,id)))].slice(0,8):[];}catch{return [];}}
 function remember(storage,userId,id,catalog){if(!userId||!Object.hasOwn(catalog,id))return;try{storage.setItem('croco:recent:'+userId,JSON.stringify([id,...recent(storage,userId,catalog).filter(v=>v!==id)].slice(0,8)));}catch{}}
 function transaction(item,money){
  const income=item.kind==='topup',paid=income&&item.status==='paid',out=!income&&item.status==='done';
  const titles={paid:'Пополнение',expired:'Счёт истёк',done:'Вывод',failed:'Вывод отменён',unknown:'Вывод в обработке',pending:income?'Ожидает оплаты':'Вывод в обработке'};
  const amount=income?(item.creditedCents??item.cents):item.cents;
  const date=new Date(item.createdAt);const when=Number.isNaN(date.getTime())?'':date.toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
  return `<div class="croco-tx"><span><b>${esc(titles[item.status]||'Операция')}</b><small>${esc([item.providerTitle,when].filter(Boolean).join(' · '))}</small></span><strong class="${paid?'is-in':out?'is-out':''}">${paid?'+':out?'−':''}${esc(money(amount||0))}</strong></div>`;
 }
 function historyHtml(items,money,limit=3){if(!Array.isArray(items)||!items.length)return '<div class="croco-empty"><svg class="icon"><use href="#i-receipt"></use></svg><b>Пока нет транзакций</b><p>Здесь появится история операций</p></div>';return items.slice(0,limit).map(item=>transaction(item,money)).join('');}
 function liveHtml(wins,money,catalog){
  if(!Array.isArray(wins)||!wins.length)return '<p class="croco-history-note">Пока нет выигрышей</p>';
  return wins.slice(0,8).map(win=>{
   const id=Object.hasOwn(catalog.names,win.game)?win.game:'holdem';
   const mult=Number.isFinite(win.multiplier)&&win.multiplier>0?win.multiplier.toFixed(2).replace('.',',')+'×':'—';
   return `<div class="croco-live-row"><span class="croco-live-player"><img src="${esc(catalog.artwork(id))}" width="32" height="32" alt="${esc(catalog.names[id])}" /><span><b>${esc(win.name||'Игрок')}</b><small>${esc(catalog.names[id])}</small></span></span><span class="croco-live-mult">${mult}</span><strong>${esc(money(win.payout??win.amount))}</strong></div>`;
  }).join('');
 }
 const api={defaults,recent,remember,transaction,historyHtml,liveHtml};
 if(typeof module==='object'&&module.exports){module.exports=api;return;}
 root.CrocoLobby=api;
 const search=document.getElementById('games-search');
 if(search)search.addEventListener('input',()=>{
  const query=search.value.trim().toLocaleLowerCase('ru');let count=0;
  document.querySelectorAll('#tab-games .game-tile').forEach(tile=>{const visible=tile.textContent.toLocaleLowerCase('ru').includes(query);tile.classList.toggle('hidden',!visible);if(visible)count++;});
  document.getElementById('games-empty').classList.toggle('hidden',count>0);
 });
 const lobby=document.querySelector?.('.lobby'),nav=document.getElementById('bottom-nav');let lastScroll=0;
 lobby?.addEventListener('scroll',()=>{const top=lobby.scrollTop,delta=top-lastScroll;lastScroll=top;if(document.body.dataset.tab!=='games'||top<12){nav.classList.remove('is-scroll-hidden');return;}if(Math.abs(delta)>3)nav.classList.toggle('is-scroll-hidden',delta>0);},{passive:true});

 const node=document.getElementById('croco-loading'),status=document.getElementById('croco-loading-status'),retry=document.getElementById('croco-retry');let dismissed=false;
 const timer=setTimeout(()=>{if(!dismissed){status.textContent='Подключение занимает больше времени. Проверьте интернет или попробуйте снова.';retry.classList.remove('hidden');}},12000);
 api.loading={dismiss(){dismissed=true;clearTimeout(timer);node.classList.add('hidden');node.setAttribute('aria-busy','false');},message(text,error=false){if(dismissed)return;status.textContent=text;if(error){clearTimeout(timer);node.classList.add('is-error');node.setAttribute('aria-busy','false');retry.classList.remove('hidden');}}};
 retry.addEventListener('click',()=>location.reload());
})(globalThis);
