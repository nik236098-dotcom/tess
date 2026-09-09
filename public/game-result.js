'use strict';
// One presentation for confirmed round totals. All amounts are integer cents.
(function(root){
  const origins=new WeakMap();
  function restore(node){
    const origin=origins.get(node);
    if(origin){origin.parent.insertBefore(node,origin.next?.parentNode===origin.parent?origin.next:null);origins.delete(node);}
  }
  const titles={win:'Выигрыш',push:'Возврат ставки',partial:'Частичный возврат',lose:'Проигрыш'};
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function model(round){
    const bet=Number(round.bet??round.stake),payout=Number(round.payout);
    if(!Number.isSafeInteger(bet)||bet<=0||!Number.isSafeInteger(payout)||payout<0)return null;
    const kind=payout>bet?'win':payout===bet?'push':payout>0?'partial':'lose';
    const multiplier=payout===0?0:payout===bet?1:Number.isFinite(round.multiplier)&&round.multiplier>0?round.multiplier:payout/bet;
    return {kind,title:titles[kind],payout,bet,multiplier,description:round.description||''};
  }
  function markup(value){
    const n=value.multiplier===0?'0':value.multiplier.toFixed(2);
    return `<button type="button" class="g-result-close" aria-label="Закрыть результат">×</button><div class="g-result-title">${value.title}</div>${value.description?`<div class="g-result-description">${escape(value.description)}</div>`:''}<div class="g-result-label">Выплата</div><div class="g-result-amount">$${(value.payout/100).toFixed(2)}</div><div class="g-result-multiplier">${n}×</div>`;
  }
  function hide(node,reset=true){
    if(!node)return;
    node.classList.add('hidden');
    if(reset){node.innerHTML='';delete node.dataset.resultKey;delete node.dataset.dismissedResult;}
  }
  function show(node,round,key){
    if(!node)return false;
    const value=round&&round.settled!==false?model(round):null;
    if(!value){hide(node);return false;}
    key=String(key??[value.bet,value.payout,value.description].join(':'));
    if(node.dataset.dismissedResult===key)return false;
    // A screen-level portal escapes scaled artwork and never occupies field space.
    const screen=node.closest?.('.screen');
    if(screen&&node.parentElement!==screen){
      if(!origins.has(node))origins.set(node,{parent:node.parentElement,next:node.nextSibling});
      screen.appendChild(node);
    }
    if(node.dataset.resultKey!==key){
      node.dataset.resultKey=key;node.dataset.revision=key;
      node.className=`g-result is-${value.kind}`;node.innerHTML=markup(value);
      node.setAttribute('role','status');node.setAttribute('aria-live','polite');
      node.onclick=()=>{node.dataset.dismissedResult=key;hide(node,false);};
    }
    node.classList.remove('hidden');
    return true;
  }
  const api={model,markup,show,hide,restore};
  if(typeof module==='object'&&module.exports)module.exports=api;else root.GameResult=api;
})(globalThis);
