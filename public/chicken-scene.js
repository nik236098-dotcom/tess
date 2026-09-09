'use strict';
/* Articulated, resolution-independent game art. Outcomes come from the server. */
(function(root){
 const clamp=n=>Math.max(0,Math.min(1,n)),ease=n=>{n=clamp(n);return n*n*(3-2*n);};
 const range=(t,a,b)=>clamp((t-a)/(b-a));
 const laneWidth=108,crossingY=231;
 const laneX=(step,camera=0)=>step?182+(step-1)*laneWidth-camera:80-camera;
 const cameraAt=step=>Math.max(0,(step-1)*laneWidth);
 function pose(info,previous,t){
  t=clamp(t);const failed=info.last?.safe===false,step=info.step||0,target=step+(failed?1:0);
  const from=previous?.step??Math.max(0,target-1),walk=range(t,.12,.77),travel=ease(walk);
  const camera=cameraAt(from)+(cameraAt(target)-cameraAt(from))*travel;
  const start=laneX(from,camera),end=laneX(target,camera);
  const x=start+(end-start)*travel;
  // Two footfalls per lane. A planted foot travels backwards relative to the body.
  const stride=walk*2,weight=walk===0||walk===1?0:Math.sin(Math.PI*walk),leg=offset=>{
   const cycle=(stride+offset)%1,stance=cycle<.6;
   const u=stance?cycle/.6:(cycle-.6)/.4;
   return {x:(stance?9-18*u:-9+18*ease(u))*weight,y:stance?0:-8*Math.sin(u*Math.PI)*weight};
  };
  const impact=failed&&t>=.79,fall=failed?ease(range(t,.79,.97)):0;
  const carY=failed?-90+288*range(t,.24,.79)+252*range(t,.79,1):-90+560*range(t,0,.48);
  return {x,camera,target,walk,bodyY:weight?-1.8*Math.sin(stride*Math.PI*2)**2*weight:0,wing:weight?5*Math.sin(stride*Math.PI*2)*weight:0,
   near:leg(0),far:leg(.5),impact,fall,birdY:194+12*fall,birdAngle:76*fall,
   carX:laneX(target||1,camera),carY,carScale:.84+.32*clamp((carY+90)/440)};
 }
 function legPath(foot,near){
  const hip=near?5:-8,ankle=hip+foot.x,knee=hip-5+foot.x*.35,y=49+foot.y;
  return `M${hip} 29 Q${knee} 36 ${ankle} ${y} M${ankle} ${y} l9 2 M${ankle} ${y} l5 5`;
 }
 function chicken(prefix){return `<g fill="none" stroke-linecap="round" stroke-linejoin="round">
  <path data-ch-leg="far" d="${legPath({x:0,y:0},false)}" stroke="#ca751f" stroke-width="4.5"/>
  <g data-ch-body="">
   <path d="M-22 11C-40 11-42-2-39-8Q-33-6-27 0C-42-18-34-23-27-17L-13-3Z" fill="url(#${prefix}-cream)" stroke="#dfd9ea" stroke-width=".6"/>
   <path d="M-26 1C-31 20-18 37 2 36C23 35 28 16 24 0L20-20C19-33 4-37-6-26C-14-17-9-7-26 1Z" fill="url(#${prefix}-cream)" stroke="#e6e0ee" stroke-width=".7"/>
   <path d="M-23 18Q-15 32 6 30Q19 28 22 15C20 37-8 47-23 18" fill="#cbc1db" opacity=".3"/>
   <path d="M0-29C-15-34-13-44-8-43L-3-36C-9-50 1-51 5-37C6-49 14-46 12-36C24-44 23-30 16-28Z" fill="url(#${prefix}-comb)" stroke="#c73743" stroke-width=".6"/>
   <ellipse cx="21" cy="-3" rx="4" ry="8" fill="url(#${prefix}-comb)"/>
   <ellipse cx="13" cy="-17" rx="5" ry="7" fill="#fff7e8"/>
   <g data-ch-eye=""><ellipse cx="15" cy="-16" rx="2.8" ry="4.6" fill="#312037"/><circle cx="15.6" cy="-18" r="1.1" fill="white"/></g>
   <path data-ch-eye-loss="" display="none" d="m12-19 6 6m0-6-6 6" stroke="#312037" stroke-width="2"/>
   <path d="M8-25q5-2 10 1" stroke="#4c3032" stroke-width="2.6"/>
   <path d="M20-15Q25-19 33-10Q35-6 22-6Z" fill="url(#${prefix}-beak)" stroke="#da8415" stroke-width=".7"/>
   <path d="M23-7L31-8" stroke="#d98b24" stroke-width=".7"/>
   <path d="M-20 5C-27 5-30 16-19 23C-8 30 6 21 4 15Q-9 20-20 5Z" data-ch-wing="" fill="url(#${prefix}-wing)" stroke="#e0d8ea" stroke-width=".8"/>
   <path d="M-26 7Q-21-1-15 0" stroke="#fff9ef" stroke-width="2.5" opacity=".7"/>
  </g><path data-ch-leg="near" d="${legPath({x:0,y:0},true)}" stroke="#f3a12c" stroke-width="4.5"/>
 </g>`;}
 function car(prefix,color){return `<g stroke-linejoin="round">
  <ellipse cy="28" rx="31" ry="8" fill="#070815" opacity=".4"/>
  <rect x="-29" y="11" width="10" height="19" rx="4" fill="#10131f"/><rect x="19" y="11" width="10" height="19" rx="4" fill="#10131f"/>
  <path d="M-25-4L-20-26Q-17-33 0-33Q17-33 20-26L25-4Z" fill="${color}" stroke="#141329" stroke-width="1"/>
  <path d="M-18-24Q0-28 18-24L21-6H-21Z" fill="url(#${prefix}-glass)" stroke="#222237" stroke-width="2"/>
  <path d="M-14-23L-3-25L-15-8H-20Z" fill="#cce1f6" opacity=".2"/>
  <path d="M-24-6Q0-11 24-6L30 10V24Q0 34-30 24V10Z" fill="${color}" stroke="#24203c" stroke-width="1"/>
  <path d="M-22-4Q0-8 22-4L26 7Q0 1-26 7Z" fill="#fff" opacity=".18"/>
  <rect x="-34" y="-5" width="10" height="6" rx="3" fill="#34374c"/><rect x="24" y="-5" width="10" height="6" rx="3" fill="#34374c"/>
  <path d="M-27 20Q0 27 27 20L26 26Q0 33-26 26Z" fill="#26283b"/>
  <rect x="-12" y="14" width="24" height="7" rx="3" fill="#192034"/><path d="M-9 16H9M-8 19H8" stroke="#56586c"/>
  <path d="M-26 9Q-19 7-14 12L-15 16Q-23 18-27 14Z" fill="#fff4b8" stroke="#ffcf76"/>
  <path d="M26 9Q19 7 14 12L15 16Q23 18 27 14Z" fill="#fff4b8" stroke="#ffcf76"/>
  <rect x="-7" y="24" width="14" height="4" rx="1" fill="#c3bace"/>
 </g>`;}
 function defs(p){return `<defs>
 <linearGradient id="${p}-cream" x1="0" y1="0" x2=".8" y2="1"><stop stop-color="#fff"/><stop offset=".7" stop-color="#fff"/><stop offset="1" stop-color="#e4def1"/></linearGradient>
 <linearGradient id="${p}-wing" x2=".7" y2="1"><stop stop-color="#fff"/><stop offset="1" stop-color="#e6e0f1"/></linearGradient>
 <linearGradient id="${p}-comb" x2=".8" y2="1"><stop stop-color="#ff7567"/><stop offset="1" stop-color="#cd243d"/></linearGradient>
 <linearGradient id="${p}-beak" x2=".4" y2="1"><stop stop-color="#ffdb57"/><stop offset="1" stop-color="#f29419"/></linearGradient>
 <linearGradient id="${p}-glass" x2=".5" y2="1"><stop stop-color="#55738e"/><stop offset="1" stop-color="#1a223d"/></linearGradient>
 <linearGradient id="${p}-blue" x1="0" y1="0" x2=".8" y2="1"><stop stop-color="#8cafff"/><stop offset=".4" stop-color="#487ceb"/><stop offset=".7" stop-color="#2856c0"/><stop offset="1" stop-color="#193570"/></linearGradient>
 <linearGradient id="${p}-red" x1="0" y1="0" x2=".8" y2="1"><stop stop-color="#ffada1"/><stop offset=".4" stop-color="#f26c77"/><stop offset=".7" stop-color="#cd435e"/><stop offset="1" stop-color="#76334a"/></linearGradient>
 <linearGradient id="${p}-road" x2="0" y2="1"><stop stop-color="#2c3a54"/><stop offset="1" stop-color="#202c42"/></linearGradient>
 <linearGradient id="${p}-curb" x2="1" y2="0"><stop stop-color="#56729a"/><stop offset=".5" stop-color="#354967"/><stop offset="1" stop-color="#7194be"/></linearGradient>
 <radialGradient id="${p}-light"><stop stop-color="#ffdc98" stop-opacity=".5"/><stop offset="1" stop-color="#ffdc98" stop-opacity="0"/></radialGradient>
 <pattern id="${p}-grain" width="29" height="23" patternUnits="userSpaceOnUse"><circle cx="3" cy="7" r=".6" fill="#ddd0fa" opacity=".07"/><circle cx="18" cy="18" r=".8" fill="#060615" opacity=".18"/></pattern>
 <clipPath id="${p}-road-clip"><path d="M36 0H364L380 300H20Z"/></clipPath>
 </defs>`;}
 function hatch(p){return `<ellipse cy="5" rx="34" ry="21" fill="#0c1322" opacity=".45"/><ellipse rx="34" ry="21" fill="#344966" stroke="#486180" stroke-width="2"/><ellipse rx="27" ry="16" fill="#21324a" stroke="#597597" stroke-width="1.5"/><path d="M-10-7V7M0-8V8M10-7V7" stroke="#111c2e" stroke-width="4.5" stroke-linecap="round"/>`;}
 function barrier(){return `<ellipse cy="20" rx="34" ry="5" fill="#0b1321" opacity=".5"/><rect x="-26" y="0" width="9" height="19" rx="4" fill="#3e5473"/><rect x="17" y="0" width="9" height="19" rx="4" fill="#3e5473"/><rect x="-32" y="-11" width="64" height="17" rx="7" fill="#455d7f"/><rect x="-28" y="-9" width="56" height="9" rx="4" fill="#eef0ff"/><path d="m-24-1 7-7h9l-7 7Zm18 0 7-7h9L3-1Zm18 0 7-7h7l-7 7Z" fill="#6287ff"/>`;}
 function laneState(index,info,reveal=true){
  if(reveal&&info.last?.safe===false)return index===(info.step||0)+1?'is-failed':index<=(info.step||0)?'is-passed':'';
  return index===(info.step||0)?'is-current':index<(info.step||0)?'is-passed':'';
 }
 function scene(info={},previous=null,animating=false){
  const p='ch-road',shown=animating?(previous||{}):info,f=pose(shown,null,1),lanes=info.coefficients||[];
  const current=shown.step||0,target=current+(!animating&&shown.last?.safe===false?1:0);
  const start=Math.max(1,target-1),end=Math.min(lanes.length||20,target+4);
  const indices=Array.from({length:end-start+1},(_,i)=>start+i);
  return `<div class="ch-scene${animating?' is-moving':''}${!animating&&info.last?.safe===false?' is-crashed':''}"><svg class="ch-road-svg" viewBox="0 0 400 338" role="img" aria-label="Курица переходит дорогу по люкам; пройденные полосы закрываются барьерами.">${defs(p)}
  <rect width="400" height="338" fill="#192238"/>
  <g data-ch-world="" transform="translate(${-f.camera} 0)">
   <g class="ch-start-zone"><path d="M0 0H128V338H0Z" fill="#1d2940"/>
   ${[0,82,164,246].map(y=>`<rect x="112" y="${y}" width="16" height="79" rx="2" fill="#35455f"/><rect x="112" y="${y+74}" width="16" height="4" rx="1" fill="#485d7a"/>`).join('')}
   ${[0,24,48,72,96].map(x=>`<rect x="${x}" y="204" width="21" height="57" rx="3" fill="#465b79"/>`).join('')}
   <g transform="translate(53 51)"><ellipse cy="107" rx="23" ry="8" fill="#101828"/><rect x="-15" y="88" width="30" height="16" rx="9" fill="#3d5271"/><rect x="-5" y="24" width="10" height="69" rx="4" fill="#3b506d"/><rect x="-27" y="-10" width="54" height="33" rx="16" fill="#3b506f"/><circle cx="-12" cy="6" r="10" fill="#202d43"/><circle cx="12" cy="6" r="10" fill="#202d43"/><circle data-ch-signal="stop" cx="-12" cy="6" r="7" fill="#e0ad59"/><circle data-ch-signal="go" cx="12" cy="6" r="7" fill="#34445f"/><path d="m-15 2 2-2M9 2l2-2" stroke="#fff3c1" stroke-width="2" stroke-linecap="round" opacity=".75"/></g>
   <g transform="translate(57 296)"><ellipse cy="14" rx="31" ry="12" fill="#101a2a"/><path d="M-29 3Q-38-13-21-16Q-24-31-6-26Q8-37 17-23Q34-23 30-9Q43 6 26 11Q21 29 6 20Q-14 29-19 15Q-36 18-29 3" fill="#2d405b"/><path d="M-26-3Q-32-15-17-15Q-19-28-3-22Q9-32 15-20Q31-22 26-8Q35 3 20 7Q14 19 3 10Q-12 20-17 5Z" fill="#3c5270"/></g>
   </g>
   ${indices.map(i=>{const x=laneX(i),kind=laneState(i,shown,!animating),safe=i<=current;
    const traffic=i>target+(animating?1:0);
    return `<g data-ch-world-lane="${i}" transform="translate(${x} 0)">
     <path d="M54 4V334" stroke="#344762" stroke-width="3" stroke-dasharray="15 19" stroke-linecap="round" opacity=".55"/>
     <g transform="translate(0 ${crossingY})">${hatch(p)}</g>
     <g data-ch-barrier="${i}" transform="translate(0 146)" ${safe?'':'display="none"'}>${barrier()}</g>
     ${traffic?`<g class="ch-traffic ${i%2?'ch-traffic-red':'ch-traffic-blue'}" style="--ch-delay:-${(i*1.7)%6}s">${car(p,`url(#${p}-${i%2?'red':'blue'})`).replace('<g ','<g transform="translate(0 56) scale(.92)" ')}</g>`:''}
     <g data-ch-lane="${i}" class="ch-lane ${kind} ${lanes[i-1]>=1000?'is-long':''}" transform="translate(0 267)"><rect x="-42" width="84" height="30" rx="12"/><text y="20" text-anchor="middle">${Number(lanes[i-1]||1).toFixed(2)}×</text></g>
    </g>`;}).join('')}
  </g>
  <ellipse data-ch-shadow="" cx="${f.x}" cy="${crossingY}" rx="22" ry="6" fill="#101829" opacity=".3"/>
  <g data-chicken="" transform="translate(${f.x} 194) scale(.75)">${chicken(p)}</g>
  <g data-ch-crossing-car="" display="none">${car(p,`url(#${p}-red)`)}</g>
  </svg></div>`;
 }
 function paint(host,info,previous,t,animating){
  const f=pose(info,animating?previous:null,t),q=s=>host.querySelector(s),attr=(s,k,v)=>q(s)?.setAttribute(k,v);
  attr('[data-ch-world]','transform',`translate(${-f.camera} 0)`);
  attr('[data-chicken]','transform',`translate(${f.x} ${f.birdY}) rotate(${f.birdAngle}) scale(.75)`);
  attr('[data-ch-body]','transform',`translate(0 ${f.bodyY})`);
  attr('[data-ch-shadow]','cx',f.x);attr('[data-ch-shadow]','rx',22+f.fall*9);
  attr('[data-ch-leg="near"]','d',legPath(f.near,true));attr('[data-ch-leg="far"]','d',legPath(f.far,false));
  attr('[data-ch-wing]','transform',`rotate(${f.wing} -12 8)`);
  attr('[data-ch-eye]','display',f.fall>.5?'none':'inline');attr('[data-ch-eye-loss]','display',f.fall>.5?'inline':'none');
  attr('[data-ch-crossing-car]','display',animating?'inline':'none');
  attr('[data-ch-crossing-car]','transform',`translate(${f.carX} ${f.carY}) scale(${f.carScale})`);
  const cleared=!animating||t>=.88,visible=cleared?info:(previous||{});
  attr('[data-ch-signal="stop"]','fill',animating?'#39485c':'#e0ad59');
  attr('[data-ch-signal="go"]','fill',animating?'#8cccaa':'#34445f');
  for(const node of host.querySelectorAll('[data-ch-barrier]')){
   const i=Number(node.dataset.chBarrier),raised=i<=(visible.step||0);
   node.setAttribute('display',raised?'inline':'none');
   const fresh=animating&&i>(previous?.step||0);
   node.setAttribute('transform',`translate(0 ${146+(fresh?8*(1-ease(range(t,.88,1))):0)})`);
  }
  for(const node of host.querySelectorAll('[data-ch-lane]')){
   const i=Number(node.dataset.chLane),state=laneState(i,visible,cleared);
   node.setAttribute('class',`ch-lane ${state} ${(info.coefficients?.[i-1]||0)>=1000?'is-long':''}`);
  }
 }
 function cover(){const p='ch-cover';return `<svg class="ch-cover" viewBox="0 0 150 140" aria-hidden="true">${defs(p)}<rect x="10" y="6" width="130" height="128" rx="16" fill="#1d2940"/><path d="M27 12V130M126 12V130" stroke="#55749a" stroke-width="2" stroke-dasharray="12 10"/><g transform="translate(76 114)">${hatch(p)}</g><g transform="translate(76 35) scale(.68)">${barrier()}</g><g transform="translate(76 73) scale(.84)">${chicken(p)}</g></svg>`;}

 const api={pose,legPath,scene,paint,cover,laneX,laneState,cameraAt,crossingY};if(typeof module==='object'&&module.exports)module.exports=api;else root.ChickenScene=api;
})(globalThis);
