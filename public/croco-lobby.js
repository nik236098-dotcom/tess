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
 const api={defaults,recent,remember,transaction,historyHtml};
 if(typeof module==='object'&&module.exports){module.exports=api;return;}
 root.CrocoLobby=api;
 const node=document.getElementById('croco-loading'),status=document.getElementById('croco-loading-status'),retry=document.getElementById('croco-retry');let dismissed=false;
 const timer=setTimeout(()=>{if(!dismissed){status.textContent='Подключение занимает больше времени. Проверьте интернет или попробуйте снова.';retry.classList.remove('hidden');}},12000);
 api.loading={dismiss(){dismissed=true;clearTimeout(timer);node.classList.add('hidden');node.setAttribute('aria-busy','false');},message(text,error=false){if(dismissed)return;status.textContent=text;if(error){clearTimeout(timer);node.classList.add('is-error');node.setAttribute('aria-busy','false');retry.classList.remove('hidden');}}};
 retry.addEventListener('click',()=>location.reload());
})(globalThis);
