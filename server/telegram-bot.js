'use strict';
const perf = require('./diagnostics');
const fs = require('fs');
const path = require('path');
const { formatMoney } = require('./money');
const esc = v => String(v ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const amount = value => esc(formatMoney(value || 0));
const date = value => new Date(value).toLocaleString('ru-RU', { timeZone: 'UTC', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
const userLine = a => `${esc(a.name || a.userName || 'Игрок')}${a.username || a.userUsername ? ' @' + esc(a.username || a.userUsername) : ''}\nID: <code>${esc(a.id || a.userId)}</code>`;
const statusName = s => ({ review: 'В обработке', pending: 'В обработке', unknown: 'Требует проверки', done: 'Успешно', failed: 'Отказано', paid: 'Успешно', expired: 'Истёк' }[s] || s);
const button = (text, callback_data) => ({ text, callback_data });
function periodStart(period, now = Date.now()) {
  const d = new Date(now); d.setUTCHours(0, 0, 0, 0);
  if (period === 'week') d.setUTCDate(d.getUTCDate() - 6);
  return period === 'all' ? 0 : d.getTime();
}
class TelegramBot {
  constructor({ token, accounts, payments, activity, appUrl = '', supportUrl = '', env = process.env, call = null }) {
    Object.assign(this, { token, accounts, payments, activity, appUrl, supportUrl, env });
    this.transport = call; this.running = false; this.sending = false; this.controller = null;
    this.channelRetry = new Map();
    this.channels = { payouts: env.TELEGRAM_PAYOUTS_CHAT_ID, events: env.TELEGRAM_EVENTS_CHAT_ID, games: env.TELEGRAM_GAMES_CHAT_ID };
  }
  async call(method, body = {}) {
    // Successful long polling intentionally waits up to 25 seconds.
    const finish = method === 'getUpdates' ? () => {} : perf.begin('telegram.' + method, 1000);
    try {
      if (this.transport) return await this.transport(method, body);
      const signal = AbortSignal.timeout(method === 'getUpdates' ? 35000 : 12000);
      const response = await fetch(`https://api.telegram.org/bot${this.token}/${method}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal,
      });
      const data = await response.json();
      if (!data.ok) { const e = new Error(`${method}: ${data.description || response.status}`); e.retryAfter = data.parameters?.retry_after; e.telegramCode = data.error_code || response.status; throw e; }
      return data.result;
    } finally { finish(); }
  }
  url(page = '') {
    if (!this.appUrl) return null;
    const u = new URL(this.appUrl); if (page) u.searchParams.set('screen', page); return u.href;
  }
  web(text, page) {
    const url = this.url(page);
    return url ? { text, web_app: { url } } : button(text, 'unavailable');
  }
  keyboard() {
    return { inline_keyboard: [[this.web('🎮 Играть', '')], [button('👤 Профиль', 'profile'), button('🤝 Рефералы', 'referrals')], [button('🎧 Поддержка', 'support')]] };
  }
  async say(chat, text, keyboard) { return this.call('sendMessage', { chat_id: chat, text, parse_mode: 'HTML', ...(keyboard ? { reply_markup: keyboard } : {}) }); }
  rememberScreen(chat, message, photo = false) {
    const account = this.accounts.get(String(chat));
    if (!account || !Number.isInteger(message?.message_id)) return;
    account.botScreen = { messageId: message.message_id, photo };
    this.accounts.scheduleSave();
  }
  async screen(chat, text, keyboard = { inline_keyboard: [] }) {
    const account = this.accounts.get(String(chat));
    if (!account || Number(chat) <= 0) return this.say(chat, text, keyboard);
    const rows = keyboard.inline_keyboard || [];
    const markup = { inline_keyboard: rows.some(row => row.some(k => k.callback_data === 'home'))
      ? rows : [...rows, [button('‹ Главное меню', 'home')]] };
    const current = account.botScreen;
    // Telegram captions are limited to 1024 characters. Long admin reports
    // migrate once to a text screen; subsequent navigation edits that screen.
    if (current && (!current.photo || text.length <= 1024)) {
      try {
        return await this.call(current.photo ? 'editMessageCaption' : 'editMessageText', {
          chat_id: chat, message_id: current.messageId, parse_mode: 'HTML', reply_markup: markup,
          ...(current.photo ? { caption: text } : { text }),
        });
      } catch (error) {
        if (/message is not modified/i.test(error.message)) return;
        // Do not duplicate messages on timeouts, rate limits or ambiguous failures.
        if (!/message to edit not found|message can(?:not|'t) be edited|there is no text in the message to edit/i.test(error.message)) throw error;
      }
    }
    const result = await this.say(chat, text, markup);
    this.rememberScreen(chat, result);
    if (current && result?.message_id !== current.messageId) {
      try { await this.call('deleteMessage', { chat_id: chat, message_id: current.messageId }); }
      catch { /* An old/deleted message must not prevent the new screen from working. */ }
    }
    return result;
  }
  async welcome(chat, account) {
    const caption = `<b>Добро пожаловать в Croco, ${esc(account.name)}!</b>\n\nИгры, кошелёк и твоя реферальная программа — в одном месте.`;
    const keyboard = this.keyboard();
    if (account.botScreen) return this.screen(chat, caption, keyboard);
    // Upload bundled artwork; Telegram sendPhoto does not accept WebP photos.
    if (this.transport) {
      const result = await this.call('sendPhoto', { chat_id: chat, photo: 'bundled:croco-welcome.jpg', caption, parse_mode: 'HTML', reply_markup: keyboard });
      this.rememberScreen(chat, result, true);
      return result;
    }
    const file = path.join(__dirname, '..', 'public', 'img', 'croco', 'bot-welcome.jpg');
    const form = new FormData(); form.set('chat_id', String(chat)); form.set('caption', caption); form.set('parse_mode', 'HTML'); form.set('reply_markup', JSON.stringify(keyboard));
    form.set('photo', new Blob([fs.readFileSync(file)], { type: 'image/jpeg' }), 'croco.jpg');
    const finishPhoto = perf.begin('telegram.sendPhoto', 1000);
    let data;
    try {
      const response = await fetch(`https://api.telegram.org/bot${this.token}/sendPhoto`, { method: 'POST', body: form, signal: AbortSignal.timeout(15000) });
      data = await response.json();
    } finally { finishPhoto(); }
    if (!data.ok) return this.screen(chat, caption, keyboard);
    this.rememberScreen(chat, data.result, true);
    return data.result;
  }
  async profile(chat, account) {
    return this.screen(chat, `<b>👤 Профиль Croco</b>\n\n${userLine(account)}\n\nКошелёк: <b>${amount(account.balance)}</b>\nРеферальный баланс: <b>${amount(account.refBalance)}</b>`,
      { inline_keyboard: [[this.web('↓ Пополнить', 'wallet'), this.web('↑ Вывести', 'withdraw')], [button('🤝 Рефералы', 'referrals')], [button('🎧 Поддержка', 'support'), this.web('🎮 Играть', '')]] });
  }
  async refReport(chat, id, page = 0) {
    const a = this.accounts.get(id); if (!a) throw new Error('Игрок не найден');
    const r = this.activity.referrals(id, { page, limit: 10 });
    let text = `<b>🤝 Рефералы</b>\n${userLine(a)}\n\nСтавка: <b>10% от игрового дохода проекта</b>\nДоступно: <b>${amount(r.balance)}</b>\nПриглашено: <b>${r.count}</b>\nДепозиты: <b>${amount(r.deposits)}</b>\nЗаработано: <b>${amount(r.earned)}</b>\n`;
    if (r.link) text += `\nСсылка: <code>${esc(r.link)}</code>\n`;
    for (const row of r.rows.slice(0, 10)) text += `\n${esc(row.name)} · <code>${esc(row.id)}</code>\nДепозиты ${amount(row.deposits)} · доход ${amount(row.earned)}`;
    const keys = []; if (page > 0) keys.push(button('←', `ref:${id}:${page - 1}`)); if (r.more) keys.push(button('Далее →', `ref:${id}:${page + 1}`));
    return this.screen(chat, text, { inline_keyboard: [keys, [...(String(chat) === String(id) ? [button('Забрать на баланс', 'claim')] : []), this.web('Открыть бонусы', 'bonuses')]].filter(a => a.length) });
  }
  async report(chat, kind, id, page = 0) {
    const a = this.accounts.get(id); if (!a) throw new Error('Игрок не найден');
    // Ten items per Telegram page; do not silently truncate user history.
    const all = kind === 'stats' ? this.activity.data.rounds.filter(r => r.userId === String(id)).slice().reverse()
      : [...this.payments.historyFor(id, Number.MAX_SAFE_INTEGER), ...this.activity.data.transfers.filter(r => r.userId === String(id))].sort((a, b) => b.createdAt - a.createdAt);
    const offset = Math.max(0, page) * 10, rows = all.slice(offset, offset + 10);
    let text = `<b>${kind === 'stats' ? '🎮 История ставок' : '💳 История операций'}</b>\n${userLine(a)}\nВсего: ${all.length}\n`;
    for (const r of rows) text += kind === 'stats'
      ? `\n${esc(r.game)} · ${date(r.at)}\nСтавка ${amount(r.bet)} · ${r.multiplier.toFixed(2)}×\nВыплата ${amount(r.payout)} · результат <b>${amount(r.net)}</b>\n`
      : `\n${r.kind === 'topup' ? '↓ Пополнение' : r.kind === 'referral' ? '🤝 Реферальный перевод' : '↑ Вывод'} · ${date(r.createdAt)}\n${amount(r.creditedCents || r.cents)} · ${esc(statusName(r.status))}\n`;
    if (!rows.length) text += '\nЗаписей пока нет.';
    const keys = []; if (page) keys.push(button('← Назад', `${kind}:${id}:${page - 1}`)); if (offset + 10 < all.length) keys.push(button('Далее →', `${kind}:${id}:${page + 1}`));
    return this.screen(chat, text, { inline_keyboard: keys.length ? [keys] : [] });
  }
  async kassa(chat, period = 'today') {
    const r = this.activity.cash(periodStart(period));
    const label = { today: 'Сегодня', week: 'Последние 7 дней', all: 'Всё время' }[period] || 'Сегодня';
    return this.screen(chat, `<b>🏦 Касса · ${label}</b>\n<i>Границы дня — UTC</i>\n\nПополнения: <b>${amount(r.incoming)}</b>\nВыплаченные выводы: <b>${amount(r.outgoing)}</b>\nДенежный поток: <b>${amount(r.cashFlow)}</b>\nЗаявки в обработке: ${amount(r.pending)}\n\nСтавки: ${amount(r.bets)}\nИгровые выплаты: ${amount(r.wins)}\nИгровой доход проекта: ${amount(r.gameRevenue)}\nРеферальные начисления: ${amount(r.commissions)}\n<b>${r.result >= 0 ? 'Результат +' : 'Убыток '}${amount(r.result)}</b>\n<i>До расходов, бонусов, комиссий и налогов; пополнения не считаются прибылью.</i>`,
      { inline_keyboard: [[button('Сегодня', 'kassa:today'), button('Неделя', 'kassa:week'), button('Всё время', 'kassa:all')], [button('↻ Обновить', `kassa:${period}`)]] });
  }
  payoutText(r) { return `<b>↑ Заявка на вывод · ${esc(statusName(r.status))}</b>\n\n${userLine({ ...r, id: r.userId })}\nСумма: <b>${amount(r.cents)}</b>\nСервис: ${esc(r.provider)} · ${esc(r.currency)}\nЗаявка: <code>${esc(r.id)}</code>\n${date(r.createdAt)} UTC${r.status === 'review' ? '\n\n«Выплачено» подтверждает выполненный вручную перевод.' : ''}`; }
  async handle(update) {
    const q = update.callback_query, m = update.message;
    const from = q?.from || m?.from; if (!from || from.is_bot) return;
    const id = String(from.id), chat = q?.message?.chat || m?.chat;
    if (!chat) return;
    const admin = this.accounts.isAdmin(id);
    try {
      if (q) {
        try { await this.call('answerCallbackQuery', { callback_query_id: q.id }); }
        catch (error) {
          // A queued click can outlive Telegram's acknowledgement window.
          // Still validate the sender, channel and payout status below.
          if (!/query is too old|query ID is invalid|query_id_invalid/i.test(error.message)) throw error;
        }
        const [action, arg, rawPage] = String(q.data || '').split(':');
        if (action === 'pay') {
          if (!admin) throw new Error('Только для администратора');
          const channel = this.activity.data.channels.payouts || this.channels.payouts;
          if (!channel || String(chat.id) !== String(channel)) throw new Error('Кнопка доступна только в канале выводов');
          const r = this.payments.getPayout(arg);
          if (!r) throw new Error('Заявка не найдена');
          if (r.status === 'review') this.payments.reviewPayout(arg, rawPage, id);
          else if (!['done', 'failed'].includes(r.status)) throw new Error('Заявка пока не доступна для ручного подтверждения');
          try { await this.call('editMessageText', { chat_id: chat.id, message_id: q.message.message_id, text: this.payoutText(r), parse_mode: 'HTML', reply_markup: { inline_keyboard: [] } }); }
          catch (error) { if (!/message is not modified/i.test(error.message)) throw error; }
          return;
        }
        if (chat.type !== 'private') return;
        const a = this.activity.register({ id, name: [from.first_name, from.last_name].filter(Boolean).join(' '), username: from.username });
        // Only private navigation callbacks can select the message to edit.
        // Prefer the saved screen if a user taps an obsolete menu.
        if (!a.botScreen) this.rememberScreen(chat.id, q.message, Boolean(q.message.photo?.length));
        if (action === 'home') return await this.welcome(chat.id, a);
        if (['stats', 'balance', 'ref'].includes(action)) {
          if (!admin && arg !== id) throw new Error('Нет доступа');
          const page = Math.max(0, Math.min(100000, Number(rawPage) || 0));
          return await (action === 'ref' ? this.refReport(chat.id, arg, page) : this.report(chat.id, action, arg, page));
        }
        if (action === 'kassa') { if (!admin) throw new Error('Только для администратора'); return await this.kassa(chat.id, arg); }
        if (action === 'profile') return await this.profile(chat.id, a);
        if (action === 'referrals' || action === 'referrals_app') return await this.refReport(chat.id, id);
        if (action === 'claim') { const row = this.activity.claim(id); return await this.screen(chat.id, `✅ На основной баланс переведено ${amount(row.cents)}`, this.keyboard()); }
        if (action === 'support') return await this.screen(chat.id, '🎧 Поддержка Croco\nУкажите ID профиля и номер операции при обращении.', { inline_keyboard: this.supportUrl ? [[{ text: 'Написать в поддержку', url: this.supportUrl }]] : [] });
        return await this.screen(chat.id, 'Откройте приложение кнопкой меню бота.', this.keyboard());
      }
      if (!m?.text) return;
      const [raw, arg, third] = m.text.trim().split(/\s+/); const command = raw.split('@')[0].toLowerCase();
      if (command === '/chatid' && admin) return await this.screen(chat.id, `ID чата: <code>${chat.id}</code>`);
      if (chat.type !== 'private') return;
      const a = this.activity.register({ id, name: [from.first_name, from.last_name].filter(Boolean).join(' '), username: from.username }, command === '/start' ? arg : null);
      if (command === '/start') return await this.welcome(chat.id, a);
      if (command === '/profile') return await this.profile(chat.id, a);
      if (command === '/wallet') return await this.screen(chat.id, `<b>Кошелёк: ${amount(a.balance)}</b>`, { inline_keyboard: [[this.web('Пополнить', 'wallet'), this.web('Вывести', 'withdraw')]] });
      if (command === '/ref' && !arg) return await this.refReport(chat.id, id);
      if (command === '/support') return await this.screen(chat.id, '🎧 Поддержка Croco', { inline_keyboard: this.supportUrl ? [[{ text: 'Написать', url: this.supportUrl }]] : [] });
      if (['/stats', '/balance', '/ref'].includes(command)) {
        if (!admin) throw new Error('Команда только для администратора');
        if (!/^\d+$/.test(arg || '')) throw new Error(`Использование: ${command} Telegram_ID`);
        return await (command === '/ref' ? this.refReport(chat.id, arg) : this.report(chat.id, command.slice(1), arg));
      }
      if (command === '/kassa') { if (!admin) throw new Error('Команда только для администратора'); return await this.kassa(chat.id); }
      if (command === '/setchannel') {
        if (!admin) throw new Error('Команда только для администратора');
        if (!['payouts', 'events', 'games'].includes(arg) || !/^-\d+$/.test(third || '')) throw new Error('/setchannel payouts|events|games -100…');
        let found;
        try { found = await this.call('getChat', { chat_id: third }); }
        catch (error) {
          if (!/chat not found/i.test(error.message)) throw error;
          throw new Error('Канал не найден. Проверьте ID с -100 и добавьте этого бота администратором канала, затем повторите /setchannel.');
        }
        if (!['channel', 'supergroup', 'group'].includes(found.type)) throw new Error('Укажите канал или группу');
        const me = await this.call('getMe');
        const member = await this.call('getChatMember', { chat_id: third, user_id: me.id });
        if (!['administrator', 'creator'].includes(member.status) || (found.type === 'channel' && member.can_post_messages === false)) throw new Error('Сначала добавьте бота администратором канала с правом публикации');
        this.accounts.atomic(() => { this.activity.data.channels[arg] = third; });
        this.channelRetry.delete(String(third));
        return await this.screen(chat.id, `✅ Канал ${esc(arg)} подключён: ${esc(found.title)}\nСохранённые уведомления будут отправлены сюда.`);
      }
      return await this.screen(chat.id, '/profile — профиль\n/wallet — кошелёк\n/ref — рефералы\n/support — поддержка' + (admin ? '\n\nАдминистратор:\n/stats id — ставки\n/balance id — операции\n/ref id — рефералы\n/kassa — касса\n/chatid — ID чата\n/setchannel payouts|events|games -100… — каналы логов' : ''), this.keyboard());
    } catch (error) {
      if (/^(send|edit|answer|get|delete)[A-Z]|fetch failed|timeout|aborted/i.test(error.message)) throw error;
      return await this.screen(chat.id, esc(error.message));
    }
  }
  async drain() {
    if (this.sending) return; this.sending = true;
    try {
      let attempted = 0;
      for (const e of this.activity.data.outbox.filter(e => { const kind=e.kind==='payout'?'payouts':e.kind==='game'?'games':'events'; return !e.delivered && (this.activity.data.channels[kind] || this.channels[kind]); })) {
        const kind = e.kind === 'payout' ? 'payouts' : e.kind === 'game' ? 'games' : 'events';
        const chat = this.activity.data.channels[kind] || this.channels[kind];
        if (!chat || (this.channelRetry.get(String(chat)) || 0) > Date.now()) continue;
        if (attempted++ >= 20) break;
        const r = e.payload; let text, keys;
        if (e.kind === 'payout') {
          const live = this.payments.getPayout(r.id) || r;
          text = this.payoutText(live);
          if (live.status === 'review') keys = { inline_keyboard: [[button('✅ Выплачено', `pay:${r.id}:done`), button('❌ Отказано', `pay:${r.id}:failed`)]] };
        } else if (e.kind === 'game') text = `<b>🎮 ${esc(r.game)}</b>\n${userLine({ ...r, id: r.userId })}\nСтавка: ${amount(r.bet)}\nВыплата: ${amount(r.payout)}\nКоэффициент: ${r.multiplier.toFixed(2)}×\nРезультат: <b>${amount(r.net)}</b>\n${date(r.at)} UTC\n<code>${esc(r.id)}</code>`;
        else if (e.kind === 'deposit') text = `<b>↓ Пополнение · Успешно</b>\n${userLine({ ...r, id: r.userId })}\n${amount(r.creditedCents)} · ${esc(r.provider)}\n<code>${esc(r.id)}</code>`;
        else text = `<b>👤 Новый пользователь</b>\n${userLine({ ...r, id: r.userId })}`;
        try { await this.say(chat, text, keys); }
        catch (error) {
          this.channelRetry.set(String(chat), Date.now() + Math.max(30000, (error.retryAfter || 0) * 1000));
          console.error('Telegram: канал временно недоступен:', chat, error.message);
          continue;
        }
        this.channelRetry.delete(String(chat));
        this.accounts.atomic(() => { e.delivered = true; });
        if (e.kind === 'payout' && ['done', 'failed'].includes(r.status)) {
          try { await this.say(r.userId, `Вывод ${amount(r.cents)}: <b>${esc(statusName(r.status))}</b>`); } catch {}
        }
        // Channel rate limit: preserve the queue rather than dropping logs.
        await new Promise(resolve => { this.delay = setTimeout(resolve, 1100); });
        if (!this.running && !this.transport) break;
      }
    } catch (error) { console.error('Telegram: доставка логов отложена:', error.message); }
    finally { this.sending = false; }
  }
  async processUpdate(update) {
    try { await this.handle(update); }
    catch (error) {
      if (![400, 403].includes(error.telegramCode)) throw error;
      console.error('Telegram: обновление отклонено:', update.update_id, error.message);
    }
    this.accounts.atomic(() => { this.activity.data.botOffset = update.update_id + 1; });
  }
  async start() {
    if (!this.token || this.running) return;
    this.running = true;
    try {
      const info = await this.call('getWebhookInfo');
      if (info.url) { console.error('Telegram-бот: уже настроен webhook. Для polling используйте scripts/setup-bot.js --polling.'); this.running = false; return; }
      const menu = await this.call('getChatMenuButton');
      if (!this.appUrl && menu.web_app?.url) this.appUrl = menu.web_app.url;
      const me = await this.call('getMe'); if (!this.activity.botUsername) this.activity.botUsername = me.username;
      await this.call('setMyCommands', { commands: [{ command: 'start', description: 'Открыть Croco' }, { command: 'profile', description: 'Мой профиль' }, { command: 'wallet', description: 'Пополнение и вывод' }, { command: 'ref', description: 'Мои рефералы' }, { command: 'support', description: 'Поддержка' }] });
      this.logTimer = setInterval(() => this.drain(), 1500); this.logTimer.unref();
      while (this.running) {
        try {
          const updates = await this.call('getUpdates', { offset: this.activity.data.botOffset || 0, timeout: 25, allowed_updates: ['message', 'callback_query'] });
          const queueWait = perf.begin('bot.batch_wait', 1000);
          for (const update of updates) {
            if (!this.running) break;
            queueWait({ batch_size: updates.length });
            const finishUpdate = perf.begin('bot.handle', 1000);
            try {
              await this.processUpdate(update);
            } finally { finishUpdate(); }
          }
        } catch (error) {
          console.error('Telegram-бот: запрос отложен:', error.message);
          await new Promise(resolve => { this.retryTimer = setTimeout(resolve, 5000); this.retryTimer.unref(); });
        }
      }
    } catch (error) { console.error('Telegram-бот не запущен:', error.message); this.running = false; }
  }
  stop() { this.running = false; clearInterval(this.logTimer); clearTimeout(this.retryTimer); }
}
module.exports = { TelegramBot, periodStart, statusName };
