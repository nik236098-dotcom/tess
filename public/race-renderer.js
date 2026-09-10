'use strict';
/* Native 3D geometry, projected onto a canvas. Tyres roll by distance/radius;
   only the sprung body pitches and heaves. No translated car image. */
(function(root){
 const R=.34,TRAVEL=50,FINISH=8-TRAVEL-1.97,LANE=2.7;
 const sub=(a,b)=>a.map((v,i)=>v-b[i]),dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
 const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
 const unit=a=>{const n=Math.hypot(...a)||1;return a.map(v=>v/n);};
 const light=unit([-3,8,4]);
 function motion(frame,index){
  const car=frame.cars[index],travel=car.distance*TRAVEL;
  const speed=car.speed||0,acceleration=car.acceleration||0;
  return {x:(index-1.5)*LANE,z:8-travel,travel,wheelAngle:-travel/R,
   heave:Math.sin(travel*3.1+index)*.013*speed,
   pitch:Math.max(-.032,Math.min(.032,acceleration*.009)),
   roll:Math.sin(travel*1.2+index)*.008*speed,braking:acceleration<-.12&&speed>.03};
 }
 function draw(ctx,width,height,frame,selected,colors){
  const cars=frame.cars.map((_,i)=>motion(frame,i)),follow=cars.reduce((s,c)=>s+c.travel,0)/4;
  const eye=[4.5,8,24-follow],target=[0,0,8-follow],forward=unit(sub(target,eye));
  const right=unit(cross(forward,[0,1,0])),up=cross(right,forward),focal=Math.min(width*1.22,height*1.6);
  const camera=p=>{const v=sub(p,eye);return [dot(v,right),dot(v,up),dot(v,forward)];};
  const project=p=>[width/2+p[0]/p[2]*focal,height*.54-p[1]/p[2]*focal];
  function projected(points){
   const p=points.map(camera),out=[];
   // Clip at the camera instead of dropping a road segment as it passes under it.
   for(let i=0;i<p.length;i++){const a=p[i],b=p[(i+1)%p.length],inside=a[2]>=.5;
    if(inside)out.push(a);if(inside!==(b[2]>=.5)){const t=(.5-a[2])/(b[2]-a[2]);out.push(a.map((v,k)=>v+(b[k]-v)*t));}}
   return out.map(project);
  }
  const color=(hex,n)=>{const v=parseInt(hex.slice(1),16);return `rgb(${[v>>16,(v>>8)&255,v&255].map(c=>Math.round(Math.max(0,Math.min(255,c*n)))).join(',')})`;};
  function polygon(points,fill,lit=false){
   const p=projected(points);if(p.length<3)return;
   ctx.beginPath();p.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();
   if(lit){const n=unit(cross(sub(points[1],points[0]),sub(points[2],points[0])));fill=color(fill,.55+.45*Math.abs(dot(n,light)));}
   ctx.fillStyle=fill;ctx.fill();
   if(lit){ctx.strokeStyle=fill;ctx.lineWidth=.35;ctx.stroke();}
  }
  const ground=(x,z,w,l,fill)=>polygon([[x,0,z],[x+w,0,z],[x+w,0,z+l],[x,0,z+l]],fill);
  ctx.clearRect(0,0,width,height);
  // Asphalt, rumble strips and lane paint all live in fixed world coordinates.
  ground(-5.7,-78,11.4,113,'#23273c');
  for(let z=-78;z<35;z+=2){ground(-5.92,z,.22,2,z%4?'#938bad':'#3b3550');ground(5.7,z,.22,2,z%4?'#938bad':'#3b3550');}
  for(let z=-78;z<35;z+=4)for(const x of [-2.7,0,2.7])ground(x-.025,z,.05,1.8,'#72778e');
  // One finish band. Its near edge is exactly the physical crossing plane.
  for(let row=0;row<2;row++)for(let col=0;col<20;col++)ground(-5.7+col*.57,FINISH-(row+1)*.57,.57,.57,(row+col)%2?'#2b293c':'#e2dfef');
  const faces=[];
  const face=(points,fill,lit=true,cull=false)=>{
   const normal=unit(cross(sub(points[1],points[0]),sub(points[2],points[0])));
   if(cull&&dot(normal,sub(eye,points[0]))>=0)return;
   const p=points.map(camera);if(p.every(v=>v[2]<.5))return;
   faces.push({screen:p.every(v=>v[2]>=.5)?p.map(project):projected(points),fill:lit?color(fill,.55+.45*Math.abs(dot(normal,light))):fill,lit,depth:p.reduce((sum,v)=>sum+v[2],0)/p.length});
  };
  function box(x,y,z,w,h,l,fill,transform=p=>p){
   const a=[x-w/2,x+w/2],b=[y-h/2,y+h/2],c=[z-l/2,z+l/2];
   const p=[ [a[0],b[0],c[0]],[a[1],b[0],c[0]],[a[1],b[1],c[0]],[a[0],b[1],c[0]], [a[0],b[0],c[1]],[a[1],b[0],c[1]],[a[1],b[1],c[1]],[a[0],b[1],c[1]] ].map(transform);
   for(const ids of [[0,1,2,3],[5,4,7,6],[1,5,6,2],[4,0,3,7],[3,2,6,7],[4,5,1,0]])face(ids.map(i=>p[i]),fill,true,true);
  }
  // Separate short poles outside the asphalt, with no second crossbar.
  for(const x of [-6.15,6.15]){box(x,.85,FINISH,.06,1.7,.06,'#a899c3');
   for(let r=0;r<3;r++)for(let c=0;c<4;c++)face([[x,1.65-r*.13,FINISH-c*.15],[x,1.65-r*.13,FINISH-c*.15-.15],[x,1.52-r*.13,FINISH-c*.15-.15],[x,1.52-r*.13,FINISH-c*.15]],(r+c)%2?'#383043':'#ebe3f4');}
  for(let i=0;i<4;i++){
   const car=cars[i],paint=colors[i];
   const chassis=p=>[p[0]+car.x,p[1],p[2]+car.z];
   const body=p=>{
    const y=p[1]-.34,z=p[2],x=p[0],cp=Math.cos(car.pitch),sp=Math.sin(car.pitch),cr=Math.cos(car.roll),sr=Math.sin(car.roll);
    const py=y*cp-z*sp,pz=y*sp+z*cp;
    return [x*cr-py*sr+car.x,x*sr+py*cr+.34+car.heave,pz+car.z];
   };
   polygon(Array.from({length:24},(_,j)=>[car.x+Math.cos(j/24*Math.PI*2)*1.04,.012,car.z+Math.sin(j/24*Math.PI*2)*2.08]),'#080b1759');
   // Each tyre is a cylinder with a rotating tread and five separate rim spokes.
   for(const x of [-.91,.91])for(const z of [-1.14,1.12]){
    const point=(side,a,r=R)=>chassis([x+side*.12,R+Math.sin(a)*r,z+Math.cos(a)*r]);
    for(let j=0;j<18;j++){const a=j/18*Math.PI*2+car.wheelAngle,b=(j+1)/18*Math.PI*2+car.wheelAngle;
     if(Math.sin((a+b)/2)*(eye[1]-R)+Math.cos((a+b)/2)*(eye[2]-car.z-z)>0)face([point(-1,a),point(1,a),point(1,b),point(-1,b)],j%3?'#151720':'#373945');}
    for(const side of [eye[0]>car.x+x?1:-1]){
     face(Array.from({length:18},(_,j)=>point(side,j/18*Math.PI*2)), '#151620');
     face(Array.from({length:18},(_,j)=>point(side,j/18*Math.PI*2,.235)), '#535764');
     face(Array.from({length:18},(_,j)=>point(side,j/18*Math.PI*2,.195)), '#1b1f2b');
     const center=point(side,0,0);
     for(let j=0;j<5;j++){const a=j/5*Math.PI*2+car.wheelAngle;face([center,point(side,a-.14,.215),point(side,a+.14,.215)],'#d4d6e0');}
    }
   }
   // Bevelled body shell, cabin, windows, rear wing and real lamp surfaces.
   const ring=(y,w,front,rear)=>[[-w+.16,y,front],[w-.16,y,front],[w,y,front+.23],[w,y,rear-.2],[w-.12,y,rear],[-w+.12,y,rear],[-w,y,rear-.2],[-w,y,front+.23]];
   const rings=[ring(.33,.79,-1.97,1.81),ring(.58,.9,-1.91,1.8),ring(.76,.79,-1.77,1.61)];
   for(let r=0;r<2;r++)for(let j=0;j<8;j++)face([rings[r][j],rings[r][(j+1)%8],rings[r+1][(j+1)%8],rings[r+1][j]].map(body),r?paint:'#2b2e40',true,true);
   face(rings[2].map(body),paint,true,true);
   const bottom=[[-.71,.77,-.79],[.71,.77,-.79],[.72,.77,1.08],[-.72,.77,1.08]],top=[[-.56,1.2,-.25],[.56,1.2,-.25],[.57,1.2,.63],[-.57,1.2,.63]];
   for(let j=0;j<4;j++)face([bottom[j],bottom[(j+1)%4],top[(j+1)%4],top[j]].map(body),'#293d56',true,true);
   face(top.map(body),paint,true,true);
   for(const x of [-.13,.13]){box(x,.771,-1.24,.095,.006,.98,'#e5e4f2',body);box(x,1.205,.19,.095,.006,.83,'#e5e4f2',body);box(x,.773,1.32,.095,.006,.4,'#e5e4f2',body);}
   for(const x of [-.67,.67]){box(x,.965,.25,.038,.39,.055,paint,body);box(x*1.27,.85,-.45,.2,.09,.18,paint,body);}
   for(const x of [-.5,.5]){
    box(x,.54,-1.927,.37,.08,.028,'#d3e9ff',body);
    box(x,.56,1.807,.43,.07,.018,car.braking?'#ff495e':'#963249',body);
    box(x,.88,1.46,.06,.25,.1,'#252733',body);
   }
   box(0,1.01,1.47,1.86,.075,.29,paint,body);
   box(0,.48,1.82,.7,.12,.04,'#121721',body);
  }
  faces.sort((a,b)=>b.depth-a.depth);for(const f of faces){
   if(f.screen.length<3)continue;ctx.beginPath();f.screen.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.fillStyle=f.fill;ctx.fill();
   if(f.lit){ctx.strokeStyle=f.fill;ctx.lineWidth=.35;ctx.stroke();}
  }
  for(let i=0;i<4;i++){
   const c=cars[i],v=camera([c.x,0,c.z+2.55]);if(v[2]<.5)continue;const [x,y]=project(v);
   ctx.fillStyle=i===selected?'#8e78e2':'#17192c';ctx.beginPath();if(ctx.roundRect)ctx.roundRect(x-11,y-9,22,18,6);else ctx.rect(x-11,y-9,22,18);ctx.fill();ctx.strokeStyle=colors[i];ctx.lineWidth=1;ctx.stroke();ctx.fillStyle='#fff';ctx.font='700 11px Arial';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(String(i+1),x,y+.5);
  }
  // Countdown is independent of the moving world and never covers the controls.
  if(frame.countdown){ctx.fillStyle='#eee7ff';ctx.font='800 46px Arial';ctx.textAlign='center';ctx.fillText(String(frame.countdown),width/2,height*.38);}
 }
 let canvas,ctx,observer,last;
 function redraw(){if(!canvas||!last)return;const width=canvas.clientWidth,height=canvas.clientHeight;if(!width||!height)return;const dpr=Math.min(2,root.devicePixelRatio||1);if(canvas.width!==Math.round(width*dpr)||canvas.height!==Math.round(height*dpr)){canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);}ctx.setTransform(dpr,0,0,dpr,0,0);draw(ctx,width,height,...last);}
 function render(host,frame,selected,colors){
  if(!host)return false;
  if(!canvas){canvas=root.document.createElement('canvas');canvas.className='rc-canvas';canvas.setAttribute('role','img');ctx=canvas.getContext('2d');if(!ctx){canvas=null;return false;}if(root.ResizeObserver){observer=new root.ResizeObserver(redraw);observer.observe(canvas);}}
  if(canvas.parentNode!==host)host.appendChild(canvas);canvas.setAttribute('aria-label',`Четыре объёмные машины на трассе. Выбрана машина ${selected+1}.`);
  last=[frame,selected,colors];redraw();return true;
 }
 const api={render,motion,geometry:{wheelRadius:R,travel:TRAVEL,finish:FINISH,nose:1.97,start:8}};
 if(typeof module==='object'&&module.exports)module.exports=api;else root.RaceRenderer=api;
})(globalThis);
