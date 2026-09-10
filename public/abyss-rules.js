'use strict';
(function(root){
 const symbols=[
  {id:'nautilus',name:'Наутилус',pay:[16,45,140]},
  {id:'gauge',name:'Манометр',pay:[18,50,160]},
  {id:'capsule',name:'Капсула',pay:[20,60,180]},
  {id:'jellyfish',name:'Медуза',pay:[22,70,210]},
  {id:'glove',name:'Перчатка',pay:[25,80,250]},
  {id:'anemone',name:'Актиния',pay:[30,100,320]},
  {id:'sonar',name:'Сонар',pay:[36,130,400]},
  {id:'fossil',name:'Аммонит',pay:[45,170,550]},
  {id:'wild',name:'Wild',pay:[60,240,1000]},
  {id:'scatter',name:'Scatter',pay:[]}
 ];
 const lines=[[0,0,0,0,0],[1,1,1,1,1],[2,2,2,2,2],[0,1,2,1,0],[2,1,0,1,2],[0,0,1,2,2],[2,2,1,0,0],[1,0,0,0,1],[1,2,2,2,1],[0,1,1,1,0],[2,1,1,1,2],[1,0,1,2,1],[1,2,1,0,1],[0,1,0,1,0],[2,1,2,1,2],[1,0,1,0,1],[1,2,1,2,1],[0,2,0,2,0],[2,0,2,0,2],[0,0,1,0,0]];
 const stakes=[20,40,60,80,100,120,160,200,300,400,600,800,1000,1500,2000,3000,4000,5000,10000,20000,50000,100000];
 const api={version:1,symbols,lines,stakes,wild:8,scatter:9,freeSpins:8,retrigger:4,maxSpins:40,maxMultiplier:10,maxWin:2500,buyCost:100,
  baseWeights:[220,200,180,160,140,120,100,80,23,20],bonusWeights:[120,120,120,120,120,120,120,120,129,20]};
 if(typeof module==='object'&&module.exports)module.exports=api;else root.AbyssRules=api;
})(globalThis);
