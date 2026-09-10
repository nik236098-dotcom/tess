'use strict';
/* Matched transparent gestures; a native fallback keeps play available on slow connections. */
(function(root){
 const names=['rock','paper','scissors'];
 const shapes=[
  'M29 89 22 70C16 61 17 49 24 46L24 33Q25 23 34 26Q38 16 47 21Q56 14 64 23Q76 20 79 31L84 57Q87 77 71 91L69 104H32Z',
  'M30 90 12 62Q7 53 14 48Q20 44 26 54L32 62 25 24Q23 14 30 13Q37 11 39 21L43 49 40 12Q40 3 48 4Q55 4 56 13L57 48 60 15Q61 7 68 9Q74 11 73 20L70 53 78 29Q81 21 87 25Q92 28 89 37L80 76Q77 87 69 92L68 105H33Z',
  'M30 92 20 74Q13 62 18 55Q22 50 30 55L37 62 26 17Q24 7 32 5Q39 4 42 14L53 47 66 12Q69 4 76 7Q82 10 79 19L66 55Q79 48 83 55Q88 61 82 70L77 85 68 94 67 105H32Z'
 ];
 function hand(index,prefix='hand',tone='violet'){
  const i=Math.max(0,Math.min(2,Number(index)||0)),base=tone==='rose'?'#f0abc4':'#bfa7ef',shade=tone==='rose'?'#ca779b':'#8465bd';
  const lines=i===0?'M25 46 34 49 36 33M37 48 46 48 47 29M49 46 58 47 60 31M30 62Q38 51 49 57L65 65Q69 73 62 77L43 71M58 78 68 80':i===1?'M36 70Q52 60 67 66M43 81Q52 74 63 77':'M37 62Q47 51 57 57L71 68Q74 75 67 79L45 72M61 49 65 58';
  return `<svg class="duel-hand-art" data-hand="${names[i]}" viewBox="0 0 100 116" aria-hidden="true"><defs><linearGradient id="${prefix}-skin" x2=".75" y2="1"><stop stop-color="#fff9f0"/><stop offset=".48" stop-color="#f5e9df"/><stop offset="1" stop-color="#dbc5c9"/></linearGradient><linearGradient id="${prefix}-cuff" x2=".3" y2="1"><stop stop-color="${base}"/><stop offset="1" stop-color="${shade}"/></linearGradient></defs><g class="duel-hand-fallback"><path d="${shapes[i]}" fill="#695178" opacity=".3" transform="translate(1 3)"/><path d="${shapes[i]}" fill="url(#${prefix}-skin)" stroke="#c8b0bd" stroke-width="1.4" stroke-linejoin="round"/><path d="${lines}" fill="none" stroke="#b994a3" stroke-width="1.5" stroke-linecap="round"/><path d="M33 87Q49 96 70 87L71 103Q51 111 32 103Z" fill="url(#${prefix}-cuff)" stroke="${shade}" stroke-width="1"/><path d="M36 92Q51 98 66 92" fill="none" stroke="#fff" opacity=".4" stroke-width="2" stroke-linecap="round"/></g><image class="duel-hand-sprite" href="/img/rps/${names[i]}-v2.webp" width="100" height="116"/></svg>`;
 }
 for(const name of names)if(root.Image){const img=new root.Image();img.onload=()=>root.document?.documentElement.classList.add('rps-'+name+'-ready');img.src='/img/rps/'+name+'-v2.webp';}
 const api={hand};if(typeof module==='object'&&module.exports)module.exports=api;else root.DuelArt=api;
})(globalThis);
