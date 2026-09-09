'use strict';
// Render the production SVG and production motion attributes, without a browser.
const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const scene=require('../public/darts-scene'),motion=require('../public/casino-motion'),rules=require('../public/darts-rules');
const output=process.argv[2];if(!output)throw Error('Pass a scratch output directory');fs.mkdirSync(output,{recursive:true});
const info={phase:'done',revision:4,multiplier:6,detail:{radius:.15,angle:-Math.PI/2,rules:rules.version},history:[{multiplier:6},{multiplier:.6},{multiplier:1.3},{multiplier:.4}]};
function render(t){
 const f=motion.frame('darts',info,null,t),visible=f.hit?info:{history:info.history.slice(1)},nodes=new Map();
 const stage={querySelector(selector){if(!nodes.has(selector))nodes.set(selector,{attributes:{},dataset:{},innerHTML:'',setAttribute(k,v){this.attributes[k]=v;}});return nodes.get(selector);}};
 scene.paint(stage,f,info);
 let svg=scene.svg(visible).replace('<defs>','<rect width="360" height="386" rx="20" fill="#1c2740"/><defs>');
 for(const name of ['dart','impact']){
  const attrs=nodes.get(`[data-dt-${name}]`).attributes;
  svg=svg.replace(new RegExp(`<[^>]*data-dt-${name}=""[^>]*>`),tag=>{
   for(const [key,value]of Object.entries(attrs)){
    const re=new RegExp(` ${key}="[^"]*"`);tag=re.test(tag)?tag.replace(re,` ${key}="${value}"`):tag.replace(/\/?>(?=$)/,ending=>` ${key}="${value}"${ending}`);
   }return tag;
  });
 }
 return svg;
}
for(let i=0;i<60;i++)fs.writeFileSync(path.join(output,`${String(i).padStart(3,'0')}.svg`),render(Math.min(1,i/42)));
fs.writeFileSync(path.join(output,'scene.svg'),render(1));
const r=spawnSync('inkscape',[path.join(output,'scene.svg'),'--export-type=png',`--export-filename=${path.join(output,'scene.png')}`,'--export-width=720'],{encoding:'utf8'});if(r.status!==0)throw Error(r.stderr);
