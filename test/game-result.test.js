'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const Result=require('../public/game-result');
test('result uses credited cents, including partial returns and a rounded break-even',()=>{
  for(const [payout,kind] of [[300,'win'],[100,'push'],[40,'partial'],[0,'lose']]){
    const view=Result.model({bet:100,payout});assert.equal(view.kind,kind);
    assert.match(Result.markup(view),new RegExp('\\$'+(payout/100).toFixed(2).replace('.','\\.')));
    assert.ok(!Result.markup(view).includes('+$'));
  }
  assert.equal(Result.model({bet:10,payout:10,multiplier:1.02}).multiplier,1);
  assert.equal(Result.model({bet:100,payout:0,multiplier:15.68}).multiplier,0);
});
test('batch and split-hand results compare total payout with total stake',()=>{
  assert.equal(Result.model({stake:500,payout:550}).kind,'win');
  assert.equal(Result.model({stake:200,payout:100}).kind,'partial');
  assert.equal(Result.model({stake:500,payout:500}).kind,'push');
});
test('unconfirmed payment is hidden; dismissal survives rerenders and resets for a new round',()=>{
  const classes=new Set(),node={dataset:{},innerHTML:'',setAttribute(){},classList:{add:n=>classes.add(n),remove:n=>classes.delete(n)}};
  const round={bet:100,payout:300,settled:false};
  assert.equal(Result.show(node,round,'one'),false);assert.equal(node.innerHTML,'');
  round.settled=true;assert.equal(Result.show(node,round,'one'),true);node.onclick();
  assert.equal(Result.show(node,round,'one'),false);assert.ok(classes.has('hidden'));
  Result.hide(node);assert.equal(Result.show(node,round,'two'),true);assert.ok(!classes.has('hidden'));
});
test('invalid monetary data cannot be presented as a settled result and descriptions are escaped',()=>{
  for(const round of [{bet:0,payout:100},{bet:100,payout:-1},{bet:NaN,payout:100},{bet:100,payout:1.5}])assert.equal(Result.model(round),null);
  const html=Result.markup(Result.model({bet:100,payout:100,description:'<img src=x onerror=alert(1)>'}));
  assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;img'));
});
