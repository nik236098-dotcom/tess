'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const s=require('../public/bowling-scene');
const strike={detail:{count:10,fallen:Array(10).fill(true)}};
test('the solid ball rotates one radian per radius travelled, with no sliding',()=>{
 for(let i=0;i<=100;i++){
  const f=s.frame(strike,i/100);assert.ok(Math.abs(f.roll-(f.z-s.START)/s.R)<1e-10);
  assert.ok(Math.abs(f.orientation[5]-Math.cos(f.roll))<1e-10);
  assert.ok(Math.abs(f.orientation[6]-Math.sin(f.roll))<1e-10);
  if(f.z>=-5.8)assert.equal(f.y,s.R);
 }
});
test('three openings remove the sphere surface and include recessed well geometry',()=>{
 assert.equal(s.holes.length,3);const h=Math.sqrt(s.R*s.R-.078*.078);
 for(let i=0;i<s.geometry.ball.length;i+=6){const p=s.geometry.ball.slice(i,i+3);for(const n of s.holes)assert.ok(p.reduce((v,x,k)=>v+x*n[k],0)<=h+1e-9);}
 assert.ok(s.geometry.well.length>1000);
 assert.ok(s.geometry.well.some((_,i,a)=>i%6===0&&Math.hypot(a[i],a[i+1],a[i+2])<s.R-.12));
 for(const data of Object.values(s.geometry)){assert.equal(data.length%18,0);assert.ok(data.every(Number.isFinite));}
});
test('a zero result rolls into the gutter and misses every pin',()=>{
 const info={detail:{count:0,fallen:Array(10).fill(false)}};
 for(let i=0;i<=100;i++){const f=s.frame(info,i/100);assert.ok(f.pins.every(p=>p.fall===0));if(f.z<0){assert.ok(Math.abs(f.x-1.82)<1e-12);for(const [x,z]of s.pins)assert.ok(Math.hypot(f.x-x,f.z-z)>s.R+.25);}}
});
test('the final standing pins match the server; no pin sinks into the lane while falling',()=>{
 for(const mask of [0,1,341,512,1023]){
  const info={detail:{fallen:Array.from({length:10},(_,i)=>Boolean(mask&(1<<i)))}};
  assert.deepEqual(s.frame(info,1).pins.map(p=>p.fall===1),info.detail.fallen);
 }
 for(let i=0;i<=100;i+=2)for(const c of s.scene(strike,i/100,.9).calls.filter(c=>c.mesh==='pin'&&!c.mirror)){
  const m=c.model;for(let n=0;n<s.geometry.pin.length;n+=6){const y=m[1]*s.geometry.pin[n]+m[5]*s.geometry.pin[n+1]+m[9]*s.geometry.pin[n+2]+m[13];assert.ok(y>=-.002,'pin intersects the lane');}
 }
});
test('the renderer waits for its texture, reuses the canvas and recovers after context loss',()=>{
 let contexts=0,draws=0,image;const callbacks={};
 const gl=new Proxy({getShaderParameter:()=>true,getProgramParameter:()=>true,drawArrays:()=>draws++},{get:(obj,key)=>key in obj?obj[key]:(()=>1)});
 const canvas={isConnected:true,parentElement:null,setAttribute(){},addEventListener:(k,v)=>callbacks[k]=v,getBoundingClientRect:()=>({width:360,height:400}),getContext:()=>{contexts++;return gl;}};
 const ctx=vm.createContext({Float32Array,Event:class{},devicePixelRatio:2,document:{createElement:()=>canvas},Image:class{constructor(){image=this;}},ResizeObserver:class{observe(){}}});
 vm.runInContext(fs.readFileSync('public/bowling-scene.js','utf8'),ctx);
 const host=()=>({dataset:{},querySelector:()=>({}),classList:{toggle(){}},dispatchEvent(){},appendChild(c){c.parentElement=this;}}),a=host(),b=host();
 assert.equal(ctx.BowlingScene.render(a,strike,0),false);assert.equal(ctx.BowlingScene.ready(),false);assert.equal(draws,0);
 image.onload();assert.equal(ctx.BowlingScene.ready(),true);assert.ok(draws>0);const before=draws;
 assert.equal(ctx.BowlingScene.render(b,strike,.3),true);assert.equal(canvas.parentElement,b);assert.equal(contexts,1);assert.ok(draws>before);
 callbacks.webglcontextlost({preventDefault(){}});assert.equal(ctx.BowlingScene.ready(),false);assert.equal(b.dataset.ready,'false');
 callbacks.webglcontextrestored();assert.equal(ctx.BowlingScene.ready(),true);assert.equal(b.dataset.ready,'true');assert.equal(contexts,1);assert.equal(canvas.width,630);
});
