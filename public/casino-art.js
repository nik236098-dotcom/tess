'use strict';
const CasinoArt=(()=>{
 const cells={gem:0,chicken:1,coin:2,ball:3,rock:4,paper:5,scissors:6,pin:7,race:8,balloon:9,target:10,fish:11,pinball:12,seven:13,bowling:14,orbit:15};
 function sprite(key,cls=''){const i=cells[key]??0;return `<span class="cg-sprite ${cls}" style="--sx:${(i%4)*100/3}%;--sy:${Math.floor(i/4)*100/3}%" aria-hidden="true"></span>`;}
 function svg(key,cls=''){return sprite(key,cls);}
 function cover(id){
  if(id==='videopoker'||id==='andar')return '<span class="cg-cover-cards"><i></i><i></i></span>';
  if(id==='sicbo')return `<span class="cg-cover-dice">${[5,3].map(n=>`<span class="cg-cover-cube">${Array.from({length:9},(_,i)=>`<i class="${(n===5?[0,2,4,6,8]:[0,4,8]).includes(i)?'is-dot':''}"></i>`).join('')}</span>`).join('')}</span>`;
  if(id==='rps')return `<span class="cg-cover-pair">${sprite('rock')}${sprite('scissors')}</span>`;
  if(id==='slots')return `<span class="cg-cover-pair">${sprite('seven')}${sprite('seven')}</span>`;
  const map={diamonds:'gem',chicken:'chicken',coin:'coin',darts:'target',bowling:'bowling',balloon:'balloon',race:'race',pinball:'pinball',fishing:'fish'};
  return sprite(map[id]);
 }
 return {sprite,svg,cover};
})();
