'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),scene=require('../public/balloon-scene');
test('pump compresses before inflation finishes and returns fully; neck remains anchored and balloon stays inside scene',()=>{
 const old={step:4},info={step:5,last:{safe:true}};
 assert.equal(scene.frame(info,old,0).pump,0);
 assert.ok(scene.frame(info,old,.36).pump>54);
 assert.equal(scene.frame(info,old,1).pump,0);
 assert.ok(scene.frame(info,old,.5).scale>scene.frame(info,old,0).scale);
 for(let step=0;step<=24;step++)assert.ok(286+(19-286)*scene.frame({step},null,1).scale>0);
 assert.equal(scene.frame(info,info,.36).pump,0,'restored state does not replay a stroke');
});
test('only server loss bursts; fragments finish and reduced motion reaches the final state',()=>{
 const old={step:3},lose={phase:'done',step:3,last:{safe:false}},win={step:4,last:{safe:true}};
 assert.equal(scene.frame(lose,old,.65).burst,false);
 assert.equal(scene.frame(lose,old,.7).burst,true);
 assert.equal(scene.frame(lose,old,1).progress,1);
 assert.equal(scene.frame(win,old,1).burst,false);
 const html=scene.board(lose,false,false);assert.match(html,/Шар лопнул/);assert.doesNotMatch(html,/Audio|sound/);
});

test('step strip preserves server coefficients, highlights the completed step and reveals zero on first-pump loss',()=>{
 const initial={phase:'play',step:0,coefficients:[1.02,1.06]},lose={...initial,phase:'done',multiplier:0,last:{safe:false}};
 const pending=scene.board(lose,true,true,[],initial);
 assert.match(pending,/aria-current="step" data-bl-step="0"/);
 assert.doesNotMatch(pending,/Шар лопнул|is-lost/);
 const done=scene.board(lose,false,false);
 assert.match(done,/Шар лопнул · 0,00×/);
 assert.doesNotMatch(done,/aria-current="step"|id="bl-value"/);
 assert.match(done,/is-lost[^>]*data-bl-step="1"/);
 const won=scene.board({...initial,step:2,multiplier:1.06},false,false);
 assert.match(won,/aria-current="step" data-bl-step="2"/);
 assert.match(won,/1,06×/);
});
