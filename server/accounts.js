'use strict';

const fs = require('fs');
const path = require('path');

const { formatMoney } = require('./money');

// Баланс игрока — отдельная сущность, не связанная со столом.
// Деньги со стола и на стол переезжают только через сесть / встать / пополнить.
//
// Все суммы здесь — целые центы (см. money.js): $100.00 хранится как 10000.

const DEFAULT_START_BALANCE = 10000; // $100.00
const MAX_BALANCE = 1000000000; // $10 000 000.00

class AccountError extends Error {}

class Accounts {
  constructor({ file = null, startingBalance = DEFAULT_START_BALANCE, admins = [] } = {}) {
    this.file = file;
    this.startingBalance = Math.max(0, Math.floor(startingBalance));
    this.admins = new Set(admins.map((id) => String(id).trim()).filter(Boolean));
    this.accounts = new Map();
    this.saveTimer = null;
    this.onChange = null; // сюда сообщаем, чей баланс изменился
    if (file) this.load();
  }

  isAdmin(userId) {
    return this.admins.has(String(userId));
  }

  // ——— Хранение ———

  load() {
    try {
      const raw = fs.readFileSync(this.file, 'utf8');
      const parsed = JSON.parse(raw);
      for (const account of parsed.accounts || []) {
        this.accounts.set(String(account.id), {
          id: String(account.id),
          name: account.name || 'Игрок',
          username: account.username || null,
          balance: Math.max(0, Math.floor(Number(account.balance) || 0)),
          createdAt: account.createdAt || Date.now(),
        });
      }
    } catch (error) {
      if (error.code !== 'ENOENT') {
        console.error('Не удалось прочитать балансы, начинаем с чистого листа:', error.message);
      }
    }
  }

  // Пишем через временный файл, чтобы не оставить обрезанный JSON при падении.
  flush() {
    if (!this.file) return;
    if (this.saveTimer) {
      clearTimeout(this.saveTimer);
      this.saveTimer = null;
    }
    const payload = JSON.stringify({ accounts: [...this.accounts.values()] }, null, 2);
    try {
      fs.mkdirSync(path.dirname(this.file), { recursive: true });
      const temporary = `${this.file}.tmp`;
      fs.writeFileSync(temporary, payload);
      fs.renameSync(temporary, this.file);
    } catch (error) {
      console.error('Не удалось сохранить балансы:', error.message);
    }
  }

  scheduleSave() {
    if (!this.file || this.saveTimer) return;
    this.saveTimer = setTimeout(() => {
      this.saveTimer = null;
      this.flush();
    }, 400);
    this.saveTimer.unref?.();
  }

  // ——— Счета ———

  ensure(user) {
    const id = String(user.id);
    let account = this.accounts.get(id);
    if (!account) {
      account = {
        id,
        name: user.name || 'Игрок',
        username: user.username || null,
        balance: this.startingBalance,
        createdAt: Date.now(),
      };
      this.accounts.set(id, account);
      this.scheduleSave();
      return account;
    }
    // Имя и ник могли смениться в Telegram — подтягиваем свежие.
    if (user.name && user.name !== account.name) {
      account.name = user.name;
      this.scheduleSave();
    }
    if (user.username !== undefined && user.username !== account.username) {
      account.username = user.username || null;
      this.scheduleSave();
    }
    return account;
  }

  get(userId) {
    return this.accounts.get(String(userId)) || null;
  }

  balanceOf(userId) {
    const account = this.get(userId);
    return account ? account.balance : 0;
  }

  // Ищем по Telegram ID или по @нику. По имени специально не ищем:
  // имена повторяются, и промахнуться легко.
  find(query) {
    const text = String(query || '').trim();
    if (!text) return null;
    if (text.startsWith('@')) {
      const username = text.slice(1).toLowerCase();
      return [...this.accounts.values()].find((a) => (a.username || '').toLowerCase() === username) || null;
    }
    return this.get(text);
  }

  withdraw(userId, amount) {
    const account = this.get(userId);
    const value = Math.floor(amount);
    if (!account) throw new AccountError('Счёт не найден');
    if (value <= 0) throw new AccountError('Некорректная сумма');
    if (account.balance < value) {
      throw new AccountError(`На балансе не хватает денег: нужно ${formatMoney(value)}, есть ${formatMoney(account.balance)}`);
    }
    account.balance -= value;
    this._changed(account);
    return account.balance;
  }

  deposit(userId, amount) {
    const account = this.get(userId);
    const value = Math.floor(amount);
    if (!account || value <= 0) return account ? account.balance : 0;
    account.balance = Math.min(MAX_BALANCE, account.balance + value);
    this._changed(account);
    return account.balance;
  }

  // Выдача и списание администратором. mode: 'add' | 'set'.
  grant(targetQuery, amount, mode = 'add') {
    const account = this.find(targetQuery);
    if (!account) throw new AccountError(`Игрок «${targetQuery}» не найден. Нужен Telegram ID или @ник`);

    const value = Math.floor(Number(amount));
    if (!Number.isFinite(value)) throw new AccountError('Укажите сумму числом');

    const target = mode === 'set' ? value : account.balance + value;
    if (target < 0) throw new AccountError(`У игрока столько нет: на балансе ${formatMoney(account.balance)}`);
    if (target > MAX_BALANCE) throw new AccountError('Слишком большой баланс');

    const delta = target - account.balance;
    account.balance = target;
    this._changed(account);
    return { account, delta };
  }

  list(limit = 50) {
    return [...this.accounts.values()]
      .sort((a, b) => b.balance - a.balance)
      .slice(0, limit)
      .map((a) => ({ id: a.id, name: a.name, username: a.username, balance: a.balance }));
  }

  _changed(account) {
    this.scheduleSave();
    if (this.onChange) this.onChange(account);
  }
}

module.exports = { Accounts, AccountError, DEFAULT_START_BALANCE };
