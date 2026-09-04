'use strict';

const fs = require('fs');
const path = require('path');

const { formatMoney } = require('./money');

// Промокоды. Код создаёт админ, игрок вводит его на главной и получает
// сумму на баланс.
//
// Это единственное место кроме пополнения, где деньги появляются из воздуха,
// поэтому правила жёсткие: выдаёт только админ, у кода есть лимит активаций,
// и один игрок активирует код ровно один раз.

const MAX_CODE_LENGTH = 32;
const MAX_ACTIVATIONS = 100000;

class PromoError extends Error {}

// Коды сравниваем без учёта регистра и лишних пробелов: игрок набирает их
// руками, и «  bonus » должен сработать так же, как «BONUS».
const normalizeCode = (code) => String(code || '').trim().toUpperCase().replace(/\s+/g, '');

class PromoCodes {
  constructor({ accounts, file = null } = {}) {
    if (!accounts) throw new PromoError('Промокодам нужен доступ к счетам');
    this.accounts = accounts;
    this.file = file;
    this.codes = new Map(); // КОД -> запись
    this.saveTimer = null;
    this.onRedeem = null;
    if (file) this.load();
  }

  // ——— Хранение ———

  load() {
    try {
      const parsed = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      for (const record of parsed.codes || []) {
        if (!record || !record.code) continue;
        this.codes.set(normalizeCode(record.code), {
          ...record,
          code: normalizeCode(record.code),
          usedBy: Array.isArray(record.usedBy) ? record.usedBy.map(String) : [],
        });
      }
    } catch (error) {
      if (error.code !== 'ENOENT') {
        console.error('Не удалось прочитать промокоды:', error.message);
      }
    }
  }

  flush() {
    if (!this.file) return;
    if (this.saveTimer) {
      clearTimeout(this.saveTimer);
      this.saveTimer = null;
    }
    try {
      fs.mkdirSync(path.dirname(this.file), { recursive: true });
      const temporary = `${this.file}.tmp`;
      fs.writeFileSync(temporary, JSON.stringify({ codes: [...this.codes.values()] }, null, 2));
      fs.renameSync(temporary, this.file);
    } catch (error) {
      console.error('Не удалось сохранить промокоды:', error.message);
    }
  }

  // Активации пишем сразу: между «начислили» и «записали» не должно быть
  // окна, иначе падение процесса позволит активировать код второй раз.
  scheduleSave() {
    if (!this.file || this.saveTimer) return;
    this.saveTimer = setTimeout(() => {
      this.saveTimer = null;
      this.flush();
    }, 400);
    this.saveTimer.unref?.();
  }

  // ——— Выдача ———

  create({ code, cents, maxActivations = 1, createdBy = null }) {
    const key = normalizeCode(code);
    if (!key) throw new PromoError('Укажите код');
    if (key.length > MAX_CODE_LENGTH) throw new PromoError(`Код длиннее ${MAX_CODE_LENGTH} символов`);
    if (!/^[A-Z0-9_-]+$/.test(key)) throw new PromoError('В коде можно использовать латиницу, цифры, дефис и подчёркивание');
    if (this.codes.has(key)) throw new PromoError(`Код «${key}» уже существует`);

    const value = Math.floor(Number(cents));
    if (!Number.isFinite(value) || value <= 0) throw new PromoError('Укажите сумму больше нуля');

    const limit = Math.floor(Number(maxActivations));
    if (!Number.isFinite(limit) || limit <= 0) throw new PromoError('Число активаций должно быть больше нуля');
    if (limit > MAX_ACTIVATIONS) throw new PromoError('Слишком много активаций');

    const record = {
      code: key,
      cents: value,
      maxActivations: limit,
      usedBy: [],
      createdAt: Date.now(),
      createdBy: createdBy ? String(createdBy) : null,
    };
    this.codes.set(key, record);
    this.flush();
    return record;
  }

  remove(code) {
    const key = normalizeCode(code);
    if (!this.codes.has(key)) throw new PromoError(`Код «${key}» не найден`);
    this.codes.delete(key);
    this.flush();
    return key;
  }

  list() {
    return [...this.codes.values()]
      .sort((a, b) => b.createdAt - a.createdAt)
      .map((record) => ({
        code: record.code,
        cents: record.cents,
        used: record.usedBy.length,
        maxActivations: record.maxActivations,
      }));
  }

  // ——— Активация ———

  redeem(user, code) {
    const key = normalizeCode(code);
    if (!key) throw new PromoError('Введите промокод');

    const record = this.codes.get(key);
    // Про несуществующий и про исчерпанный код отвечаем по-разному:
    // подобрать чужой код это всё равно не помогает, а игроку понятнее.
    if (!record) throw new PromoError('Такого промокода нет');

    const userId = String(user.id);
    if (record.usedBy.includes(userId)) throw new PromoError('Вы уже активировали этот промокод');
    if (record.usedBy.length >= record.maxActivations) throw new PromoError('Промокод уже разобрали');

    record.usedBy.push(userId);
    this.accounts.ensure({ id: userId, name: user.name, username: user.username });
    const balance = this.accounts.deposit(userId, record.cents);
    // Сначала на диск, потом уже отвечаем игроку: иначе перезапуск сервера
    // между этими шагами вернёт коду одну «свободную» активацию.
    this.flush();

    if (this.onRedeem) this.onRedeem({ userId, code: key, cents: record.cents });
    return { code: key, cents: record.cents, balance, text: `Промокод активирован: +${formatMoney(record.cents)}` };
  }
}

module.exports = { PromoCodes, PromoError, normalizeCode };
