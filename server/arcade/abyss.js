'use strict';
const {randomInt}=require('node:crypto'),R=require('../../public/abyss-rules');
class AbyssError extends Error {}
const fail=text=>{throw new AbyssError(text);};
function config(){return {minBet:R.stakes[0],maxBet:R.stakes.at(-1),stakes:R.stakes,buyCost:R.buyCost};}
function check(previous,revision){if(!Number.isSafeInteger(revision)||revision!==previous.revision)fail('Раунд обновился. Повторите действие');}
function draw(weights,rng){let n=rng(weights.reduce((a,b)=>a+b,0));for(let i=0;i<weights.length;i++){if(n<weights[i])return i;n-=weights[i];}throw new AbyssError('Некорректный результат генератора');}
function evaluate(grid,unitBet){
 const wins=[];let payout=0;
 for(let line=0;line<R.lines.length;line++){
  const cells=R.lines[line].map((row,col)=>row*5+col);let best=null;
  for(let symbol=0;symbol<=R.wild;symbol++){
   let count=0;while(count<5&&(grid[cells[count]]===symbol||grid[cells[count]]===R.wild))count++;
   if(count<3)continue;const pay=R.symbols[symbol].pay[count-3];
   if(!best||pay>best.pay)best={line,symbol,count,pay,cells:cells.slice(0,count),payout:unitBet/R.lines.length*pay};
  }
  if(best){wins.push(best);payout+=best.payout;}
 }
 return {lines:wins,payout};
}
function finish(r){
 r.phase='done';r.multiplier=r.payout/r.bet;r.result=r.payout>r.bet?'win':r.payout===r.bet?'push':'lose';
 r.history=[{multiplier:r.multiplier,payout:r.payout,result:r.result,bought:r.options.buyBonus},...r.history].slice(0,15);return r;
}
function spin(r,rng){
 const bonusSpin=r.bonus.remaining>0,usedMultiplier=bonusSpin?r.bonus.multiplier:1;
 const grid=Array.from({length:15},()=>draw(bonusSpin?R.bonusWeights:R.baseWeights,rng));
 const evaluated=evaluate(grid,r.unitBet),rawWin=evaluated.payout*usedMultiplier;
 const win=Math.min(rawWin,r.unitBet*R.maxWin-r.payout);r.payout+=win;
 if(bonusSpin){r.bonus.remaining--;r.bonus.played++;if(win>0)r.bonus.multiplier=Math.min(R.maxMultiplier,r.bonus.multiplier+1);}
 const scatterCount=grid.filter(n=>n===R.scatter).length;
 const triggered=scatterCount>=3?Math.min(bonusSpin?R.retrigger:R.freeSpins,R.maxSpins-r.bonus.awarded):0;
 r.bonus.remaining+=triggered;r.bonus.awarded+=triggered;
 const capped=r.payout===r.unitBet*R.maxWin;if(capped)r.bonus.remaining=0;
 r.detail={grid,lines:evaluated.lines,win,rawWin,scatterCount,triggered,bonusSpin,usedMultiplier,capped};
 r.revision++;if(!r.bonus.remaining)finish(r);return r;
}
function start(previous,amount,options,revision,rng=randomInt){
 check(previous,revision);if(previous.phase==='play'||!previous.settled)fail('Сначала завершите текущий раунд');
 if(!Number.isSafeInteger(amount)||!R.stakes.includes(amount))fail('Выберите ставку из списка');
 if(!options||typeof options!=='object'||Array.isArray(options)||('buyBonus'in options&&typeof options.buyBonus!=='boolean'))fail('Некорректные настройки');
 const bought=options.buyBonus===true;
 const r={version:1,game:'abyss',revision:revision+1,phase:'play',settled:false,unitBet:amount,bet:amount*(bought?R.buyCost:1),payout:0,multiplier:0,result:null,history:previous.history||[],options:{buyBonus:bought},bonus:{remaining:0,awarded:0,played:0,multiplier:1}};
 if(!bought)return spin(r,rng);
 r.bonus.remaining=R.freeSpins;r.bonus.awarded=R.freeSpins;
 const grid=Array.from({length:15},()=>draw(R.baseWeights.slice(0,8),rng));const columns=[0,1,2,3,4];
 for(let i=0;i<3;i++){const col=columns.splice(rng(columns.length),1)[0];grid[rng(3)*5+col]=R.scatter;}
 // The purchased trigger awards the feature only: never display an unpaid line win.
 if(evaluate(grid,amount).payout)grid.forEach((n,i)=>{if(n!==R.scatter)grid[i]=(i%5+Math.floor(i/5)*3)%8;});
 r.detail={grid,lines:[],win:0,rawWin:0,scatterCount:3,triggered:R.freeSpins,bonusSpin:false,usedMultiplier:1,bought:true,capped:false};
 return r;
}
function act(previous,action,index,revision,rng=randomInt){
 check(previous,revision);if(previous.game!=='abyss'||previous.phase!=='play'||previous.settled||previous.bonus?.remaining<1)fail('Нет активного бонуса');
 if(action!=='ag_pick'||index!==0)fail('Продолжите бесплатные вращения');
 return spin(structuredClone(previous),rng);
}
function publicState(r){
 const out={phase:r.phase,revision:r.revision,settled:r.settled,bet:r.bet,payout:r.payout,multiplier:r.multiplier,result:r.result,history:r.history,options:r.options||null};
 if(r.phase!=='bet')Object.assign(out,{unitBet:r.unitBet,bonus:r.bonus,detail:r.detail});
 return structuredClone(out);
}
module.exports={config,start,act,publicState,evaluate,draw,AbyssError};
