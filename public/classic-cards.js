'use strict';
// Rasterized from the bundled classic SVG deck: consistent in Telegram/WebKit.
(function(root){
  const valid = /^[A2-9TJQK][shdc]$/;
  const pending = new Map();
  const source = code => `/img/classic/cards/${code}.webp`;
  function load(codes = []) {
    return Promise.all([...new Set(codes)].filter(code => valid.test(code)).map(code => {
      if (!pending.has(code)) pending.set(code, new Promise(resolve => {
        const img = new Image(); let timer;
        const finish = ok => { clearTimeout(timer); img.onload = img.onerror = null; if (!ok) pending.delete(code); resolve(ok); };
        img.onload = () => finish(true); img.onerror = () => finish(false);
        timer = setTimeout(() => finish(false), 2500); img.src = source(code);
      }));
      return pending.get(code);
    }));
  }
  function face(code){
    if(!valid.test(code)) return '';
    const rank = code[0] === 'T' ? '10' : code[0], suit = {s:'♠',h:'♥',d:'♦',c:'♣'}[code[1]];
    return `<span class="pt-card-fallback" aria-hidden="true">${rank}<small>${suit}</small><i>${suit}</i></span><img class="pt-card-face" src="${source(code)}" width="338" height="489" alt="${rank}${suit}" decoding="sync" />`;
  }
  if (root.document) root.document.addEventListener('error', event => {
    if (event.target?.classList?.contains('pt-card-face')) event.target.classList.add('is-missing');
  }, true);
  root.ClassicCards={load,face};
})(globalThis);
