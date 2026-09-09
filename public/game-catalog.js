'use strict';
(function(root){
  const names={holdem:"Texas Hold'em",omaha:'Omaha',blackjack:'Blackjack',baccarat:'Baccarat',roulette:'Roulette',mines:'Mines',nvuti:'Nvuti',hilo:'Hilo',crash:'Crash',plinko:'Plinko',tower:'Tower',keno:'Keno',dragon:'Dragon & Tiger',diamonds:'Diamonds',videopoker:'Video Poker',sicbo:'Sic Bo',chicken:'Chicken',coin:'Coin Flip',rps:'Rock Paper Scissors',slots:'Croc Slots',andar:'Andar Bahar',darts:'Darts',bowling:'Bowling',balloon:'Balloon',race:'Racing',fishing:'Fishing'};
  const file=id=>id==='race'?'racing':id;
  const text=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function tile(id,native=false){
    const name=names[id];if(!name)return '';
    return `<button type="button" ${native?`id="play-${id}"`:`data-arcade="${id}"`} class="game-tile" aria-label="${text(name)}"><img src="/img/game-cards/${file(id)}.webp" alt="" width="600" height="800" loading="lazy" decoding="async"><span class="game-tile-title${name.length>13?' is-long':''}">${text(name)}</span></button>`;
  }
  const api={names,tile,file};if(typeof module==='object'&&module.exports)module.exports=api;else root.GameCatalog=api;
})(globalThis);
