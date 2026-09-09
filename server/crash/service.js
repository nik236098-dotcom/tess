'use strict';
const { CrashGame, CrashError } = require('./game');
const { MAX_BALANCE } = require('../accounts');
function createCrashService({ accounts, clients, noteWin }) {
  const games = new Map();
  // Restored rounds progress even if their player never reconnects.
  for (const account of accounts.accounts.values()) if (account.crashRound) {
    const game = new CrashGame(); game.restore(account.crashRound); games.set(account.id, game);
  }
  const save = (id, game) => { accounts.get(id).crashRound = game.snapshot(); accounts.flush(); };
  function resolve(id, game, now) {
    const revision = game.revision; const settled = game.settled;
    game.advance(now);
    if (game.phase === 'done' && !game.settled && accounts.balanceOf(id) + game.payout <= MAX_BALANCE) {
      game.settled = true;
      if (game.payout) accounts.deposit(id, game.payout);
      if (game.payout > game.bet) noteWin({ userId:id, name:accounts.get(id).name, amount:game.payout-game.bet, game:'crash', code:'CR' });
    }
    if (revision !== game.revision || settled !== game.settled) save(id,game);
  }
  function send(client, game, now = Date.now()) {
    client.send({ type:'cr', ...game.state(now), balance:accounts.balanceOf(client.user.id) });
  }
  function handle(client, message) {
    const id=client.user.id; let game=games.get(id);
    if (!game) { game=new CrashGame(); games.set(id,game); }
    client.watchingCrash=true;
    const now=Date.now(); resolve(id,game,now);
    try {
      if (message.type==='cr_start') {
        game.check(message.revision); game.validate(message.amount,message.autoStop);
        if (accounts.balanceOf(id)<message.amount) throw new CrashError('Недостаточно средств');
        accounts.withdraw(id,message.amount);
        try { game.start(message.amount,message.autoStop,message.revision,now); }
        catch(error) { accounts.deposit(id,message.amount); throw error; }
        save(id,game); resolve(id,game,now);
      } else if (message.type==='cr_cashout') {
        game.cashout(message.revision,now); resolve(id,game,now); save(id,game);
      }
    } catch(error) { resolve(id,game,now); send(client,game,now); throw error; }
    send(client,game,now);
  }
  const timer=setInterval(()=>{
    const now=Date.now();
    for(const [id,game] of games) {
      if(game.phase!=='play' && game.settled) continue;
      resolve(id,game,now);
      const client=clients.get(id);
      if(client?.watchingCrash) send(client,game,now);
    }
  },100);
  timer.unref();
  function stop() {
    clearInterval(timer);
    for(const [id,game] of games) { resolve(id,game,Date.now()); save(id,game); }
  }
  return { handle, stop };
}
module.exports={ createCrashService };
