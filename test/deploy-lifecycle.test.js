'use strict';
// Execute the actual Bash updater against disposable command doubles. No real service or checkout is modified.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawnSync}=require('node:child_process');
function run(mode){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'croco-deploy-test-')),bin=path.join(dir,'bin');fs.mkdirSync(bin);
 const helper=`#!${process.execPath}
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
if(path.basename(process.argv[1])==='tar')process.exit(0);
const dir=process.env.CROCO_TEST_DIR,file=path.join(dir,'state.json');
let state=fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):{ref:'old',probes:0,events:[]};
let name=path.basename(process.argv[1]),args=process.argv.slice(2);if(name==='sudo'){name=args[2];args=args.slice(3);}if(name==='git'&&args[0]==='-C')args=args.slice(2);
state.events.push(name+' '+args.join(' '));let code=0,out='';const mode=process.env.CROCO_TEST_MODE;
if(name==='id')out='0';
if(name==='git'){
 if(args[0]==='rev-parse')out=args.includes('FETCH_HEAD')?'new':state.ref;
 if(args[0]==='checkout'){state.ref=args.at(-1);state.probes=0;}
}
if(name==='node'&&mode==='bad-check'&&args.includes('public/app.js'))code=1;
if(name==='systemctl'&&args[0]==='start'&&mode==='failed-start'&&state.ref==='new')code=1;
if(name==='curl'){state.probes++;if(state.ref==='new'&&(mode==='timeout'||state.probes<=3))code=7;}
if(name==='sleep')Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,40);
fs.writeFileSync(file,JSON.stringify(state));if(out)console.log(out);process.exit(code);
`;
 fs.writeFileSync(path.join(bin,'helper'),helper,{mode:0o755});for(const cmd of ['sudo','git','id','node','systemctl','curl','sleep','flock','tar'])fs.symlinkSync('helper',path.join(bin,cmd));
 let script=fs.readFileSync('scripts/crash-update.sh','utf8').replace('/opt/poker/app',dir).replace('/run/lock/poker-update.lock',path.join(dir,'lock')).replace('/tmp/croco-update.XXXXXXXX',path.join(dir,'stage.XXXXXXXX')).replace('/usr/bin/node "$@"','command node "$@"').replace('[[ -x /usr/bin/node ]]', '[[ -x '+process.execPath+' ]]').replace('SECONDS + 45','SECONDS + 2');
 fs.writeFileSync(path.join(dir,'update.sh'),script);
 const result=spawnSync('bash',[path.join(dir,'update.sh')],{env:{...process.env,PATH:bin+':'+process.env.PATH,CROCO_TEST_DIR:dir,CROCO_TEST_MODE:mode},encoding:'utf8',timeout:10000});
 const state=JSON.parse(fs.readFileSync(path.join(dir,'state.json')));const leftover=fs.readdirSync(dir).filter(f=>f.startsWith('stage.'));
 fs.rmSync(dir,{recursive:true,force:true});assert.equal(result.error,undefined);assert.deepEqual(leftover,[]);return {...result,state};
}
test('invalid preflight leaves the old service and checkout untouched',()=>{const r=run('bad-check');assert.notEqual(r.status,0);assert.equal(r.state.ref,'old');assert.ok(r.state.events.includes('node --check public/app.js'));assert.ok(!r.state.events.some(s=>s.startsWith('systemctl stop')||s.startsWith('git checkout')));});
test('preflight precedes stop and success waits for two HTTP responses after slow startup',()=>{const r=run('success');assert.equal(r.status,0,r.stderr);const e=r.state.events;assert.ok(e.indexOf('node -')<e.indexOf('systemctl stop poker'));assert.equal(r.state.ref,'new');assert.equal(r.state.probes,5);assert.match(r.stdout,/Приложение отвечает по HTTP/);});
test('HTTP timeout restores previous checkout and verifies its response before reporting rollback',()=>{const r=run('timeout');assert.notEqual(r.status,0);assert.equal(r.state.ref,'old');assert.equal(r.state.probes,2);assert.match(r.stderr,/Предыдущая версия восстановлена и отвечает по HTTP/);assert.doesNotMatch(r.stdout,/Готово:/);});
test('failed systemctl start also rolls back instead of leaving the site stopped',()=>{const r=run('failed-start');assert.notEqual(r.status,0);assert.equal(r.state.ref,'old');assert.equal(r.state.probes,2);assert.match(r.stderr,/Предыдущая версия восстановлена/);});
