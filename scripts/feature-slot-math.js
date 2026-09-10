'use strict';
// Reproducible Monte Carlo audit. Observed returns are estimates, not certified RTP.
const F=require('../server/arcade/feature-slots'),G=require('../server/arcade/game');
const samples=Number(process.argv[2]||20000);if(!Number.isSafeInteger(samples)||samples<100||samples>1000000)throw Error('samples must be 100..1000000');
const result={samples,seed:872331,unitBet:100,bonusCostX:100,games:{}};
for(const id of F.ids){let seed=result.seed;const rng=n=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return Math.floor(seed/4294967296*n);};let sum=0,squared=0,max=0,spins=0,capped=0;
 for(let i=0;i<samples;i++){let r=F.start(id,G.initial(),100,{buyBonus:true},0,rng);while(r.phase==='play')r=F.act(id,r,'ag_pick',0,r.revision,rng);const x=r.payout/100;sum+=x;squared+=x*x;max=Math.max(max,x);spins+=r.bonus.played;capped+=Number(r.detail.capped);}
 const mean=sum/samples,se=Math.sqrt(Math.max(0,squared/samples-mean*mean)/samples);
 result.games[id]={meanBonusX:mean,meanReturnOnBuy:mean/100,standardErrorX:se,maxObservedX:max,meanSpins:spins/samples,capped};
}console.log(JSON.stringify(result,null,2));
