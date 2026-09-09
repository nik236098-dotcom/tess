'use strict';
// A single coordinate system for pockets, rotor and ball; independent of frame rate.
(function(root){
  const order=[0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26];
  const reds=new Set([1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]);
  const colour=n=>n===0?'green':reds.has(n)?'red':'black';
  const pocket=n=>-90+order.indexOf(n)*360/37;
  const clamp=t=>Math.max(0,Math.min(1,t));
  const smooth=t=>{t=clamp(t);return t*t*t*(t*(t*6-15)+10);};
  function plan(number,startWheel=0,startBall=-90,startRadius=264,random=Math.random){
    if(!order.includes(number))throw new RangeError('Unknown pocket');
    const target=pocket(number);
    const residue=((startBall-startWheel-target)%360+360)%360;
    return {number,startWheel,target,travel:8*360+residue,endWheel:startWheel+(4+random())*360,capture:.88,startRadius};
  }
  function sample(p,t){
    t=clamp(t);
    const wheel=p.startWheel+(p.endWheel-p.startWheel)*smooth(t);
    // Relative velocity reaches zero at capture; thereafter the ball rides its pocket.
    const ball=wheel+p.target+p.travel*(1-smooth(t/p.capture));
    const outward=smooth(t/.12),drop=smooth((t-.64)/(p.capture-.64));
    const track=p.startRadius+(264-p.startRadius)*outward;
    const bounce=t>.72&&t<p.capture?3*Math.sin(Math.PI*(t-.72)/(.16))**2*(1-drop):0;
    return {wheel,ball,radius:track+(176-track)*drop+bounce,locked:t>=p.capture};
  }
  function cells(){
    const out=[{key:'straight:0',type:'straight',value:0,label:'0',cls:'green',column:'1',row:'1 / 4'}];
    for(let c=0;c<12;c++)for(let r=0;r<3;r++){
      const n=3*c+3-r;out.push({key:`straight:${n}`,type:'straight',value:n,label:String(n),cls:colour(n),column:String(c+2),row:String(r+1)});
    }
    for(let d=1;d<=3;d++)out.push({key:`dozen:${d}`,type:'dozen',value:d,label:`${(d-1)*12+1}–${d*12}`,cls:'dark dozen',column:`${1+(d-1)*4} / ${d===3?14:1+d*4}`,row:'4'});
    ['low','even','red','black','odd','high'].forEach((type,i)=>out.push({key:type+':',type,value:null,label:['1–18','Чёт','◆','◇','Нечёт','19–36'][i],cls:'dark outside '+(type==='red'?'red-bet':''),column:`${1+i*2} / ${i===5?14:3+i*2}`,row:'5'}));
    return out;
  }
  function wheel(){
    const point=(r,a)=>[r*Math.cos(a*Math.PI/180),r*Math.sin(a*Math.PI/180)];
    const xy=p=>p.map(n=>n.toFixed(3)).join(',');
    const sector=(r0,r1,a,b,fill)=>`<path d="M${xy(point(r0,a))}L${xy(point(r1,a))}A${r1} ${r1} 0 0 1 ${xy(point(r1,b))}L${xy(point(r0,b))}A${r0} ${r0} 0 0 0 ${xy(point(r0,a))}Z" fill="${fill}" stroke="#ac9eda" stroke-width=".9"/>`;
    const colors={red:'#a91e37',black:'#11172e',green:'#14805c'};
    let sectors='';
    for(const n of order){const a=pocket(n),[x,y]=point(224,a);sectors+=sector(204,245,a-180/37,a+180/37,colors[colour(n)])+sector(151,200,a-180/37,a+180/37,colors[colour(n)]);sectors+=`<text x="${x}" y="${y}" transform="rotate(${a+90} ${x} ${y})" text-anchor="middle" dominant-baseline="central" class="num">${n}</text>`;}
    let rays='';for(let i=0;i<16;i++)rays+=`<path d="M${xy(point(36,i*22.5))}L${xy(point(150,i*22.5))}" stroke="#7681c1" stroke-opacity=".2"/>`;
    return `<svg viewBox="-322 -322 644 644" role="img" aria-label="Европейская рулетка, 37 чисел">
      <defs>
        <linearGradient id="rv-rim" x2=".2" y2="1"><stop stop-color="#b5a0f8"/><stop offset=".13" stop-color="#28264f"/><stop offset=".55" stop-color="#15182f"/><stop offset=".87" stop-color="#6662b0"/><stop offset="1" stop-color="#17132e"/></linearGradient>
        <radialGradient id="rv-bowl"><stop stop-color="#354976"/><stop offset=".7" stop-color="#1a294d"/><stop offset="1" stop-color="#0d122c"/></radialGradient>
        <linearGradient id="rv-metal"><stop stop-color="#42467d"/><stop offset=".25" stop-color="#cdd1fa"/><stop offset=".48" stop-color="#7079ad"/><stop offset=".67" stop-color="#e9e8ff"/><stop offset="1" stop-color="#343354"/></linearGradient>
        <radialGradient id="rv-ball" cx="32%" cy="25%"><stop stop-color="#fff"/><stop offset=".5" stop-color="#f9f8ff"/><stop offset="1" stop-color="#898aa9"/></radialGradient>
      </defs>
      <circle cy="7" r="310" fill="#05091d"/>
      <circle r="310" fill="url(#rv-rim)" stroke="#7770b4" stroke-width="2"/>
      <circle r="301" fill="none" stroke="#b3a0ff" stroke-width="2"/>
      <circle r="289" fill="url(#rv-bowl)" stroke="#0a0f29" stroke-width="7"/>
      <circle r="273" fill="none" stroke="#4e527b" stroke-width="2"/>
      <circle r="255" fill="none" stroke="#747bad" stroke-width="3"/>
      <g id="rl-rotor"><circle r="247" fill="#0b102b"/>${sectors}<circle r="149" fill="url(#rv-bowl)" stroke="#9c98d1" stroke-width="2"/>${rays}
        <circle r="37" fill="url(#rv-metal)" stroke="#cbd0ee"/><circle r="29" fill="#272e54" stroke="#919cc9"/>
        <path d="M-57 -4H57M-4 -57V57" stroke="#222749" stroke-width="13" stroke-linecap="round"/>
        <path d="M-57 -7H57M-7 -57V57" stroke="url(#rv-metal)" stroke-width="8" stroke-linecap="round"/>
        <circle r="19" fill="url(#rv-metal)" stroke="#d1d5f6"/><circle cx="-3" cy="-4" r="9" fill="url(#rv-ball)"/>
      </g>
      <g aria-hidden="true">
        <ellipse cy="4" rx="34" ry="20" fill="#050c2580"/>
        <ellipse cy="-1" rx="26" ry="16" fill="url(#rv-metal)" stroke="#a9b1d9"/>
        <path d="M-15 -12Q-11 -30 -11 -48L11 -48Q11 -30 15 -12Z" fill="url(#rv-metal)" stroke="#979dd0" stroke-width="1.5"/>
        <ellipse cy="-12" rx="16" ry="6" fill="url(#rv-metal)" stroke="#c0c6f2"/>
        <ellipse cy="-48" rx="12" ry="6" fill="url(#rv-metal)" stroke="#bfc4f2"/>
        <circle cy="-58" r="13" fill="url(#rv-ball)" stroke="#9197c9" stroke-width="2"/>
      </g>
      <path d="M0 -304l5 8-5 8-5-8Z M304 0l-8 5-8-5 8-5Z M0 304l5-8-5-8-5 8Z M-304 0l8 5 8-5-8-5Z" fill="#b9acf5"/>
      <g id="rl-ball" class="hidden" transform="translate(0 -264)"><ellipse cy="5" rx="8" ry="6" fill="#0008"/><circle r="7" fill="url(#rv-ball)" stroke="#e9e8ff" stroke-width=".6"/></g>
    </svg>`;
  }
  const api={order,colour,pocket,plan,sample,cells,wheel};
  if(typeof module==='object'&&module.exports)module.exports=api;else root.RouletteView=api;
})(globalThis);
