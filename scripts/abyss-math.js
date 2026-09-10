'use strict';
// Deterministic offline audit. Production spins use crypto.randomInt.
const A=require('../server/arcade/abyss'),R=require('../public/abyss-rules'),G=require('../server/arcade/game');
let seed=927481;const rng=n=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)%n;};
const count=Number(process.argv[2]||100000);if(!Number.isInteger(count)||count<1000)throw Error('At least 1000 bonus rounds are required');
let base=0;const weights=R.baseWeights,total=weights.reduce((a,b)=>a+b,0);
for(let n=0;n<100000;n++){let code=n,p=1,row=[];for(let j=0;j<5;j++){const symbol=code%10;code=Math.floor(code/10);row.push(symbol);p*=weights[symbol]/total;}base+=p*A.evaluate([...row,...row,...row],20).payout/20;}
let trigger=0;const p=weights[9]/total;for(let k=3;k<=15;k++){let ways=1;for(let i=1;i<=k;i++)ways=ways*(16-i)/i;trigger+=ways*p**k*(1-p)**(15-k);}
let won=0,squared=0,caps=0,spins=0;const payouts=[];
for(let i=0;i<count;i++){let round=A.start(G.initial(),100,{buyBonus:true},0,rng);while(round.phase==='play')round=A.act(round,'ag_pick',0,round.revision,rng);const m=round.payout/100;won+=m;squared+=m*m;spins+=round.bonus.played;caps+=Number(round.detail.capped);payouts.push(m);}
const mean=won/count,se=Math.sqrt((squared/count-mean*mean)/count);payouts.sort((a,b)=>a-b);
console.log(JSON.stringify({version:R.version,seed:927481,bonusRounds:count,baseLineReturnExact:base,scatterTriggerProbabilityExact:trigger,bonusMeanInSpinBets:mean,bonusMean95CI:[mean-1.96*se,mean+1.96*se],bonusBuyReturnEstimate:mean/R.buyCost,baseGameReturnEstimate:base+trigger*mean,meanFreeSpins:spins/count,capHits:caps,bonusMedian:payouts[Math.floor(count*.5)],bonusP95:payouts[Math.floor(count*.95)],note:'Offline estimate, not certification. Base game estimate adds the simulated bonus EV to exact line EV; the round cap can slightly lower it.'},null,2));
