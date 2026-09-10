'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createRequire}=require('node:module');
const root=path.resolve(__dirname,'..'),localRequire=createRequire(path.join(root,'package.json'));
const script=fs.readFileSync(path.join(root,'scripts/crash-update.sh'),'utf8');
const check=script.match(/node - <<'JS'\n([\s\S]*?)\nJS/)[1];
const catalog=localRequire('./public/game-catalog');
function verify(missing){
 vm.runInNewContext(check,{require(id){if(id==='node:fs')return {statSync(p){if(p===missing)throw new Error('Missing asset: '+p);return fs.statSync(path.join(root,p));}};return localRequire(id);}});
}
test('deployment validates the same artwork paths used by every catalog tile',()=>{
 for(const id of Object.keys(catalog.names))assert.ok(catalog.tile(id).includes(`src="${catalog.artwork(id)}"`));
 assert.equal(catalog.artwork('cryo'),'/img/game-cards/cryo.svg');
 assert.equal(catalog.artwork('midnight'),'/img/game-cards/midnight.svg');
 assert.equal(catalog.artwork('race'),'/img/game-cards/racing.webp');
 assert.doesNotThrow(()=>verify());
});
test('deployment still rejects missing slot cards and symbols instead of bypassing validation',()=>{
 for(const asset of ['public/img/game-cards/cryo.svg','public/img/game-cards/midnight.svg','public/img/feature-slots/cryo/8.svg','public/img/feature-slots/midnight/station.svg'])assert.throws(()=>verify(asset),/Missing asset:/);
});
