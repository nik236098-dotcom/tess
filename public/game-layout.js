'use strict';
// Fit only the scene. Betting controls retain their real CSS sizes and hit areas.
(function(){
  function start(){
    const tables=new ResizeObserver(()=>{
      if(typeof fitBlackjack==='function')fitBlackjack();
      if(typeof fitBaccarat==='function')fitBaccarat();
      if(typeof fitRoulette==='function')fitRoulette();
    });
    for(const id of ['screen-bj','screen-bc','screen-rl']){const screen=document.getElementById(id);if(screen)tables.observe(screen);}
    const viewport=document.getElementById('ag-scene-viewport'),stage=document.getElementById('ag-stage');
    if(!viewport||!stage)return;
    let frame=0;
    function fit(){
      frame=0;const width=viewport.clientWidth,height=viewport.clientHeight;
      if(!width||!height)return;
      stage.style.width=width+'px';
      stage.style.setProperty('--scene-height',height+'px');
      const natural=stage.scrollHeight;
      const scale=Math.min(1,height/Math.max(1,natural));
      stage.style.transform=`translate(-50%,-50%) scale(${scale})`;
    }
    const schedule=()=>{if(!frame)frame=requestAnimationFrame(fit);};
    new ResizeObserver(schedule).observe(viewport);
    new MutationObserver(schedule).observe(stage,{childList:true,subtree:true,characterData:true});
    stage.addEventListener('load',schedule,true);window.addEventListener('resize',schedule);
    // Keep the selected step in sight, without scrolling the entire screen.
    const table=document.getElementById('ag-paytable');
    new MutationObserver(()=>{const current=table.querySelector('[aria-current="step"]');if(current)table.scrollLeft=Math.max(0,current.offsetLeft-table.offsetLeft-(table.clientWidth-current.clientWidth)/2);}).observe(table,{childList:true});
    schedule();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
