'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const scene=require('../public/sicbo-scene'),motion=require('../public/casino-motion');
test('rounded dice form a closed mesh with no unpaired edges or detached faces',()=>{
 const edges=new Map(),g=scene.geometry.die;
 const key=p=>p.map(n=>n.toFixed(7)).join(',');
 for(let i=0;i<g.length;i+=18){const v=[g.slice(i,i+3),g.slice(i+6,i+9),g.slice(i+12,i+15)];
  for(let j=0;j<3;j++){const pair=[key(v[j]),key(v[(j+1)%3])].sort().join('|');edges.set(pair,(edges.get(pair)||0)+1);}
 }
 for(const [edge,count] of edges)assert.equal(count,2,edge);
 for(let i=0;i<g.length;i+=6){assert.ok(g.slice(i,i+6).every(Number.isFinite));assert.ok(Math.abs(Math.hypot(...g.slice(i+3,i+6))-1)<1e-9);}
});
test('all six results occupy the top of a settled die with distinct adjacent and opposite faces',()=>{
 for(let value=1;value<=6;value++){
  const frame=scene.scene([value,value,value],null);
  for(const call of frame.draws.filter(d=>d.mesh==='die')){
   assert.equal(call.pips[1],value);const faces=call.pips.flatMap(n=>[n,7-n]);assert.equal(new Set(faces).size,6);
   assert.equal(call.model[1],0);assert.equal(call.model[5],1);assert.equal(call.model[9],0);
  }
 }
});
test('animated rounded meshes stay above the tray floor through every hop and rotation',()=>{
 const g=scene.geometry.die;
 for(let tick=0;tick<=100;tick++){
  const poses=motion.frame('sicbo',{},null,tick/100).dice,frame=scene.scene([5,5,1],poses);
  assert.ok(frame.camera.every(Number.isFinite));
  for(const {model:m} of frame.draws.filter(d=>d.mesh==='die')){
   let min=Infinity;for(let i=0;i<g.length;i+=6)min=Math.min(min,m[1]*g[i]+m[5]*g[i+1]+m[9]*g[i+2]+m[13]);
   assert.ok(min>=.035-1e-8,`die cuts floor at frame ${tick}: ${min}`);
  }
 }
});
test('finished animation and an idle scene have identical die transforms',()=>{
 const end=scene.scene([3,4,5],motion.frame('sicbo',{},null,1).dice),idle=scene.scene([3,4,5],null);
 assert.deepEqual(end.draws,idle.draws);
});

test('rerenders reuse one graphics context and restore the scene after context loss',()=>{
 const vm=require('node:vm'),fs=require('node:fs');let contexts=0,draws=0,observer;
 const callbacks={},classList={add(){},remove(){}};
 const gl=new Proxy({getShaderParameter:()=>true,getProgramParameter:()=>true,drawArrays:()=>draws++},{get:(obj,key)=>key in obj?obj[key]:(()=>1)});
 const canvas={parentElement:null,setAttribute(){},addEventListener:(name,fn)=>callbacks[name]=fn,getBoundingClientRect:()=>({width:320,height:272}),getContext:()=>{contexts++;return gl;}};
 const ctx=vm.createContext({Float32Array,devicePixelRatio:2,document:{createElement:()=>canvas},ResizeObserver:class{constructor(fn){observer=fn;}observe(){}}});
 vm.runInContext(fs.readFileSync('public/sicbo-scene.js','utf8'),ctx);
 const host=()=>({classList,appendChild(c){c.parentElement=this;}}),a=host(),b=host();
 assert.equal(ctx.SicboScene.render(a,[3,4,5],null),true);
 assert.equal(ctx.SicboScene.render(b,[5,5,1],null),true);assert.equal(contexts,1);assert.equal(canvas.parentElement,b);assert.equal(draws,10);
 callbacks.webglcontextlost({preventDefault(){}});assert.equal(canvas.hidden,true);
 assert.equal(ctx.SicboScene.render(b,[5,5,1],null),false);
 callbacks.webglcontextrestored();assert.equal(canvas.hidden,false);assert.equal(contexts,1);assert.equal(draws,15);
 observer();assert.equal(draws,20);assert.equal(canvas.width,560);
});
