'use strict';
const fs=require('node:fs');
const path=require('node:path');

class RecentWins {
  constructor({file=null,limit=12,log=console.error}={}) {
    this.file=file;this.limit=limit;this.log=log;this.entries=[];
    if(!file)return;
    try {
      const data=JSON.parse(fs.readFileSync(file,'utf8'));
      if(!Array.isArray(data.wins))throw new Error('Invalid Live feed');
      this.entries=data.wins.filter(w=>w&&Number.isFinite(w.amount)&&w.amount>0&&typeof w.name==='string'&&typeof w.game==='string'&&Number.isFinite(w.at)).slice(0,limit);
    } catch(error) { if(error.code!=='ENOENT')log('Не удалось прочитать Live:',error.message); }
  }
  add(win) {
    if(!win||!Number.isFinite(win.amount)||win.amount<=0)return;
    const multiplier=Number.isFinite(win.bet)&&win.bet>0&&Number.isFinite(win.payout)?win.payout/win.bet:null;
    this.entries.unshift({...win,multiplier,at:Date.now()});
    this.entries.length=Math.min(this.entries.length,this.limit);
    if(!this.file)return;
    const temporary=this.file+'.tmp';
    try {
      fs.mkdirSync(path.dirname(this.file),{recursive:true});
      fs.writeFileSync(temporary,JSON.stringify({wins:this.entries}),{mode:0o600});
      fs.renameSync(temporary,this.file);
    } catch(error) {
      // The payout is already settled; a feed-storage failure must not undo it.
      this.log('Не удалось сохранить Live:',error.message);
      try {fs.unlinkSync(temporary);}catch{}
    }
  }
}
module.exports={RecentWins};
