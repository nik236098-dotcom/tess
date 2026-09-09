'use strict';
(function(root){
  const copy=(dealer,hands)=>({dealer:dealer.slice(),hands:hands.map(h=>h.slice())});
  // Pure presentation plan. Server cards and payouts are never changed.
  function plan(oldDealer,oldHands,dealer,hands,fresh){
    let d=fresh?[]:oldDealer.slice(),h=fresh?hands.map(()=>[]):oldHands.map(a=>a.slice());
    if(!fresh&&hands.length>h.length&&h.length===1){h=[[h[0][0]],[h[0][1]]];}
    while(h.length<hands.length)h.push([]);
    const initial=copy(d,h),steps=[];
    const add=(side,hand,index,code,kind='deal')=>{
      (side==='dealer'?d:h[hand])[index]=code;
      steps.push({...copy(d,h),side,hand,index,kind});
    };
    if(fresh){
      for(let i=0;i<2;i++){
        for(let k=0;k<hands.length;k++)if(hands[k][i])add('player',k,i,hands[k][i]);
        if(dealer[i])add('dealer',0,i,i===1?'??':dealer[i]);
      }
    }
    for(let k=0;k<hands.length;k++)for(let i=0;i<hands[k].length;i++)if(h[k][i]!==hands[k][i])add('player',k,i,hands[k][i],h[k][i]?'flip':'deal');
    for(let i=0;i<dealer.length;i++)if(d[i]!==dealer[i])add('dealer',0,i,dealer[i],d[i]==='??'?'flip':'deal');
    return {initial,steps};
  }
  const api={plan};if(typeof module==='object'&&module.exports)module.exports=api;else root.BlackjackDeal=api;
})(globalThis);
