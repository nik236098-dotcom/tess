'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function setup(){
 const images=[];
 class Image { constructor(){images.push(this);} }
 const ctx={Image,setTimeout,clearTimeout};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../public/classic-cards.js'),'utf8'),ctx);
 return {cards:ctx.ClassicCards,images};
}
test('visible card loading deduplicates requests and ignores concealed cards',async()=>{
 const {cards,images}=setup();
 const a=cards.load(['As','As','??']),b=cards.load(['As']);
 assert.equal(images.length,1);
 images[0].onload();
 await Promise.all([a,b]);await cards.load(['As']);
 assert.equal(images.length,1);
});
test('failed card image can be retried on the next state',async()=>{
 const {cards,images}=setup();
 const a=cards.load(['Kh']);images[0].onerror();await a;
 const b=cards.load(['Kh']);assert.equal(images.length,2);images[1].onload();await b;
});
test('every card face points to a bundled WebP asset and concealed cards emit no image',()=>{
 const {cards}=setup();
 for(const suit of 'shdc')for(const rank of 'A23456789TJQK'){
  const markup=cards.face(rank+suit),src=markup.match(/src="([^"]+)"/)[1];
  const bytes=fs.readFileSync(path.join(__dirname,'../public',src));
  assert.equal(bytes.toString('ascii',0,4),'RIFF');assert.equal(bytes.toString('ascii',8,12),'WEBP');
 }
 assert.equal(cards.face('??'),'');assert.equal(cards.face('<img>'),'');
});
