'use strict';
/* Real meshes, drilled ball geometry and distance-driven rolling. No moving sprites. */
(function(root){
 const physics=typeof module==='object'&&module.exports?require('./bowling-physics'):root.BowlingPhysics;
 const {R,START,DURATION}=physics,END=-6.7,pins=physics.rack;
 const clamp=n=>Math.max(0,Math.min(1,n)),phase=(t,a,b)=>clamp((t-a)/(b-a));
 const sub=(a,b)=>a.map((v,i)=>v-b[i]),dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0),cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
 const unit=a=>{const l=Math.hypot(...a)||1;return a.map(v=>v/l);};
 const identity=()=>[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
 function mul(a,b){const c=Array(16).fill(0);for(let j=0;j<4;j++)for(let i=0;i<4;i++)for(let k=0;k<4;k++)c[j*4+i]+=a[k*4+i]*b[j*4+k];return c;}
 function rotate(axis,t){const [x,y,z]=unit(axis),c=Math.cos(t),s=Math.sin(t),v=1-c;return [x*x*v+c,y*x*v+z*s,z*x*v-y*s,0,x*y*v-z*s,y*y*v+c,z*y*v+x*s,0,x*z*v+y*s,y*z*v-x*s,z*z*v+c,0,0,0,0,1];}
 function model(x,y,z,sx=1,sy=sx,sz=sx,rotation=identity()){const m=rotation.slice();for(let i=0;i<3;i++){m[i]*=sx;m[4+i]*=sy;m[8+i]*=sz;}m[12]=x;m[13]=y;m[14]=z;return m;}
 const holes=[[-.25,.6,.76],[.19,.71,.68],[.07,.29,.95]].map(unit);
 const frame=(info,t)=>physics.frame(info,t);
 // Clip the sphere at each drill opening; bevels, inner walls and well bottoms are meshes.
 function ballGeometry(){
  const shell=[],well=[],hr=.078,h=Math.sqrt(R*R-hr*hr),slices=96,rows=64;
  const vertex=(i,j)=>{const a=i/slices*Math.PI*2,b=j/rows*Math.PI;return [R*Math.sin(b)*Math.cos(a),R*Math.cos(b),R*Math.sin(b)*Math.sin(a)];};
  function clip(poly,n){const out=[];for(let i=0;i<poly.length;i++){const a=poly[i],b=poly[(i+1)%poly.length],da=dot(a,n)-h,db=dot(b,n)-h;if(da<=0)out.push(a);if((da<=0)!==(db<=0)){const t=da/(da-db);out.push(a.map((v,k)=>v+(b[k]-v)*t));}}return out;}
  for(let j=0;j<rows;j++)for(let i=0;i<slices;i++)for(const tri of [[vertex(i,j),vertex(i+1,j),vertex(i+1,j+1)],[vertex(i,j),vertex(i+1,j+1),vertex(i,j+1)]]){
   let p=tri;for(const n of holes){p=clip(p,n);if(!p.length)break;}for(let k=1;k<p.length-1;k++)for(const v of [p[0],p[k],p[k+1]])shell.push(...v,...unit(v));
  }
  for(const n of holes){const a=unit(cross(n,[0,1,0])),b=cross(n,a),rings=[[hr,h],[.067,h-.007],[.064,h-.035],[.064,h-.185],[0,h-.188]];
   const point=(r,i)=>{const t=i/48*Math.PI*2;return n.map((v,k)=>v*r[1]+r[0]*(a[k]*Math.cos(t)+b[k]*Math.sin(t)));};
   for(let j=0;j<rings.length-1;j++)for(let i=0;i<48;i++){
    const p=point(rings[j],i),q=point(rings[j],i+1),r=point(rings[j+1],i+1),s=point(rings[j+1],i),normal=unit(cross(sub(r,p),sub(q,p)));
    for(const v of [p,q,r,p,r,s])well.push(...v,...normal);
   }
  }
  return {ball:shell,well};
 }
 function lathe(){
  const profile=physics.profile,mesh=[],sample=physics.sampleProfile;
  const at=(i,j)=>{const t=j/78*(profile.length-1),[r,y]=sample(t),lo=sample(Math.max(0,t-.01)),hi=sample(Math.min(profile.length-1,t+.01)),a=i/48*2*Math.PI;return [r*Math.cos(a),y,r*Math.sin(a),...unit([(hi[1]-lo[1])*Math.cos(a),lo[0]-hi[0],(hi[1]-lo[1])*Math.sin(a)])];};
  for(let j=0;j<78;j++)for(let i=0;i<48;i++){const a=at(i,j),b=at(i+1,j),c=at(i+1,j+1),d=at(i,j+1);mesh.push(...a,...b,...c,...a,...c,...d);}return mesh;
 }
 function box(){const mesh=[],faces=[[[1,0,0],[1,-1,-1],[1,1,-1],[1,1,1],[1,-1,1]],[[-1,0,0],[-1,-1,1],[-1,1,1],[-1,1,-1],[-1,-1,-1]],[[0,1,0],[-1,1,-1],[-1,1,1],[1,1,1],[1,1,-1]],[[0,-1,0],[-1,-1,1],[-1,-1,-1],[1,-1,-1],[1,-1,1]],[[0,0,1],[1,-1,1],[1,1,1],[-1,1,1],[-1,-1,1]],[[0,0,-1],[-1,-1,-1],[-1,1,-1],[1,1,-1],[1,-1,-1]]];for(const [n,a,b,c,d]of faces)for(const v of [a,b,c,a,c,d])mesh.push(...v.map(x=>x*.5),...n);return mesh;}
 function gutter(){const mesh=[];const point=(i,z)=>{const a=i/32*Math.PI;return [-Math.cos(a)*.22,-Math.sin(a)*.18,z,...unit([-Math.cos(a),Math.sin(a),0])];};for(let i=0;i<32;i++)mesh.push(...point(i,-9),...point(i+1,-9),...point(i+1,11),...point(i,-9),...point(i+1,11),...point(i,11));return mesh;}
 const geometry={screen:[-1,-1,0,0,0,1,1,-1,0,0,0,1,1,1,0,0,0,1,-1,-1,0,0,0,1,1,1,0,0,0,1,-1,1,0,0,0,1],...ballGeometry(),pin:lathe(),box:box(),gutter:gutter(),floor:[-1,0,-1,0,1,0,1,0,-1,0,1,0,1,0,1,0,1,0,-1,0,-1,0,1,0,1,0,1,0,1,0,-1,0,1,0,1,0]};
 const eye=[0,4.1,11.9];
 function camera(aspect){const z=unit(sub(eye,[0,.08,-.1])),x=unit(cross([0,1,0],z)),y=cross(z,x),v=[x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1],f=1/Math.tan(41*Math.PI/360),near=.1,far=55;return mul([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)/(near-far),-1,0,0,2*far*near/(near-far),0],v);}
 const vertex=`attribute vec3 aPosition;attribute vec3 aNormal;uniform mat4 uModel;uniform mat4 uVP;uniform float uKind;varying vec3 vWorld;varying vec3 vNormal;varying vec3 vLocal;void main(){vec4 p=uModel*vec4(aPosition,1.);vWorld=p.xyz;vLocal=aPosition;vNormal=mat3(uModel)*aNormal;gl_Position=uKind>5.5?vec4(aPosition.xy,.9999,1.):uVP*p;}`;
 const fragment=`precision highp float;
 uniform sampler2D uBackdrop;uniform vec2 uResolution;uniform vec3 uEye,uColor,uBall;uniform vec3 uPins[10];uniform float uKind,uAlpha,uMirror;
 varying vec3 vWorld,vNormal,vLocal;
 float hash(float n){return fract(sin(n*127.1)*43758.5453);}
 void main(){
 vec3 plate=texture2D(uBackdrop,gl_FragCoord.xy/uResolution).rgb;
 if(uKind>5.5){gl_FragColor=vec4(plate,1.);return;}
 vec3 n=normalize(vNormal),base=uColor;float gloss=.5,shine=110.;
 if(uKind<.5){base=plate;gloss=.7;shine=160.; }else if(uKind<1.5){
  vec3 p=vLocal*14.;float w=sin(p.x+sin(p.z*1.4)+cos(p.y*1.6));float vein=sin(p.z*2.+sin(p.y*2.5)+w*2.5);
  base=mix(vec3(.018,.075,.27),vec3(.045,.27,.74),smoothstep(-.8,.9,w));base=mix(base,vec3(.13,.39,.77),pow(.5+.5*vein,8.)*.22);gloss=1.;shine=130.;
 }else if(uKind<2.5){base=vec3(.013,.021,.044);gloss=.13;}
 else if(uKind<3.5){base=vec3(.91,.94,.99);if((vLocal.y>.78&&vLocal.y<.825)||(vLocal.y>.865&&vLocal.y<.91))base=vec3(.8,.035,.075);gloss=.62;shine=130.;}
 else if(uKind>4.5){gl_FragColor=vec4(base,uAlpha);return;}
 vec3 v=normalize(uEye-vWorld),l=normalize(vec3(-2.8,6.5,4.)-vWorld),l2=normalize(vec3(3.,4.,-5.)-vWorld);
 float diffuse=max(dot(n,l),0.),fill=max(dot(n,l2),0.),spec=pow(max(dot(n,normalize(l+v)),0.),shine)+pow(max(dot(n,normalize(l2+v)),0.),shine)*.55;
 vec3 lit=base*(.27+.62*diffuse+.3*fill)+vec3(.88,.94,1.)*spec*gloss;
 float fresnel=pow(1.-max(dot(n,v),0.),4.);lit+=vec3(.08,.17,.34)*fresnel*gloss;
 if(uKind<.5){
  float shadow=1.;for(int i=0;i<10;i++){vec2 d=vWorld.xz-uPins[i].xz-vec2(.025,-.025);shadow*=1.-.38*exp(-dot(d,d)/.028);}
  vec2 d=vWorld.xz-uBall.xz;shadow*=1.-.67*exp(-dot(d,d)/.10);lit=plate*shadow;
 }
 if(uKind>.5&&uKind<1.5){vec3 r=reflect(-v,n);float panel=smoothstep(.5,.6,r.y)*(1.-smoothstep(.8,.9,r.y))*(1.-smoothstep(.15,.22,abs(r.x+.25)));lit+=vec3(.65,.79,1.)*panel*.55;}
 if(uKind>3.5&&uKind<4.5)lit=mix(lit,base*.55,.75);
 if(uMirror>.5)lit*=.8;
 gl_FragColor=vec4(uKind<.5?lit:pow(max(lit,vec3(0.)),vec3(.82)),uAlpha);
 }`;
 function scene(info,t,aspect){
  const f=frame(info,t),pinModels=f.pins.map(p=>model(p.x,p.y,p.z,1.25,1.25,1.25,rotate([p.dirZ,0,-p.dirX],p.angle))),ball=model(f.x,f.y,f.z,1,1,1,f.orientation),calls=[];
  const add=(mesh,m,kind,color=[.1,.16,.26],alpha=1,mirror=0)=>calls.push({mesh,model:m,kind,color,alpha,mirror});
  add('screen',identity(),6);
  // Draw mirrored meshes before the translucent varnished lane; the lane writes depth.
  const mirror=model(0,0,0,1,-1,1);
  for(const m of pinModels)add('pin',mul(mirror,m),3,[1,1,1],1,1);
  if(f.visible){add('ball',mul(mirror,ball),1,[1,1,1],1,1);add('well',mul(mirror,ball),2,[1,1,1],1,1);}
  add('floor',model(0,0,(11+physics.EDGE)/2,1.58,1,(11-physics.EDGE)/2),0,[1,1,1],.73);
  for(const side of [-1,1]){add('floor',model(side*1.82,-.16,(11+physics.EDGE)/2,.24,1,(11-physics.EDGE)/2),0,[1,1,1],1);add('floor',model(side*2.23,0,(11+physics.EDGE)/2,.18,1,(11-physics.EDGE)/2),0,[1,1,1],1);}
  // A real recessed collector, with floor and front lip occluding the ball below the lane.
  add('box',model(0,physics.PIT-.06,physics.EDGE-.7,4.25,.12,1.2),4,[.012,.019,.03]);
  add('box',model(0,-.55,physics.EDGE-.02,4.25,1.1,.055),4,[.033,.04,.06]);
  add('box',model(0,-.43,physics.EDGE-1.4,4.25,1.35,.12),4,[.012,.019,.03]);
  for(const x of [-2.12,2.12])add('box',model(x,-.52,physics.EDGE-.7,.10,1.15,1.2),4,[.015,.025,.04]);
  for(const m of pinModels)add('pin',m,3);
  if(f.visible){add('ball',ball,1);add('well',ball,2);}
  return {calls,camera:camera(aspect),ball:[f.x,f.y,f.z],pins:pinModels.flatMap(m=>[m[12],m[13],m[14]])};
 }
 let canvas,gl,program,buffers,loc,last,observer,texture,backdrop,imageReady=false,lost=false,failed=false;
 function compile(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;}
 function init(){program=gl.createProgram();const vs=compile(gl.VERTEX_SHADER,vertex),fs=compile(gl.FRAGMENT_SHADER,fragment);gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);gl.deleteShader(vs);gl.deleteShader(fs);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));buffers={};for(const [name,data]of Object.entries(geometry)){const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);buffers[name]={buffer,count:data.length/6};}loc={};for(const n of ['uBackdrop','uResolution','uModel','uVP','uEye','uColor','uKind','uAlpha','uMirror','uBall','uPins[0]'])loc[n]=gl.getUniformLocation(program,n);for(const n of ['aPosition','aNormal'])loc[n]=gl.getAttribLocation(program,n);gl.enable(gl.DEPTH_TEST);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.clearColor(.014,.025,.046,1);texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);if(imageReady)upload();lost=false;}
 function upload(){gl.bindTexture(gl.TEXTURE_2D,texture);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB,gl.RGB,gl.UNSIGNED_BYTE,backdrop);}
 function draw(){if(!gl||lost||!imageReady||!last||!canvas.isConnected)return;const rect=canvas.getBoundingClientRect();if(!rect.width||!rect.height)return;const dpr=Math.min(root.devicePixelRatio||1,1.75),w=Math.round(rect.width*dpr),h=Math.round(rect.height*dpr);if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}gl.viewport(0,0,w,h);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(program);gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,texture);gl.uniform1i(loc.uBackdrop,0);gl.uniform2f(loc.uResolution,w,h);const s=scene(last.info,last.t,w/h);gl.uniformMatrix4fv(loc.uVP,false,new Float32Array(s.camera));gl.uniform3fv(loc.uEye,eye);gl.uniform3fv(loc.uBall,s.ball);gl.uniform3fv(loc['uPins[0]'],s.pins);
  for(const c of s.calls){const b=buffers[c.mesh];gl.bindBuffer(gl.ARRAY_BUFFER,b.buffer);for(const [i,n]of ['aPosition','aNormal'].entries()){gl.enableVertexAttribArray(loc[n]);gl.vertexAttribPointer(loc[n],3,gl.FLOAT,false,24,i*12);}gl.uniformMatrix4fv(loc.uModel,false,new Float32Array(c.model));gl.uniform3fv(loc.uColor,c.color);gl.uniform1f(loc.uKind,c.kind);gl.uniform1f(loc.uAlpha,c.alpha);gl.uniform1f(loc.uMirror,c.mirror);gl.drawArrays(gl.TRIANGLES,0,b.count);}
 }
 function render(host,info,t){if(!host||failed)return false;last={info,t};try{
  if(!canvas){canvas=root.document.createElement('canvas');canvas.className='bw-webgl';canvas.setAttribute('aria-label','Объёмная дорожка, кегли и вращающийся шар');gl=canvas.getContext('webgl',{alpha:false,antialias:true,preserveDrawingBuffer:false});if(!gl){failed=true;return false;}init();backdrop=new root.Image();backdrop.onload=()=>{imageReady=true;upload();draw();hostState(!lost);};backdrop.onerror=()=>{failed=true;hostState(false);};backdrop.src='/img/bowling/lane.webp';canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();lost=true;hostState(false);});canvas.addEventListener('webglcontextrestored',()=>{try{init();draw();hostState(imageReady);}catch{failed=true;hostState(false);}});if(root.ResizeObserver){observer=new root.ResizeObserver(draw);observer.observe(canvas);}}
  if(canvas.parentElement!==host)host.appendChild(canvas);draw();hostState(!lost&&imageReady);return !lost&&imageReady;
 }catch(e){failed=true;if(root.console)root.console.error('Bowling renderer:',e);hostState(false);return false;}}
 function hostState(ready){const host=canvas?.parentElement;if(host){const message=host.querySelector('.bw-fallback');if(message)message.textContent=failed?'Не удалось загрузить 3D. Закрой и снова открой приложение.':lost?'Восстанавливаем 3D…':'Загружаем дорожку…';host.classList.toggle('is-rendered',ready);if(host.dataset.ready!==String(ready)){host.dataset.ready=String(ready);host.dispatchEvent(new root.Event('bowlingready',{bubbles:true}));}}}
 function ready(){return Boolean(gl&&imageReady&&!lost&&!failed);}
 function board(info,animating){const done=info?.phase==='done'&&!animating,count=done?info.detail?.count:null;return `<div class="bw-panel"><div class="bw-toolbar"><span>Один бросок · десять кеглей</span><button type="button" data-bw-sound aria-label="Звук боулинга" aria-pressed="${root.BowlingAudio?.isEnabled()!==false}">${root.BowlingAudio?.isEnabled()!==false?'Звук: вкл':'Звук: выкл'}</button></div><div class="bw-viewport"><p class="bw-fallback">Загружаем дорожку…</p></div><div class="bw-result" role="status" aria-live="polite"><div><small>Сбито кеглей</small><b>${done?count+' / 10':'— / 10'}</b></div><strong class="${done&&count===10?'is-strike':''}">${animating?'Шар на дорожке…':done?count===10?'СТРАЙК!':count===0?'Мимо':info.payout?'Есть попадание!':'Бросок завершён':'Готов к броску'}</strong></div></div><div class="bw-payouts" aria-label="Коэффициенты за сбитые кегли">${[[6,'0,5'],[7,'1'],[8,'3'],[9,'20'],[10,'443']].map(([n,m])=>`<div class="${done&&count===n?'is-active':''}"><small>${n===10?'Страйк':n+' кеглей'}</small><b>${m}×</b></div>`).join('')}</div>`;}
 const api={render,ready,board,frame,physics,scene,geometry,vertex,fragment,R,START,END,DURATION,pins,holes};if(typeof module==='object'&&module.exports)module.exports=api;else root.BowlingScene=api;
})(globalThis);
