 'use strict';
const {randomInt}=require('node:crypto');
const rules=require('../../public/feature-slots-rules');
const {draw,AbyssError}=require('./abyss');
const fail=s=>{throw new AbyssError(s);};
function config(id){const r=rules[id];return {minBet:r.stakes[0],maxBet:r.stakes.at(-1),stakes:r.stakes,buyCost:r.buyCost};}
function evaluate(id,grid,bet,locked={},multiplier=1){
 const r=rules[id],lines=[];let numerator=0;
 r.lines.forEach((line,index)=>{
  const cells=line.map((row,col)=>row*5+col);let best=null;
  for(let symbol=0;symbol<=r.wild;symbol++){
   let count=0;while(count<5&&(grid[cells[count]]===symbol||grid[cells[count]]===r.wild))count++;
   if(count<3)continue;
   const hit=cells.slice(0,count),factor=id==='cryo'?Math.max(1,hit.reduce((sum,c)=>sum+(grid[c]===r.wild?(locked[c]||0):0),0)):multiplier;
   const pay=r.symbols[symbol].pay[count-3],value=pay*factor;
   if(!best||value>best.value)best={line:index,symbol,count,cells:hit,pay,factor,value,payout:Math.floor(bet*value/r.lines.length)};
  }
  if(best){numerator+=bet*best.value;lines.push(best);}
 });
 return {lines,payout:Math.floor(numerator/r.lines.length)};
}
function finish(r){r.phase='done';r.multiplier=r.payout/r.bet;r.result=r.payout>r.bet?'win':r.payout===r.bet?'push':'lose';r.history=[{multiplier:r.multiplier,payout:r.payout,result:r.result,bought:r.options.buyBonus},...r.history].slice(0,15);return r;}
function spin(round,rng=randomInt){
 const r=structuredClone(round),R=rules[r.game],bonusSpin=r.bonus.remaining>0;
 const rawGrid=Array.from({length:15},()=>draw(bonusSpin?R.bonusWeights:R.baseWeights,rng));
 const grid=[...rawGrid],added=[],upgraded=[];
 if(bonusSpin){
  r.bonus.remaining--;r.bonus.played++;
  if(r.game==='cryo'){
   for(let c=0;c<15;c++){
    const before=r.bonus.locked[c];
    if(rawGrid[c]===R.wild){
     r.bonus.locked[c]=before?R.upgrades[Math.min(3,R.upgrades.indexOf(before)+1)]:1;
     if(!before)added.push(c);else if(r.bonus.locked[c]>before)upgraded.push(c);
    }
    if(r.bonus.locked[c])grid[c]=R.wild;
   }
  }else{
   r.bonus.keys=Math.min(9,r.bonus.keys+grid.filter(n=>n===R.wild).length);
   r.bonus.multiplier=[1,2,3,5][Math.floor(r.bonus.keys/3)];
  }
 }
 const usedMultiplier=bonusSpin?r.bonus.multiplier:1;
 const evaluated=evaluate(r.game,grid,r.unitBet,bonusSpin?r.bonus.locked:{},usedMultiplier);
 const rawWin=evaluated.payout,win=Math.min(rawWin,r.unitBet*R.maxWin-r.payout);r.payout+=win;
 const scatterCount=grid.filter(n=>n===R.scatter).length;
 const triggered=scatterCount>=3?Math.min(bonusSpin?R.retrigger:R.freeSpins,R.maxSpins-r.bonus.awarded):0;
 r.bonus.remaining+=triggered;r.bonus.awarded+=triggered;
 const capped=r.payout>=r.unitBet*R.maxWin;if(capped)r.bonus.remaining=0;
 r.detail={grid,lines:evaluated.lines,win,rawWin,scatterCount,triggered,bonusSpin,usedMultiplier,capped,added,upgraded};
 r.revision++;return r.bonus.remaining?r:finish(r);
}
function check(previous,revision){if(!Number.isSafeInteger(revision)||revision!==previous.revision)fail('Раунд обновился. Повторите действие');}
function start(id,previous,amount,options,revision,rng=randomInt){
 const R=rules[id];check(previous,revision);
 if(previous.phase==='play'||!previous.settled)fail('Сначала завершите текущий раунд');
 if(!Number.isSafeInteger(amount)||!R.stakes.includes(amount))fail('Выберите ставку из списка');
 if(!options||typeof options!=='object'||Array.isArray(options)||Object.keys(options).some(k=>k!=='buyBonus')||('buyBonus'in options&&typeof options.buyBonus!=='boolean'))fail('Некорректные настройки');
 const bought=options.buyBonus===true;
 const r={version:1,game:id,phase:'play',settled:false,revision:revision+1,unitBet:amount,bet:amount*(bought?R.buyCost:1),payout:0,multiplier:0,result:null,history:previous.history||[],options:{buyBonus:bought},bonus:{remaining:0,awarded:0,played:0,multiplier:1,locked:{},keys:0}};
 if(!bought)return spin(r,rng);
 const grid=Array.from({length:15},()=>draw(R.baseWeights.slice(0,8),rng)),cols=[0,1,2,3,4];
 for(let i=0;i<3;i++){const col=cols.splice(rng(cols.length),1)[0];grid[rng(3)*5+col]=R.scatter;}
 if(evaluate(id,grid,amount).payout)grid.forEach((n,i)=>{if(n!==R.scatter)grid[i]=(i%5+Math.floor(i/5)*3)%8;});
 r.bonus.remaining=R.freeSpins;r.bonus.awarded=R.freeSpins;
 r.detail={grid,lines:[],win:0,rawWin:0,scatterCount:3,triggered:R.freeSpins,bonusSpin:false,usedMultiplier:1,capped:false,bought:true,added:[],upgraded:[]};return r;
}
function act(id,previous,action,index,revision,rng=randomInt){check(previous,revision);if(previous.game!==id||previous.phase!=='play'||previous.settled||previous.bonus?.remaining<1)fail('Нет активного бонуса');if(action!=='ag_pick'||index!==0)fail('Продолжите бесплатные вращения');return spin(previous,rng);}
function publicState(id,r){const out={phase:r.phase,revision:r.revision,settled:r.settled,bet:r.bet,payout:r.payout,multiplier:r.multiplier,result:r.result,history:r.history,options:r.options||null};if(r.phase!=='bet')Object.assign(out,{unitBet:r.unitBet,bonus:r.bonus,detail:r.detail});return structuredClone(out);}
module.exports={ids:Object.keys(rules),config,start,act,publicState,evaluate};
