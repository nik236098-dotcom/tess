'use strict';
const crypto = require('crypto');
const { AccountError, MAX_BALANCE } = require('./accounts');
const PRIVATE_SLOTS = new Set(['abyss', 'cryo', 'midnight']);
const RATE = 10;
const PAGE_SIZE = 30;

class Activity {
  constructor({ accounts, payments, botUsername = '' }) {
    this.accounts = accounts; this.payments = payments; this.botUsername = botUsername;
  }
  get data() { return this.accounts.finance; }
  enqueue(kind, payload, key) {
    const id = key || crypto.randomUUID();
    if (!this.data.outbox.some(e => e.id === id)) this.data.outbox.push({ id, kind, payload, at: Date.now(), delivered: false });
  }
  register(user, startParam) {
    return this.accounts.atomic(() => {
      const existing = this.accounts.get(user.id);
      const account = this.accounts.ensure(user);
      if (!existing) {
        const parentId = /^ref_(\d+)$/.exec(String(startParam || ''))?.[1];
        if (parentId && parentId !== account.id && this.accounts.get(parentId)) account.referrerId = parentId;
        this.enqueue('registration', { userId: account.id, name: account.name, username: account.username }, 'user:' + account.id);
      }
      return account;
    });
  }
  round(input) {
    return this.accounts.atomic(() => {
      const account = this.accounts.get(input.userId);
      if (!account) return null; // bots have no cash wallet
      const { bet, payout } = input;
      if (!Number.isSafeInteger(bet) || bet < 0 || !Number.isSafeInteger(payout) || payout < 0) throw new AccountError('Некорректный результат ставки');
      const id = input.id || crypto.randomUUID();
      if (this.data.rounds.some(r => r.id === id)) return null;
      const row = { id, userId: account.id, name: account.name, username: account.username,
        game: input.game, bet, payout, net: payout - bet, multiplier: bet ? payout / bet : 0,
        result: payout > bet ? 'win' : payout < bet ? 'lose' : 'push', at: Date.now(),
        houseRevenue: ['holdem', 'omaha', 'table-blackjack'].includes(input.game) ? 0 : bet - payout,
        commission: 0, referrerId: account.referrerId || null };
      if (account.referrerId && row.houseRevenue !== 0) {
        const parent = this.accounts.get(account.referrerId);
        if (parent) {
          account.refRevenue = (account.refRevenue || 0) + row.houseRevenue;
          const target = Math.floor(Math.max(0, account.refRevenue) * RATE / 100);
          row.commission = Math.max(0, target - (account.refEarned || 0));
          account.refEarned = (account.refEarned || 0) + row.commission;
          parent.refBalance = (parent.refBalance || 0) + row.commission;
          this.accounts._changed(parent);
        }
      }
      this.data.rounds.push(row);
      this.enqueue('game', row, 'game:' + id);
      return row;
    });
  }
  claim(userId) {
    return this.accounts.atomic(() => {
      const account = this.accounts.get(userId), value = account?.refBalance || 0;
      if (!value) throw new AccountError('Нет доступных начислений');
      if (account.balance + value > MAX_BALANCE) throw new AccountError('Превышен лимит баланса');
      account.balance += value; account.refBalance = 0;
      const row = { id: crypto.randomUUID(), kind: 'referral', userId: account.id, cents: value, status: 'done', createdAt: Date.now() };
      this.data.transfers.push(row); this.accounts._changed(account);
      return row;
    });
  }
  history(userId, { page = 0, game = '' } = {}) {
    const rows = this.data.rounds.filter(r => r.userId === String(userId) && (!game || r.game === game)).reverse();
    const offset = Math.max(0, Math.floor(Number(page) || 0)) * PAGE_SIZE;
    return { rows: rows.slice(offset, offset + PAGE_SIZE), more: rows.length > offset + PAGE_SIZE, total: rows.length };
  }
  transactions(userId, page = 0) {
    const rows = [...this.payments.historyFor(userId, Number.MAX_SAFE_INTEGER), ...this.data.transfers.filter(t => t.userId === String(userId))]
      .sort((a, b) => b.createdAt - a.createdAt);
    const offset = Math.max(0, Math.floor(Number(page) || 0)) * PAGE_SIZE;
    return { rows: rows.slice(offset, offset + PAGE_SIZE), more: rows.length > offset + PAGE_SIZE, total: rows.length };
  }
  referrals(userId, { since = 0, query = '', page = 0, limit = PAGE_SIZE } = {}) {
    limit = Math.max(1, Math.min(PAGE_SIZE, Math.floor(Number(limit) || PAGE_SIZE)));
    const all = [...this.accounts.accounts.values()].filter(a => a.referrerId === String(userId));
    const paid = [...this.payments.invoices.values()].filter(i => i.status === 'paid' && i.creditedAt >= since);
    const rounds = this.data.rounds.filter(r => r.referrerId === String(userId) && r.at >= since);
    const rows = all.map(a => {
      const deposits = paid.filter(i => i.userId === a.id);
      const results = rounds.filter(r => r.userId === a.id);
      return { id: a.id, name: a.name, username: a.username, createdAt: a.createdAt,
        deposits: deposits.reduce((s, i) => s + i.creditedCents, 0), depositCount: deposits.length,
        revenue: results.reduce((s, r) => s + r.houseRevenue, 0), earned: results.reduce((s, r) => s + r.commission, 0),
        lastDeposit: Math.max(0, ...deposits.map(i => i.creditedAt)), carry: Math.max(0, Math.ceil((a.refEarned || 0) * 100 / RATE) - (a.refRevenue || 0)) };
    }).sort((a, b) => b.createdAt - a.createdAt);
    const filtered = rows.filter(r => `${r.name} ${r.username || ''} ${r.id}`.toLowerCase().includes(String(query).toLowerCase().slice(0, 80)));
    const offset = Math.max(0, Math.floor(Number(page) || 0)) * limit;
    return { rate: RATE, balance: this.accounts.get(userId)?.refBalance || 0, count: all.length,
      deposits: rows.reduce((s, r) => s + r.deposits, 0), earned: rows.reduce((s, r) => s + r.earned, 0),
      link: this.botUsername ? `https://t.me/${this.botUsername}?start=ref_${userId}` : null,
      rows: filtered.slice(offset, offset + limit), more: filtered.length > offset + limit };
  }
  cash(since = 0) {
    const sum = (rows, key) => rows.reduce((s, row) => s + (row[key] || 0), 0);
    const rounds = this.data.rounds.filter(r => r.at >= since);
    const deposits = [...this.payments.invoices.values()].filter(i => i.status === 'paid' && i.creditedAt >= since);
    const payouts = [...this.payments.payouts.values()].filter(p => p.status === 'done' && p.finishedAt >= since);
    const incoming = sum(deposits, 'creditedCents'), outgoing = sum(payouts, 'cents');
    const gameRevenue = sum(rounds, 'houseRevenue'), commissions = sum(rounds, 'commission');
    return { incoming, outgoing, cashFlow: incoming - outgoing, gameRevenue, commissions,
      // Operating expenses, taxes and fees are not known by this application.
      result: gameRevenue - commissions, bets: sum(rounds, 'bet'), wins: sum(rounds, 'payout'),
      pending: sum([...this.payments.payouts.values()].filter(p => ['pending', 'review', 'unknown'].includes(p.status)), 'cents') };
  }
}
module.exports = { Activity, PRIVATE_SLOTS, RATE, PAGE_SIZE };
