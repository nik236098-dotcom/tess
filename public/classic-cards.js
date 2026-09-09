'use strict';
// Inline same-document references avoid WebKit's external SVG <use> blank faces.
(function(root){
  const prefix='bj-classic-';
  const suits={s:['spade','♠'],h:['heart','♥'],d:['diamond','♦'],c:['club','♣']};
  let pending;
  function load(){
    if(pending)return pending;
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),8000);
    pending=fetch('/img/classic/deck.svg',{signal:controller.signal}).then(r=>{if(!r.ok)throw Error('Card artwork unavailable');return r.text();}).then(text=>{
      const doc=new DOMParser().parseFromString(text,'image/svg+xml');
      if(doc.querySelector('parsererror'))throw Error('Invalid card artwork');
      const svg=doc.documentElement;
      for(const el of svg.querySelectorAll('*')){
        if(el.id)el.id=prefix+el.id;
        for(const attr of Array.from(el.attributes)){
          if(attr.localName==='href'&&attr.value.startsWith('#'))el.setAttributeNS(attr.namespaceURI,attr.name,'#'+prefix+attr.value.slice(1));
          else if(attr.value.includes('url(#'))el.setAttribute(attr.name,attr.value.replace(/url\(#([^)]*)\)/g,(_,id)=>`url(#${prefix}${id})`));
        }
      }
      svg.setAttribute('width','0');svg.setAttribute('height','0');svg.setAttribute('aria-hidden','true');
      svg.style.cssText='position:absolute;width:0;height:0;overflow:hidden;pointer-events:none';
      document.body.appendChild(document.importNode(svg,true));
      document.documentElement.classList.add('bj-classic-ready');return true;
    }).catch(()=>{pending=null;return false;}).finally(()=>clearTimeout(timeout));
    return pending;
  }
  function face(code){
    const pair=suits[code[1]],rank=({A:'1',T:'10',J:'jack',Q:'queen',K:'king'})[code[0]]||code[0];
    if(!pair||!['A','2','3','4','5','6','7','8','9','T','J','Q','K'].includes(code[0]))return '';
    const label=code[0]==='T'?'10':code[0];
    return `<span class="pt-card-fallback"><b>${label}<small>${pair[1]}</small></b><i>${pair[1]}</i><b>${label}<small>${pair[1]}</small></b></span><svg class="pt-card-face" viewBox="0 0 169.075 244.64" role="img" aria-label="${code}"><use href="#${prefix}${pair[0]}_${rank}" xlink:href="#${prefix}${pair[0]}_${rank}"></use></svg>`;
  }
  root.ClassicCards={load,face};
})(globalThis);
