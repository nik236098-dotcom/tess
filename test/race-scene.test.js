'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),race=require('../public/race-scene');
function permutations(items){return items.length?items.flatMap((n,i)=>permutations(items.filter((_,j)=>j!==i)).map(t=>[n,...t])):[[]];}
test('all 24 finishing orders follow the server, every car advances continuously in its lane',()=>{
 for(const order of permutations([0,1,2,3])){const info={detail:{order,winner:order[0]}},crossings=new Map();let previous=race.frame(info,0);
  for(let i=1;i<=200;i++){const f=race.frame(info,i/200);f.cars.forEach((c,j)=>{assert.ok(c.y<=previous.cars[j].y+1e-9);assert.ok(c.scale>0);if(c.finished&&!crossings.has(j))crossings.set(j,i);});for(let j=1;j<4;j++)assert.ok(f.cars[j].x>f.cars[j-1].x);previous=f;}
  assert.deepEqual([...crossings.keys()],order);assert.equal(previous.complete,true);assert.equal([...previous.cars].sort((a,b)=>a.y-b.y)[0],previous.cars[order[0]]);
 }
});
test('winner is not exposed until animation finishes and reduced motion shows final result',()=>{const info={phase:'done',detail:{winner:2,order:[2,0,3,1]}};assert.doesNotMatch(race.board(info,true,0),/Первым финишировал/);assert.match(race.board(info,false,0),/Первым финишировал №3/);assert.ok(race.frame(info,1).cars.every(c=>c.finished));});
test('a finish is recorded exactly when the nose crosses the drawn finish line, with no car overlap',()=>{
 for(const order of permutations([0,1,2,3]))for(let i=0;i<=300;i++){
  const f=race.frame({detail:{order}},i/300);
  for(const car of f.cars)assert.equal(car.finished,car.noseY<=race.geometry.finishY);
  for(let lane=1;lane<4;lane++){const a=f.cars[lane-1],b=f.cars[lane];assert.ok(a.x+35*a.scale<b.x-35*b.scale);}
 }
});
