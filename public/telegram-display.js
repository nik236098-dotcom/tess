'use strict';
(function(root){
 function start(tg,doc=root.document){
  if(!tg)return;
  const sync=()=>doc?.documentElement.classList.toggle('tg-fullscreen',Boolean(tg.isFullscreen));
  // expand remains the fallback for old clients and unsupported platforms.
  tg.expand();
  if(typeof tg.requestFullscreen!=='function'||!tg.isVersionAtLeast?.('8.0'))return;
  tg.onEvent('fullscreenChanged',sync);
  tg.onEvent('fullscreenFailed',()=>{sync();if(!tg.isFullscreen)tg.expand();});
  sync();
  if(!tg.isFullscreen){try{tg.requestFullscreen();}catch{tg.expand();}}
 }
 const api={start};if(typeof module==='object'&&module.exports)module.exports=api;else root.TelegramDisplay=api;
})(globalThis);
