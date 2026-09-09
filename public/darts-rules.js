'use strict';
/* Medium payouts; areas are arranged monotonically inward by user request.
 * Sources and derivation: docs/DARTS.md. Browser geometry and server share this table.
 */
(function(root){
 const bands=[
  {value:.4,upper:1200,color:'#17233a',name:'Внешняя зона'},
  {value:.6,upper:537,color:'#354963',name:'Синяя зона'},
  {value:1.3,upper:192,color:'#efc45f',name:'Золотая зона'},
  {value:3.1,upper:102,color:'#ed8950',name:'Оранжевая зона'},
  {value:6,upper:52,color:'#e95a71',name:'Красная зона'},
  {value:16,upper:12,color:'#69e9aa',name:'Центр'}
 ].map((b,i,all)=>Object.freeze({...b,radius:Math.sqrt(b.upper/1200),probability:(b.upper-(all[i+1]?.upper||0))/1200}));
 function outcome(area){if(!Number.isFinite(area)||area<0||area>=1)throw new RangeError('Invalid dart area');return [...bands].reverse().find(b=>area<b.upper/1200).value;}
 const api=Object.freeze({version:'stake-medium-radial-v1',bands:Object.freeze(bands),outcome});
 if(typeof module==='object'&&module.exports)module.exports=api;else root.DartsRules=api;
})(globalThis);
