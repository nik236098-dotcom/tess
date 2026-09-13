'use strict';
// Self-contained card files avoid WebKit's nested SVG <use> rendering failures.
(function(root){
  const valid = /^[A2-9TJQK][shdc]$/;
  function load(){ return Promise.resolve(true); }
  function face(code){
    if(!valid.test(code)) return '';
    return `<img class="pt-card-face" src="/img/classic/cards/${code}.svg" width="169" height="245" alt="${code}" decoding="sync" />`;
  }
  root.ClassicCards={load,face};
})(globalThis);
