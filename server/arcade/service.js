'use strict';
const { ArcadeError, GAMES, config, initial, start, actGame, publicState } = require('./game');
const { MAX_BALANCE } = require('../accounts');

function createArcadeService({ accounts, noteWin, rng, isAdmin = user => accounts.isAdmin?.(user.id) === true }) {
  function handle(client, message) {
    const game = message.game;
    if (!GAMES.includes(game)) throw new ArcadeError('Игра не найдена');
    const account = accounts.get(client.user.id);
    const oldRounds = account.arcadeRounds;
    const previous = oldRounds?.[game] || initial();
    let next = previous;
    let balance = account.balance;
    let newlyPaid = false;
    try {
      if (message.type === 'ag_start') {
        if (game === 'abyss' && message.options?.testMax && !isAdmin(client.user)) throw new ArcadeError('Тест бонуса доступен только администратору');
        if (!Number.isSafeInteger(message.amount) || balance < message.amount) throw new ArcadeError('Недостаточно средств или неверная сумма');
        next = start(game, previous, message.amount, message.options, message.revision, rng);
        if (balance < next.bet) throw new ArcadeError(game==='abyss'?'Недостаточно средств для покупки бонуса':'Недостаточно средств на все шарики');
        balance -= next.bet;
      } else if (message.type === 'ag_pick' || message.type === 'ag_cashout') {
        next = actGame(game, previous, message.type, message.index, message.revision, rng);
      } else if (message.type !== 'ag_open') throw new ArcadeError('Неизвестное действие');
      if (next.phase === 'done' && !next.settled && balance + next.payout <= MAX_BALANCE) {
        next = { ...next, settled: true };
        balance += next.payout;
        newlyPaid = true;
      }
      if (next !== previous) {
        const before = account.balance;
        account.arcadeRounds = { ...oldRounds, [game]: next };
        account.balance = balance;
        try { accounts.flush({ strict: true }); }
        catch (error) {
          account.arcadeRounds = oldRounds; account.balance = before;
          throw new ArcadeError('Не удалось сохранить действие. Баланс и раунд не изменены — попробуйте позже');
        }
        // Notify only after the wallet and result have been saved together.
        if (before !== balance) accounts.onChange?.(account);
        if (newlyPaid && next.payout > next.bet) noteWin({ userId: account.id, name: account.name, amount: next.payout - next.bet, game, code: 'AG' });
      }
      client.send({ type: 'ag', game, requestId: message.requestId, accepted: true, config: config(game), ...publicState(game, next), balance: account.balance });
    } catch (error) {
      client.send({ type: 'ag', game, requestId: message.requestId, accepted: false, config: config(game), ...publicState(game, account.arcadeRounds?.[game] || previous), balance: account.balance });
      throw error;
    }
  }
  return { handle };
}
module.exports = { createArcadeService };
