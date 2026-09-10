 'use strict';
(function(root){
 const common=typeof module==='object'&&module.exports?require('./abyss-rules'):root.AbyssRules;
 const make=(id,title,feature,names)=>({id,title,feature,lines:common.lines,stakes:common.stakes,wild:8,scatter:9,freeSpins:8,retrigger:3,maxSpins:32,maxWin:2500,buyCost:100,
 symbols:names.map((name,i)=>({id:String(i),name,pay:i===9?[]:[8+i*3,24+i*12,90+i*40]})),
 baseWeights:[220,200,180,160,140,120,100,80,18,20],bonusWeights:[150,145,140,135,130,125,120,115,22,22]});
 const cryo=make('cryo','CRYO VAULT','DEEP FREEZE',['Cryo Capsule','Expedition Visor','Ice Crystal','Power Cell','Vault Key','Data Drive','Pressure Gauge','Frozen Relic','Frozen Core','Access Badge']);
 const midnight=make('midnight','MIDNIGHT EXPRESS','VAULT HEIST',['Pocket Watch','Leather Case','Rail Lantern','Silver Key','Compass','Velvet Mask','Engine','Vault','Conductor','Golden Ticket']);
 cryo.upgrades=[1,2,3,5];
 cryo.bonusWeights[8]=35;midnight.bonusWeights[8]=148;
 cryo.description='3 Scatter дают 8 бесплатных вращений. В бонусе Wild остаётся на своём месте до конца. Повторный Wild в этой ячейке повышает его множитель: 1× → 2× → 3× → 5×. Множители Wild в выигрышной линии складываются; без Wild множитель 1×. Три новых Scatter добавляют 3 вращения, максимум 32 за бонус. Scatter на замороженной ячейке заменяется сохранённым Wild и не учитывается.';
 midnight.description='3 Scatter дают 8 бесплатных вращений. В бонусе каждый выпавший Conductor Wild добавляет ключ. Каждые 3 ключа открывают следующий вагон: множитель всех линий растёт с 1× до 2×, затем 3× и 5×. Новый множитель действует на текущем вращении. Wild не сохраняются. Три Scatter добавляют 3 вращения, максимум 32 за бонус.';
 for(const r of [cryo,midnight])r.description+=' 5 барабанов, 3 ряда, 20 линий слева направо; оплачивается лучшая комбинация 3–5 символов на линии. Wild заменяет обычные символы. Выплаты считаются от 1/20 ставки, итог вращения округляется вниз до цента. Bonus Buy стоит 100 ставок и запускает тот же бонус через три Scatter без выплаты вводного вращения. Общий максимум — 2500 ставок за вращение. Состояние сохраняется при выходе.';
 const api={cryo,midnight};if(typeof module==='object'&&module.exports)module.exports=api;else root.FeatureSlotRules=api;
})(globalThis);
