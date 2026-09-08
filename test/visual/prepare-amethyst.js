'use strict';
// Generate disposable visual harness from the actual production markup/client.
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'../..');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const write=(p,s)=>fs.writeFileSync(path.join(root,p),s);
write('public/qa-amethyst-client.js',read('public/app.js').replace(/\nboot\(\);\s*$/, '\nbindUi(); watchTableSize();\n')+'\n'+read('test/visual/amethyst-fixture.js'));
write('public/qa-amethyst-app.html',read('public/index.html').replace('/app.js?v=95','/qa-amethyst-client.js').replace('<script src="https://telegram.org/js/telegram-web-app.js"></script>',''));
write('public/qa-amethyst-app-frame.html','<!doctype html><html><meta charset="utf-8"><style>body{margin:8px;background:#100a18}iframe{border:0;width:390px;height:780px;display:block}</style><iframe src="/qa-amethyst-app.html?clean=1"></iframe></html>');
