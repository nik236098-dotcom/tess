'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {plan}=require('../public/blackjack-deal');
test('opening deal alternates player/dealer one card at a time',()=>{
 const p=plan([],[],['9s','??'],[['Ts','7h']],true);
 assert.deepEqual(p.initial,{dealer:[],hands:[[]]});
 assert.deepEqual(p.steps.map(s=>s.side),['player','dealer','player','dealer']);
 assert.deepEqual(p.steps.map(s=>s.dealer.length+s.hands[0].length),[1,2,3,4]);
 assert.deepEqual(p.steps.at(-1).hands,[['Ts','7h']]);
});
test('immediate blackjack is dealt before the hole card flips and result is shown',()=>{
 const p=plan([],[],['Qs','9d'],[['As','Kh']],true);
 assert.equal(p.steps[3].dealer[1],'??');assert.equal(p.steps[4].kind,'flip');
 assert.equal(p.steps[4].dealer[1],'9d');
});
test('hit adds only the new card; dealer reveal and draws are separate steps',()=>{
 const beforeD=['9s','??'],beforeH=[['Ts','7h']];
 const hit=plan(beforeD,beforeH,beforeD,[['Ts','7h','2d']],false);
 assert.equal(hit.steps.length,1);assert.equal(hit.steps[0].index,2);
 const dealer=plan(beforeD,beforeH,['9s','4d','5c'],beforeH,false);
 assert.deepEqual(dealer.steps.map(s=>s.kind),['flip','deal']);
 assert.equal(dealer.steps[0].dealer.length,2);
 assert.equal(plan(beforeD,beforeH,beforeD,beforeH,false).steps.length,0,'duplicate snapshots do not redeal');
});
test('split redistributes existing cards and only deals the two new ones',()=>{
 const p=plan(['9s','??'],[['8s','8h']],['9s','??'],[['8s','3d'],['8h','Tc']],false);
 assert.deepEqual(p.initial.hands,[['8s'],['8h']]);
 assert.deepEqual(p.steps.map(s=>[s.hand,s.index,s.kind]),[[0,1,'deal'],[1,1,'deal']]);
});
