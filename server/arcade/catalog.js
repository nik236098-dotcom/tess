'use strict';
const {randomInt}=require('node:crypto');
const {games,ids}=require('../../public/casino-rules');
class CatalogError extends Error {}
const fail=message=>{throw new CatalogError(message);};
const integer=(n,min,max)=>Number.isInteger(n)&&n>=min&&n<=max;
const rounded=n=>Math.floor((n+1e-10)*100)/100;
const cents=(bet,m)=>Math.floor(bet*Math.round(m*100)/100);
const shuffle=(size,rng)=>{const a=Array.from({length:size},(_,i)=>i);for(let i=0;i<size-1;i++){const j=i+rng(size-i);[a[i],a[j]]=[a[j],a[i]];}return a;};
const card=id=>({id,rank:id%13+2,suit:'schd'[Math.floor(id/13)]});
const distribution=game=>game==='fishing'?[[5000,0],[3000,.5],[1200,2],[600,5],[180,10],[20,55]]:[[6000,0],[2000,1],[1200,2],[600,5],[180,10],[20,30]];
function prize(game,rng){let roll=rng(10000);for(const [w,m] of distribution(game)){if(roll<w)return m;roll-=w;}throw Error('Invalid prize distribution');}
function multiplicities(values){return Object.values(values.reduce((a,n)=>(a[n]=(a[n]||0)+1,a),{})).sort((a,b)=>b-a);}
function evaluate(cards){
 const ranks=cards.map(c=>c.rank).sort((a,b)=>a-b), groups=multiplicities(ranks),flush=cards.every(c=>c.suit===cards[0].suit);
 const straight=new Set(ranks).size===5&&(ranks[4]-ranks[0]===4||ranks.join(',')==='2,3,4,5,14');
 if(flush&&straight)return ranks[0]===10?['Роял-флеш',800]:['Стрит-флеш',60];
 if(groups[0]===4)return ['Каре',22];if(groups.join(',')==='3,2')return ['Фулл-хаус',9];
 if(flush)return ['Флеш',6];if(straight)return ['Стрит',4];if(groups[0]===3)return ['Тройка',3];
 if(groups[0]===2&&groups[1]===2)return ['Две пары',2];
 if(ranks.some((n,i)=>n>=11&&ranks[i+1]===n))return ['Валеты и старше',1];return ['Нет комбинации',0];
}
function validate(game,o){
 if(!o||typeof o!=='object'||Array.isArray(o))fail('Некорректные настройки');
 const g=games[game];if(!g)fail('Игра не найдена');
 if(g.choices){if(!g.choices.some(([,v])=>v===o[game==='chicken'||game==='balloon'?'level':'side']))fail('Выберите настройку игры');return {[game==='chicken'||game==='balloon'?'level':'side']:o[game==='chicken'||game==='balloon'?'level':'side']};}
 if(game==='penalty'||game==='pinball'){if(!integer(o.side,0,game==='penalty'?4:1))fail('Выберите направление');return {side:o.side};}
 return {};
}
function seriesSpec(game,options){
 if(game==='chicken'||game==='balloon'){const size=game==='chicken'?21:25,bad={easy:1,medium:3,hard:5}[options.level];return {size,bad,max:size-bad};}
 return {max:game==='penalty'?5:game==='pinball'?10:20,p:game==='coin'||game==='rps'?.5:.8};
}
function coefficients(game,options){const s=seriesSpec(game,options);let p=1;return Array.from({length:s.max},(_,i)=>{p*=s.size?(s.size-s.bad-i)/(s.size-i):s.p;return rounded(.98/p);});}
function config(game){const g=games[game];if(!g)fail('Игра не найдена');return {minBet:100,maxBet:100000,catalog:true,definition:g};}
function finish(r,m){r.phase='done';r.multiplier=m;r.payout=cents(r.bet,m);r.result=r.payout>r.bet?'win':r.payout===r.bet?'push':'lose';r.revision++;r.history=[{multiplier:m,payout:r.payout,result:r.result},...r.history].slice(0,15);return r;}
function start(game,previous,amount,options,revision,rng=randomInt){
 if(!Number.isSafeInteger(revision)||revision!==previous.revision)fail('Раунд обновился');
 if(previous.phase==='play'||!previous.settled)fail('Сначала завершите текущий раунд');
 if(!integer(amount,100,100000))fail('Ставка от $1 до $1000');
 const selected=validate(game,options),r={version:1,revision:revision+1,phase:'play',settled:false,bet:amount,payout:0,multiplier:0,result:null,history:previous.history||[],options:selected,game};
 if(games[game].series){r.step=0;r.events=[];r.coefficients=coefficients(game,selected);const spec=seriesSpec(game,selected);if(spec.size)r.order=shuffle(spec.size,rng).map(n=>n<spec.bad?0:1);return r;}
 if(game==='videopoker'){r.deck=shuffle(52,rng);r.cards=r.deck.slice(0,5).map(card);return r;}

 let m=0;r.detail={};
 if(game==='diamonds'){const gems=Array.from({length:5},()=>rng(7)),key=multiplicities(gems).join(',');const values={'5':50,'4,1':5,'3,2':4,'3,1,1':3,'2,2,1':2,'2,1,1,1':.1};m=values[key]||0;r.detail={gems};}
 else if(game==='sicbo'){const dice=Array.from({length:3},()=>rng(6)+1),sum=dice.reduce((a,b)=>a+b,0),triple=dice.every(n=>n===dice[0]);m=selected.side==='triple'?(triple?31:0):!triple&&(selected.side==='small'?sum>=4&&sum<=10:sum>=11&&sum<=17)?2:0;r.detail={dice,sum,triple};}
 else if(game==='slots'){const grid=Array.from({length:9},()=>rng(6)),pays=[6,12,24,36,54,79.68],lines=[];let payout=0;for(let row=0;row<3;row++){const cells=grid.slice(row*3,row*3+3),stake=Math.floor(amount/3)+(row===0?amount%3:0),mult=cells.every(n=>n===cells[0])?pays[cells[0]]:0;const won=cents(stake,mult);payout+=won;lines.push({row,stake,multiplier:mult,payout:won});}r.detail={grid,lines};finish(r,payout/amount);r.payout=payout;r.multiplier=payout/amount;r.result=payout>amount?'win':payout===amount?'push':'lose';r.history[0]={multiplier:r.multiplier,payout,result:r.result};return r;}
 else if(game==='andar'){const deck=shuffle(52,rng),center=card(deck.shift()),dealt=[];for(const id of deck){const c=card(id);dealt.push(c);if(c.rank===center.rank)break;}const winner=dealt.length%2?'andar':'bahar';m=selected.side===winner?(winner==='andar'?1.9:2):0;r.detail={center,dealt,winner};}
 else if(game==='darts'){const area=rng(1000000)/1000000,angle=rng(1000000)/1000000*Math.PI*2;m=area<.01?20:area<.09?5:area<.36?1:.17;r.detail={radius:Math.sqrt(area),angle};}
 else if(game==='bowling'){const fallen=Array.from({length:10},()=>rng(2)===1),count=fallen.filter(Boolean).length;m=({6:.5,7:1,8:3,9:20,10:443})[count]||0;r.detail={fallen,count};}
 else if(game==='fishing'){m=prize(game,rng);r.detail={prize:m};}
 else if(game==='race'){const order=shuffle(4,rng);m=order[0]===selected.side?3.92:0;r.detail={order,winner:order[0]};}
 else fail('Игра не поддерживается');
 finish(r,m);
 if(game==='sicbo')Object.assign(r.history[0],{sum:r.detail.sum,dice:[...r.detail.dice],triple:r.detail.triple});
 return r;
}
function act(game,previous,action,index,revision,rng=randomInt){
 if(!Number.isSafeInteger(revision)||revision!==previous.revision)fail('Раунд обновился');
 if(previous.phase!=='play'||previous.settled||previous.game!==game)fail('Нет активного раунда');
 const r=structuredClone(previous),g=games[game];
 if(action==='ag_cashout'){if(!g.series)fail('В этой игре нет досрочной выплаты');return finish(r,r.step?r.coefficients[r.step-1]:1);}
 if(action!=='ag_pick')fail('Неизвестное действие');
 if(game==='videopoker'){
  if(!Array.isArray(index)||index.length>5||new Set(index).size!==index.length||index.some(n=>!integer(n,0,4)))fail('Отметьте карты, которые нужно оставить');
  let next=5;r.cards=r.cards.map((c,i)=>index.includes(i)?c:card(r.deck[next++]));r.held=index;const [name,m]=evaluate(r.cards);r.detail={combination:name};return finish(r,m);
 }
 if(!g.series)fail('Действие не поддерживается');
 let safe=true,event={};
 if(r.order){if(index!==0)fail('Нажмите следующий шаг');safe=Boolean(r.order[r.step]);event={safe};}
 else if(game==='coin'){if(!integer(index,0,1))fail('Выберите сторону');const opponent=rng(2);safe=index===opponent;event={choice:index,opponent,safe};}
 else if(game==='rps'){if(!integer(index,0,2))fail('Выберите жест');const opponent=rng(3);if(index===opponent){r.last={choice:index,opponent,tie:true};r.revision++;return r;}safe=(index-opponent+3)%3===1;event={choice:index,opponent,safe};}
 else if(game==='penalty'){if(!integer(index,0,4))fail('Выберите угол');const opponent=rng(5);safe=opponent!==index;event={choice:index,opponent,safe};}
 else if(game==='pinball'){if(!integer(index,0,1))fail('Выберите лопатку');safe=rng(5)!==0;event={choice:index,bumper:rng(3),safe};}
 r.last=event;r.events.push(event);r.revision++;
 if(!safe)return finish(r,0);
 r.step++;r.multiplier=r.coefficients[r.step-1];
 return r.step===r.coefficients.length?finish(r,r.multiplier):r;
}
function publicState(game,r){
 const out={phase:r.phase,revision:r.revision,settled:r.settled,bet:r.bet,payout:r.payout,multiplier:r.multiplier,result:r.result,history:r.history,options:r.options||null};
 if(r.phase==='bet')return out;
 if(games[game].series)Object.assign(out,{step:r.step,events:r.events,last:r.last,coefficients:r.coefficients,available:r.phase==='play'?cents(r.bet,r.step?r.coefficients[r.step-1]:1):r.payout});
 if(game==='videopoker'){const [name,multiplier]=evaluate(r.cards);Object.assign(out,{cards:r.cards,held:r.held||[],hand:{name,multiplier}});}
 if(r.phase==='done')out.detail=r.detail||null;
 return out;
}
module.exports={CatalogError,ids,config,start,act,publicState,evaluate,coefficients,distribution};
