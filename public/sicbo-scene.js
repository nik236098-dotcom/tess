'use strict';
/* One continuous rounded mesh per die. No DOM faces or CSS 3D flattening. */
(function(root){
 const vertex=`attribute vec3 aPosition;attribute vec3 aNormal;
 uniform mat4 uModel;uniform mat4 uViewProjection;
 varying vec3 vWorld;varying vec3 vNormal;varying vec3 vLocal;
 void main(){vec4 p=uModel*vec4(aPosition,1.0);vWorld=p.xyz;vLocal=aPosition;vNormal=mat3(uModel)*aNormal;gl_Position=uViewProjection*p;}`;
 const fragment=`precision highp float;
 uniform vec3 uEye;uniform vec3 uColor;uniform vec3 uPips;uniform mat4 uModel;
 uniform float uKind;uniform vec3 uDice[3];
 varying vec3 vWorld;varying vec3 vNormal;varying vec3 vLocal;
 float pipOn(float value,int i){
  if(value<1.5)return i==4?1.0:0.0;
  if(value<2.5)return i==0||i==8?1.0:0.0;
  if(value<3.5)return i==0||i==4||i==8?1.0:0.0;
  if(value<4.5)return i==0||i==2||i==6||i==8?1.0:0.0;
  if(value<5.5)return i==0||i==2||i==4||i==6||i==8?1.0:0.0;
  return i==0||i==2||i==3||i==5||i==6||i==8?1.0:0.0;
 }
 void main(){
  vec3 n=normalize(vNormal),color=uColor;float gloss=0.25,shine=48.0;
  if(uKind<0.5){
   vec3 q=abs(vLocal),tangent,bitangent;vec2 uv;float value;
   if(q.x>q.y&&q.x>q.z){uv=vLocal.zy;tangent=vec3(0,0,1);bitangent=vec3(0,1,0);value=vLocal.x>0.0?uPips.x:7.0-uPips.x;}
   else if(q.y>q.z){uv=vLocal.xz;tangent=vec3(1,0,0);bitangent=vec3(0,0,1);value=vLocal.y>0.0?uPips.y:7.0-uPips.y;}
   else{uv=vLocal.xy;tangent=vec3(1,0,0);bitangent=vec3(0,1,0);value=vLocal.z>0.0?uPips.z:7.0-uPips.z;}
   float nearest=2.0;vec2 delta=vec2(0);
   for(int i=0;i<9;i++){float x=mod(float(i),3.0)-1.0;float y=floor(float(i)/3.0)-1.0;vec2 d=uv-vec2(x,y)*0.238;float dist=length(d);if(pipOn(value,i)>0.5&&dist<nearest){nearest=dist;delta=d;}}
   float ink=1.0-smoothstep(0.079,0.088,nearest);
   color=mix(color,mix(vec3(0.13,0.062,0.19),vec3(0.026,0.009,0.049),smoothstep(0.015,0.088,nearest)),ink);
   vec3 dent=mat3(uModel)*(tangent*delta.x+bitangent*delta.y);
   n=normalize(n+dent*ink*7.0);gloss=mix(0.32,0.18,ink);shine=80.0;
  }
  vec3 l=normalize(vec3(-3.5,7.0,4.0)-vWorld),v=normalize(uEye-vWorld),h=normalize(l+v);
  float diffuse=max(dot(n,l),0.0),spec=pow(max(dot(n,h),0.0),shine)*gloss;
  float fill=max(dot(n,normalize(vec3(4,3,-5))),0.0);
  vec3 lit=color*(0.35+0.8*diffuse+0.24*fill)+vec3(1.0,0.91,0.87)*spec;
  if(uKind>0.5&&uKind<1.5){lit+=vec3(0.09,0.07,0.20)*smoothstep(0.32,0.46,vWorld.y);}
  if(uKind>1.5){
   float shadow=1.0;
   for(int i=0;i<3;i++){vec2 d=vWorld.xz-uDice[i].xz-vec2(0.5,-0.3)*uDice[i].y;float spread=0.42+uDice[i].y*0.18;shadow*=1.0-0.62*exp(-dot(d,d)/(spread*spread));}
   lit*=shadow;lit+=vec3(0.018,0.008,0.037)*max(0.0,1.0-length(vWorld.xz)*0.28);
  }
  gl_FragColor=vec4(pow(max(lit,vec3(0)),vec3(0.85)),1.0);
 }`;
 const sub=(a,b)=>a.map((x,i)=>x-b[i]),dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0);
 const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
 const normal=a=>{const n=Math.hypot(...a)||1;return a.map(x=>x/n);};
 const identity=()=>[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
 function multiply(a,b){const c=Array(16).fill(0);for(let col=0;col<4;col++)for(let row=0;row<4;row++)for(let k=0;k<4;k++)c[col*4+row]+=a[k*4+row]*b[col*4+k];return c;}
 function rotation(x,y,z){x*=Math.PI/180;y*=Math.PI/180;z*=Math.PI/180;const sx=Math.sin(x),cx=Math.cos(x),sy=Math.sin(y),cy=Math.cos(y),sz=Math.sin(z),cz=Math.cos(z);return multiply(multiply([1,0,0,0,0,cx,sx,0,0,-sx,cx,0,0,0,0,1],[cy,0,-sy,0,0,1,0,0,sy,0,cy,0,0,0,0,1]),[cz,sz,0,0,-sz,cz,0,0,0,0,1,0,0,0,0,1]);}
 const eye=[0,9.4,7.3];
 function camera(aspect){const z=normal(sub(eye,[0,0,0.15])),x=normal(cross([0,1,0],z)),y=cross(z,x),view=[x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1];const f=1/Math.tan(28*Math.PI/360),near=.1,far=40;return multiply([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)/(near-far),-1,0,0,2*far*near/(near-far),0],view);}
 function roundedDie(){const out=[],size=20,r=.16,b=.5-r;const maps=[(u,v)=>[.5,u,v],(u,v)=>[-.5,v,u],(u,v)=>[v,.5,u],(u,v)=>[u,-.5,v],(u,v)=>[u,v,.5],(u,v)=>[v,u,-.5]];for(const map of maps){const vertex=(u,v)=>{const q=map(u/size-.5,v/size-.5),c=q.map(n=>Math.max(-b,Math.min(b,n))),n=normal(sub(q,c));return [...c.map((a,i)=>a+r*n[i]),...n];};for(let y=0;y<size;y++)for(let x=0;x<size;x++){const a=vertex(x,y),b=vertex(x+1,y),c=vertex(x+1,y+1),d=vertex(x,y+1);out.push(...a,...b,...c,...a,...c,...d);}}return out;}
 function outline(){const corners=[[-1.6,-2.3],[1.6,-2.3],[3.05,-.55],[2.1,2.3],[-2.1,2.3],[-3.05,-.55]],out=[];for(let i=0;i<6;i++){const p=corners[(i+5)%6],q=corners[i],r=corners[(i+1)%6],a=q.map((v,k)=>v*.86+p[k]*.14),b=q.map((v,k)=>v*.86+r[k]*.14);for(let j=0;j<=8;j++){const t=j/8;out.push(q.map((v,k)=>(1-t)**2*a[k]+2*(1-t)*t*v+t*t*b[k]));}}return out;}
 function tray(){const path=outline(),rings=[[.99,-.23],[1.018,-.15],[1.025,.27],[1.014,.40],[.995,.455],[.923,.455],[.900,.39],[.865,.09],[.854,.035]],mesh=[],floor=[];const point=(r,i)=>[path[i][0]*r[0],r[1],path[i][1]*r[0]];for(let j=0;j<rings.length-1;j++)for(let i=0;i<path.length;i++){const next=(i+1)%path.length,a=point(rings[j],i),b=point(rings[j],next),c=point(rings[j+1],next),d=point(rings[j+1],i);const smooth=(r,k)=>normal(cross(sub(point(rings[Math.min(rings.length-1,r+1)],k),point(rings[Math.max(0,r-1)],k)),sub(point(rings[r],(k+1)%path.length),point(rings[r],(k+path.length-1)%path.length))));for(const [v,r,k] of [[a,j,i],[b,j,next],[c,j+1,next],[a,j,i],[c,j+1,next],[d,j+1,i]])mesh.push(...v,...smooth(r,k));}
  for(let i=0;i<path.length;i++)for(const p of [[0,.03,0],point(rings.at(-1),i),point(rings.at(-1),(i+1)%path.length)])floor.push(...p,0,1,0);return {mesh,floor};}
 const geometry={die:roundedDie(),...tray()};
 function scene(values,poses,aspect=1.18){
  const transforms=values.map((value,i)=>{const p=poses?.[i],rx=p?(p.rx+58):0,ry=[-14,18,-20][i]+(p?p.ry-26:0),rz=p?p.rz-[-10,12,-8][i]:0,m=rotation(rx,ry,rz);const support=.34*(Math.abs(m[1])+Math.abs(m[5])+Math.abs(m[9]))+.16;m[12]=[0,-1.26,1.27][i]+(p?.x||0)*.017;m[13]=.036+support+(p?.height||0)*.019;m[14]=[-1.08,1.03,.95][i]+(p?.y||0)*.012;return m;});
  const positions=transforms.flatMap(m=>[m[12],m[13],m[14]]);
  const draws=[{mesh:'floor',model:identity(),kind:2,color:[.105,.060,.18],pips:[1,1,1]},{mesh:'mesh',model:identity(),kind:1,color:[.27,.16,.54],pips:[1,1,1]},...values.map((value,i)=>({mesh:'die',model:transforms[i],kind:0,color:[.92,.87,.83],pips:[({1:2,2:3,3:1,4:2,5:1,6:3})[value],value,({1:3,2:1,3:2,4:1,5:3,6:2})[value]]}))];return {camera:camera(aspect),eye,positions,draws};
 }
 let canvas=null,gl=null,program=null,buffers=null,locations=null,last=null,observer=null,lost=false;
 function shader(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;}
 function initialize(){program=gl.createProgram();const vs=shader(gl.VERTEX_SHADER,vertex),fs=shader(gl.FRAGMENT_SHADER,fragment);gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);gl.deleteShader(vs);gl.deleteShader(fs);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));buffers={};for(const [key,data] of Object.entries(geometry)){const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);buffers[key]={buffer,count:data.length/6};}locations={};for(const name of ['uModel','uViewProjection','uEye','uColor','uPips','uKind','uDice[0]'])locations[name]=gl.getUniformLocation(program,name);locations.aPosition=gl.getAttribLocation(program,'aPosition');locations.aNormal=gl.getAttribLocation(program,'aNormal');gl.enable(gl.DEPTH_TEST);gl.clearColor(0,0,0,0);lost=false;}
 function draw(){if(!gl||lost||!last)return;const rect=canvas.getBoundingClientRect(),width=Math.max(1,Math.round(rect.width*Math.min(root.devicePixelRatio||1,1.75))),height=Math.max(1,Math.round(rect.height*Math.min(root.devicePixelRatio||1,1.75)));if(!rect.width||!rect.height)return;if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;}gl.viewport(0,0,width,height);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(program);const frame=scene(last.values,last.poses,width/height);gl.uniformMatrix4fv(locations.uViewProjection,false,new Float32Array(frame.camera));gl.uniform3fv(locations.uEye,frame.eye);gl.uniform3fv(locations['uDice[0]'],frame.positions);for(const call of frame.draws){const b=buffers[call.mesh];gl.bindBuffer(gl.ARRAY_BUFFER,b.buffer);gl.enableVertexAttribArray(locations.aPosition);gl.vertexAttribPointer(locations.aPosition,3,gl.FLOAT,false,24,0);gl.enableVertexAttribArray(locations.aNormal);gl.vertexAttribPointer(locations.aNormal,3,gl.FLOAT,false,24,12);gl.uniformMatrix4fv(locations.uModel,false,new Float32Array(call.model));gl.uniform3fv(locations.uColor,call.color);gl.uniform3fv(locations.uPips,call.pips);gl.uniform1f(locations.uKind,call.kind);gl.drawArrays(gl.TRIANGLES,0,b.count);}}
 function render(host,values,poses){if(!host||!root.document?.createElement)return false;last={values,poses};try{if(!canvas){canvas=root.document.createElement('canvas');canvas.className='sb-webgl';canvas.setAttribute('aria-hidden','true');gl=canvas.getContext('webgl',{alpha:true,antialias:true,premultipliedAlpha:false});if(!gl)return false;initialize();canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();lost=true;canvas.hidden=true;canvas.parentElement?.classList.remove('is-rendered');});canvas.addEventListener('webglcontextrestored',()=>{try{initialize();canvas.hidden=false;canvas.parentElement?.classList.add('is-rendered');draw();}catch{gl=null;}});if(root.ResizeObserver){observer=new root.ResizeObserver(draw);observer.observe(canvas);}}if(!gl||lost)return false;if(canvas.parentElement!==host)host.appendChild(canvas);draw();return true;}catch{gl=null;return false;}}
 const api={render,geometry,scene,vertex,fragment};if(typeof module==='object'&&module.exports)module.exports=api;else root.SicboScene=api;
})(globalThis);
