'use strict';
// Small fixed-step contact solver. Server count limits toppling; contacts choose the pins.
(function(root){
 const R=.42,START=5.8,DURATION=4600,DT=1/120,EDGE=-8.4,PIT=-1.1;
 const rack=[[-.9,-4.95],[-.3,-4.95],[.3,-4.95],[.9,-4.95],[-.6,-4.25],[0,-4.25],[.6,-4.25],[-.3,-3.55],[.3,-3.55],[0,-2.85]];
 const profile=[[.12,0],[.153,.025],[.18,.12],[.2,.26],[.186,.37],[.15,.48],[.095,.63],[.063,.76],[.063,.87],[.095,.97],[.105,1.04],[.089,1.1],[.041,1.135],[0,1.14]];
 function sampleProfile(t){const i=Math.min(profile.length-2,Math.floor(t)),u=t-i,p0=profile[Math.max(0,i-1)],p1=profile[i],p2=profile[i+1],p3=profile[Math.min(profile.length-1,i+2)];return [0,1].map(k=>.5*((2*p1[k])+(-p0[k]+p2[k])*u+(2*p0[k]-5*p1[k]+4*p2[k]-p3[k])*u*u+(-p0[k]+3*p1[k]-3*p2[k]+p3[k])*u*u*u));}
 const supportProfile=Array.from({length:79},(_,i)=>sampleProfile(i/78*(profile.length-1)));
 const shape=[[.20,.18],[.36,.25],[.66,.17],[1.02,.095],[1.30,.13]],cache=new Map();
 const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
 const identity=()=>[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
 function multiply(a,b){const c=Array(16).fill(0);for(let j=0;j<4;j++)for(let i=0;i<4;i++)for(let k=0;k<4;k++)c[j*4+i]+=a[k*4+i]*b[j*4+k];return c;}
 function rotation(x,z,angle){const len=Math.hypot(x,z)||1; x/=len;z/=len;const c=Math.cos(angle),s=Math.sin(angle),v=1-c;return [x*x*v+c,z*s,x*z*v,0,-z*s,c,x*s,0,x*z*v,-x*s,z*z*v+c,0,0,0,0,1];}
 function count(info){const d=info?.detail;return Number.isInteger(d?.count)?clamp(d.count,0,10):Array.isArray(d?.fallen)?d.fallen.filter(Boolean).length:10;}
 function support(theta){const sin=Math.sin(theta),cos=Math.cos(theta);return Math.max(0,...shape.map(([y,r])=>r-y*cos),...supportProfile.map(([r,y])=>1.25*(r*sin-y*cos)));}
 function spheres(p){const sin=Math.sin(p.angle),cos=Math.cos(p.angle),height=p.y??support(p.angle);return shape.map(([y,r])=>({x:p.x+p.dirX*y*sin,y:height+y*cos,z:p.z+p.dirZ*y*sin,r}));}
 function simulate(target){
  const bodies=rack.map(([x,z],i)=>({id:i,x,y:0,z,vx:0,vz:0,angle:0,omega:0,dirX:0,dirZ:-1,active:false,source:null,hitTime:null,landed:false}));
  const ball={x:0,y:R,z:START,vx:target?0:.95,vz:-5.25,vy:0,rotation:identity(),travel:0};
  const frames=[],events=[];let activated=0,time=0;
  function activate(p,nx,nz,source){if(p.active||activated>=target||(source==='ball'&&p.id!==9))return false;if(activated===0&&p.id!==9)return false;
   const len=Math.hypot(nx,nz)||1;p.active=true;p.source=source;p.hitTime=time;p.dirX=nx/len;p.dirZ=nz/len;p.omega=2.25;p.angle=.018;p.y=support(p.angle);activated++;events.push({type:source==='ball'?'head':'pin',pin:p.id,source,time,energy:1});return true;
  }
  function snapshot(){return {x:ball.x,y:ball.y,z:ball.z,travel:ball.travel,roll:-ball.travel/R,orientation:ball.rotation.slice(),visible:true,speed:Math.hypot(ball.vx,ball.vz),inPit:ball.z<EDGE,pins:bodies.map(p=>({x:p.x,y:p.y,z:p.z,angle:p.angle,dirX:p.dirX,dirZ:p.dirZ,fall:p.active?clamp(p.angle/(Math.PI/2),0,1):0,active:p.active,source:p.source,hitTime:p.hitTime}))};}
  frames.push(snapshot());
  for(let step=1;step<=Math.ceil(DURATION/1000/DT);step++){
   time=step*DT;const oldX=ball.x,oldZ=ball.z;
   if(time>.12){
    if(!target&&ball.x>=1.82){ball.x=1.82;ball.vx=0;}
    const drag=ball.z<EDGE?.996:(activated?.9968:.9996);ball.vx*=drag;ball.vz*=drag;
    ball.x+=ball.vx*DT;ball.z+=ball.vz*DT;
    if(ball.z<EDGE){ball.vy-=9.81*DT;ball.y=Math.max(PIT+R,ball.y+ball.vy*DT);if(ball.y===PIT+R){ball.vy=0;ball.vx*=.9;ball.vz*=.9;}if(ball.z<EDGE-1.25+R){ball.z=EDGE-1.25+R;ball.vz=Math.max(0,-ball.vz*.08);}}
    else ball.y=R-(!target?.16*clamp((ball.x-1.55)/.27,0,1):0);
    if(target){ball.x=clamp(ball.x,-1.48+R,1.48-R);}
   }
   for(const p of bodies)if(p.active){
    if(p.angle<Math.PI/2){p.omega+=6.5*Math.sin(p.angle+.18)*DT;p.angle=Math.min(Math.PI/2,p.angle+p.omega*DT);p.y=support(p.angle);if(p.angle===Math.PI/2&&!p.landed){p.landed=true;events.push({type:'land',pin:p.id,time,energy:.45});p.omega=0;}}
    p.x+=p.vx*DT;p.z+=p.vz*DT;p.vx*=.962;p.vz*=.962;
   }
   // Resolve contacts several times per step to prevent tunnelling through a narrow rack.
   for(let iteration=0;iteration<5;iteration++){
    for(const p of bodies){
     let hit=null;for(const c of spheres(p)){const dx=c.x-ball.x,dy=c.y-ball.y,dz=c.z-ball.z,dist=Math.hypot(dx,dy,dz),over=R+c.r-dist;if(over>0&&(!hit||over>hit.over))hit={dx,dy,dz,dist,over};}
     if(!hit)continue;const h=hit,len=Math.hypot(h.dx,h.dz)||1,nx=h.dx/len,nz=h.dz/len;
     if(time>.12)activate(p,nx,nz,'ball');
     const pinInv=p.active?.72:0,ballInv=.17,total=pinInv+ballInv,correction=h.over*.75;
     ball.x-=nx*correction*ballInv/total;ball.z-=nz*correction*ballInv/total;
     if(p.active){p.x+=nx*correction*pinInv/total;p.z+=nz*correction*pinInv/total;}
     const approach=(ball.vx-p.vx)*nx+(ball.vz-p.vz)*nz;
     if(approach>0){const impulse=approach*1.12/total;ball.vx-=impulse*ballInv*nx;ball.vz-=impulse*ballInv*nz;if(p.active){p.vx+=impulse*pinInv*nx;p.vz+=impulse*pinInv*nz;}}
    }
    for(let i=0;i<10;i++)for(let j=i+1;j<10;j++){
     const a=bodies[i],b=bodies[j];if(!a.active&&!b.active)continue;
     let hit=null;for(const ca of spheres(a))for(const cb of spheres(b)){const dx=cb.x-ca.x,dy=cb.y-ca.y,dz=cb.z-ca.z,dist=Math.hypot(dx,dy,dz),over=ca.r+cb.r-dist;if(over>0&&(!hit||over>hit.over))hit={dx,dz,over};}
     if(!hit)continue;const len=Math.hypot(hit.dx,hit.dz)||1,nx=hit.dx/len,nz=hit.dz/len;
     if(a.active&&!b.active)activate(b,nx,nz,a.id);else if(b.active&&!a.active)activate(a,-nx,-nz,b.id);
     const ia=a.active?1:0,ib=b.active?1:0,total=ia+ib;if(!total)continue;
     const correction=hit.over*.54;a.x-=nx*correction*ia/total;a.z-=nz*correction*ia/total;b.x+=nx*correction*ib/total;b.z+=nz*correction*ib/total;
     const approach=(a.vx-b.vx)*nx+(a.vz-b.vz)*nz;
     if(approach>0){const impulse=approach*1.05/total;a.vx-=impulse*nx*ia;a.vz-=impulse*nz*ia;b.vx+=impulse*nx*ib;b.vz+=impulse*nz*ib;}
    }
    for(const p of bodies)if(p.active){const x=clamp(p.x,-1.25,1.25),z=Math.max(-5.8,p.z);if(x!==p.x)p.vx*=-.12;if(z!==p.z)p.vz*=-.12;p.x=x;p.z=z;}
   }
   // Final sphere projection keeps the visible ball outside every pin collider.
   for(let pass=0;pass<5;pass++)for(const p of bodies)for(const c of spheres(p)){
    const dy=c.y-ball.y,reach=Math.sqrt(Math.max(0,(R+c.r)**2-dy*dy)),dx=ball.x-c.x,dz=ball.z-c.z,len=Math.hypot(dx,dz);
    if(reach>len+.0001){const nx=len?dx/len:0,nz=len?dz/len:1,correction=reach-len+.0001;ball.x+=nx*correction;ball.z+=nz*correction;const inward=ball.vx*nx+ball.vz*nz;if(inward<0){ball.vx-=inward*nx;ball.vz-=inward*nz;}}
   }
   if(ball.z>=EDGE&&target)ball.y=R;
   const dx=ball.x-oldX,dz=ball.z-oldZ,distance=Math.hypot(dx,dz);ball.travel+=distance;
   if(distance>1e-10)ball.rotation=multiply(rotation(dz,-dx,distance/R),ball.rotation);
   frames.push(snapshot());
  }
  return {frames,events,count:activated};
 }
 function timeline(info){const n=count(info);if(!cache.has(n))cache.set(n,simulate(n));return cache.get(n);}
 function frame(info,t){const frames=timeline(info).frames;return frames[Math.min(frames.length-1,Math.floor(clamp(t,0,1)*(frames.length-1)))];}
 const api={frame,timeline,count,rack,R,START,DURATION,EDGE,PIT,spheres,support,profile,sampleProfile};if(typeof module==='object'&&module.exports)module.exports=api;else root.BowlingPhysics=api;
})(globalThis);
