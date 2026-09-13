'use strict';
const CrocoPages = (() => {
  const privateSlots = new Set(['abyss', 'cryo', 'midnight']);
  let walletMode = 'deposit', walletBack = 'home', historyBack = 'profile', infoBack = 'information';
  let refData = null, refPage = 0, betPage = 0, operationPage = 0, searchTimer;
  const cash = n => money(n || 0).replace('.', ',');
  const when = n => new Date(n).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  const esc = escapeHtml;
  const documents = {
    payments: ['Пополнение и вывод', ['Откройте кошелёк, выберите «Пополнить», платёжный сервис и сумму. Нажмите «Пополнить» и оплатите созданный счёт в выбранном боте. Если баланс не обновился, нажмите «Я оплатил»: сервер проверит статус счёта.', 'На вкладке «Вывести» выберите сервис и сумму. Сумма заявки резервируется на балансе. Статус «В обработке» означает, что заявка ожидает обработки. После подтверждения выплаты статус меняется на «Успешно». При отказе статус — «Отказано», а сумма возвращается на баланс.', 'Пополнения и выводы доступны в истории операций. При обращении в поддержку сообщите свой Telegram ID и номер операции.']],
    referrals: ['Реферальная программа', ['Поделитесь своей реферальной ссылкой из вкладки «Бонусы». Новый пользователь закрепляется за вами при первом входе по этой ссылке. Существующие аккаунты нельзя перепривязать; приглашать самого себя нельзя.', 'Вознаграждение составляет 10% игрового дохода проекта с реферала: ставки минус выплаты по завершённым играм против проекта. Депозиты показываются отдельно и сами по себе не дают вознаграждение. Переводы между игроками за покерным столом доходом проекта не считаются.', 'Начисления появляются сразу после расчёта завершённого раунда и доступны по кнопке «Забрать на баланс». Если реферал отыграл предыдущие проигрыши, его дальнейшие проигрыши сначала покрывают учтённый минус. Повторно вознаграждение за ту же сумму не начисляется. Уже полученное вознаграждение не списывается.', 'Минус считается отдельно по каждому рефералу. Список показывает сумму депозитов и ваш заработок. Нажмите на друга, чтобы увидеть число пополнений, доход проекта и сумму, которую нужно покрыть до следующего начисления.']],
    security: ['Безопасность аккаунта', ['Вход связан с вашим Telegram-аккаунтом. Включите двухэтапную аутентификацию в Telegram и проверяйте активные сеансы в настройках Telegram.', 'Никому не сообщайте коды входа, пароль Telegram, приватные ключи или seed-фразу. Для обращения используйте кнопку поддержки внутри приложения.', 'Перед оплатой проверяйте выбранный сервис и сумму. В истории операций сохраняются номер заявки и её статус.']],
    responsible: ['Ответственная игра', ['Играйте только на сумму, которую можете позволить себе потерять. Делайте перерывы и не пытайтесь срочно отыграться.', 'Если игра перестала приносить удовольствие или вам нужна помощь с ограничением доступа к аккаунту, обратитесь в поддержку.']],
  };
  const faq = [
    ['Не пришло пополнение', 'Проверьте статус счёта в платёжном боте. Откройте кошелёк и нажмите «Я оплатил». Если оплата подтверждена, а баланс не изменился, сообщите поддержке ID операции.'],
    ['Где посмотреть статус вывода?', 'Откройте Профиль → История операций. «В обработке» — заявка ожидает обработки, «Успешно» — выплата подтверждена, «Отказано» — сумма возвращена на баланс.'],
    ['Игра прервалась — что со ставкой?', 'Переподключитесь и откройте ту же игру. Сервер определяет результат. Проверьте историю игр; если завершённого результата нет, обратитесь в поддержку с ID аккаунта и временем ставки.'],
    ['Почему не начислен реферальный бонус?', 'Бонус начисляется с игрового дохода, а не с депозита. Если реферал ранее выиграл, его проигрыши сначала покрывают учтённый минус. Подробности доступны по нажатию на реферала.'],
    ['Не работает промокод', 'Проверьте код, срок действия и доступное число активаций. Один аккаунт может использовать один и тот же код только один раз.'],
  ];
  function support() {
    if (state.links.support) openExternal(state.links.support);
    else toast('Контакт поддержки пока не указан');
  }
  function updateAccount() {
    document.body.dataset.admin = String(state.isAdmin);
    $('profile-tag').textContent = state.user?.username ? '@' + state.user.username : '';
    $('profile-id').textContent = 'ID: ' + (state.user?.id || '—');
    $('wallet-balance').textContent = cash(state.balance);
    $('profile-balance').textContent = cash(state.balance);
    $('btn-topup').disabled = false;
    document.querySelectorAll('#tab-games [data-arcade]').forEach(el => {
      if (privateSlots.has(el.dataset.arcade)) el.dataset.privateSlot = 'true';
    });
    const historyGame = $('history-game');
    const selected = historyGame.value;
    historyGame.innerHTML = '<option value="">Все игры</option>' + Object.entries(GameCatalog.names).filter(([id]) => state.isAdmin || !privateSlots.has(id)).map(([id, name]) => `<option value="${id}">${esc(name)}</option>`).join('');
    historyGame.value = selected;
  }
  function wallet(mode = 'deposit') {
    if (state.tab !== 'wallet') walletBack = state.tab === 'profile' ? 'profile' : 'home';
    walletMode = mode;
    showTab('wallet'); renderWallet();
  }
  function renderWallet() {
    $('wallet-balance').textContent = cash(state.balance);
    const deposit = walletMode === 'deposit';
    $('wallet-deposit').classList.toggle('is-active', deposit); $('wallet-withdraw').classList.toggle('is-active', !deposit);
    renderTopUp(); renderPayout();
    $('topup-card').classList.toggle('hidden', !deposit);
    $('payout-card').classList.toggle('hidden', deposit);
    $('wallet-unavailable').classList.toggle('hidden', deposit ? state.topup.config.enabled : state.topup.config.payout.enabled);
    for (const [name, enabled] of [['topup', state.topup.config.enabled], ['payout', state.topup.config.payout.enabled]]) {
      $(name + '-amount').disabled = !enabled;
      if (!enabled) {
        $(name + '-providers').classList.remove('hidden');
        $(name + '-providers').innerHTML = providerOptions([]).map(item => `<button type="button" class="cp-provider-option" disabled>${providerMarkup(item)}</button>`).join('');
        $(name + '-presets').innerHTML = [10,25,50,100].map(amount => `<button type="button" class="chip-btn" disabled>$${amount}</button>`).join('');
        const action = $(name === 'topup' ? 'topup-create' : 'payout-send'); action.disabled = true; action.textContent = name === 'topup' ? 'Пополнить →' : 'Вывести →';
      }
    }
    if (deposit && state.topup.config.enabled) $('topup-create').textContent = state.topup.busy ? 'Создаём счёт…' : 'Пополнить →';
  }
  function providerOptions(enabled) {
    return [{ id: 'xrocket', title: 'xRocket' }, { id: 'cryptobot', title: 'Crypto Bot' }].map(item => {
      const provider = enabled.find(p => p.id === item.id);
      return provider ? { ...provider, available: true } : { ...item, available: false };
    });
  }
  function providerMarkup(item) {
    const blue = item.id === 'cryptobot';
    return `<span class="cp-provider-art${blue ? ' is-blue' : ''}">${icon(blue ? 'send' : 'rocket')}</span><span class="cp-provider-text"><b>${esc(item.title)}</b><small>${item.available === false ? 'Скоро будет доступно' : walletMode === 'withdraw' ? 'На ваш аккаунт Telegram' : 'Оплата через Telegram'}</small></span>`;
  }
  function referrals(reset = true) {
    if (!state.connected) return;
    if (reset) refPage = 0;
    const period = $('ref-period').value; let since = 0;
    if (period !== 'all') { const d = new Date(); d.setHours(0, 0, 0, 0); if (period === 'week') d.setDate(d.getDate() - 6); if (period === 'month') d.setDate(1); since = d.getTime(); }
    send({ type: 'referrals', since, query: $('ref-search').value, page: refPage });
  }
  function receiveRef(data) {
    if (!refPage || !refData) refData = data; else refData = { ...data, rows: [...refData.rows, ...data.rows] };
    $('ref-balance').textContent = cash(data.balance); $('ref-claim').disabled = !data.balance;
    $('ref-count').textContent = data.count; $('ref-deposits').textContent = cash(data.deposits); $('ref-earned').textContent = cash(data.earned);
    $('ref-link').textContent = data.link || 'Ссылка временно недоступна';
    $('ref-copy').disabled = !data.link; $('ref-invite').disabled = !data.link;
    $('ref-more').classList.toggle('hidden', !data.more);
    $('ref-list').innerHTML = refData.rows.length ? refData.rows.map(row => `<button class="cp-ref-row" data-ref-id="${esc(row.id)}" aria-expanded="false"><span class="cp-ref-person"><i>${esc((row.name || 'И')[0])}</i><span><b>${esc(row.name)}</b><small>${esc(new Date(row.createdAt).toLocaleDateString('ru-RU'))}</small></span></span><span>${cash(row.deposits)}</span><span class="cp-ref-income">${row.earned ? '+' : ''}${cash(row.earned)}${icon('chevron-right')}</span></button><div class="cp-ref-detail hidden" id="ref-detail-${esc(row.id)}">${row.username ? '@' + esc(row.username) + ' · ' : ''}ID: ${esc(row.id)}<br>Пополнений: ${row.depositCount}<br>Доход проекта: ${cash(row.revenue)}<br>Учтённый минус до следующего начисления: ${cash(row.carry)}${row.lastDeposit ? '<br>Последнее пополнение: ' + when(row.lastDeposit) : ''}</div>`).join('') : '<p class="cp-muted">Здесь появятся приглашённые друзья.</p>';
  }
  function gamesHistory(reset = true) {
    if (reset) { betPage = 0; $('bet-history-list').innerHTML = '<p class="cp-muted">Загружаем ставки…</p>'; }
    send({ type: 'game_history', page: betPage, game: $('history-game').value });
  }
  function receiveBets(data) {
    const html = data.rows.map(r => {
      const game = GameCatalog.names[r.game] ? r.game : 'holdem';
      return `<button class="cp-bet-row" data-round-id="${esc(r.id)}"><span class="cp-bet-person"><img src="${GameCatalog.artwork(game)}" alt="" /><span><b>${esc(r.name)}</b><small>${esc(GameCatalog.names[game])}</small></span></span><span>${cash(r.bet)}</span><span>${r.multiplier.toFixed(2).replace('.', ',')}×</span><strong class="${r.net > 0 ? 'cp-positive' : r.net < 0 ? 'cp-negative' : ''}">${r.net > 0 ? '+' : ''}${cash(r.net)}</strong></button><div class="cp-ref-detail hidden">${when(r.at)}<br>Ставка: ${cash(r.bet)} · выплата: ${cash(r.payout)}<br>ID: ${esc(r.id)}</div>`;
    }).join('');
    if (!data.page) $('bet-history-list').innerHTML = html || '<p class="cp-muted">Здесь появятся все завершённые ставки, включая проигрыши.</p>';
    else $('bet-history-list').insertAdjacentHTML('beforeend', html);
    $('bets-more').classList.toggle('hidden', !data.more);
  }
  function operations(from = state.tab) {
    historyBack = from === 'wallet' ? 'wallet' : 'profile'; operationPage = 0;
    showTab('operations'); $('history-card').classList.remove('hidden');
    send({ type: 'history', page: 0 });
  }
  function receiveOperations(data) {
    const names = { review: 'В обработке', pending: 'В обработке', unknown: 'В обработке', done: 'Успешно', failed: 'Отказано', paid: 'Успешно', expired: 'Истёк' };
    const rows = data.rows || data.history || [];
    const html = rows.map(r => {
      const incoming = ['topup', 'referral'].includes(r.kind), done = ['paid', 'done'].includes(r.status);
      const title = r.kind === 'topup' ? 'Пополнение' : r.kind === 'referral' ? 'Реферальный перевод' : 'Вывод';
      return `<div class="cp-operation">${icon(incoming ? 'arrow-down' : 'arrow-up')}<span><b>${title}</b><small>${esc(r.providerTitle || '')} · ${when(r.createdAt)}</small><small>${r.kind === 'topup' && r.status === 'pending' ? 'Ожидает оплаты' : names[r.status] || esc(r.status)}</small><small>ID: ${esc(r.id)}</small></span><strong class="${done && incoming ? 'cp-positive' : ''}">${done ? incoming ? '+' : '−' : ''}${cash(r.creditedCents || r.cents)}</strong></div>`;
    }).join('');
    if (!data.page) $('history-list').innerHTML = html || '<p class="cp-muted">Операций пока не было.</p>';
    else $('history-list').insertAdjacentHTML('beforeend', html);
    $('operations-more').classList.toggle('hidden', !data.more);
  }
  function detail(key) {
    infoBack = ['profile', 'bonuses'].includes(state.tab) ? state.tab : 'information';
    showTab('helpdetail');
    if (key === 'rules') {
      $('help-detail-title').textContent = 'Правила игр';
      $('help-detail-content').innerHTML = Object.entries(GameCatalog.names).filter(([id]) => (state.isAdmin || !privateSlots.has(id)) && id !== 'darts').map(([id, name]) => `<details class="cp-faq"><summary><span class="cp-bet-person"><img src="${GameCatalog.artwork(id)}" alt="" /><b>${esc(name)}</b></span></summary><p>${esc(ruleText(id))}</p></details>`).join(''); return;
    }
    if (key === 'terms' || key === 'privacy') {
      const url = state.config[key === 'terms' ? 'termsUrl' : 'privacyUrl'];
      if (url) { openExternal(url); showTab(infoBack); return; }
      $('help-detail-title').textContent = key === 'terms' ? 'Условия использования' : 'Конфиденциальность';
      $('help-detail-content').innerHTML = '<p>Документ пока не опубликован. Запросить информацию можно у поддержки.</p><button class="cp-primary" data-support>Написать в поддержку →</button>'; return;
    }
    const doc = documents[key] || documents.security;
    $('help-detail-title').textContent = doc[0]; $('help-detail-content').innerHTML = doc[1].map(t => `<p>${esc(t)}</p>`).join('');
  }
  function ruleText(id) {
    const rules = {
      holdem: 'Две закрытые карты и пять общих. Соберите лучшую комбинацию из любых пяти карт. Торговля проходит до флопа, на флопе, тёрне и ривере. Доступны фолд, чек, колл и повышение ставки.',
      omaha: 'Четыре закрытые карты и пять общих. Комбинация обязательно состоит из двух ваших и трёх общих карт. Следите за доступными действиями и размером банка.',
      blackjack: 'Наберите больше очков, чем дилер, не превышая 21. Картинки дают 10, туз — 1 или 11. Можно взять карту или остановиться. Удвоение и разделение доступны, когда их разрешает текущая рука.',
      mines: 'Выберите ставку и число мин. Открывайте безопасные клетки: коэффициент растёт. Заберите выплату до попадания на мину. Мина завершает раунд проигрышем.',
      nvuti: 'Выберите условие и порог. Сервер разыграет случайное число. Коэффициент зависит от вероятности выбранного исхода и показывается до ставки.',
      crash: 'Коэффициент растёт до случайного момента остановки. Заберите выплату раньше остановки или настройте автоматическое получение. После остановки незабранная ставка проигрывает.',
      hilo: 'Угадайте, будет ли следующая карта выше или ниже. Доступные варианты зависят от текущей карты. После удачного выбора можно продолжить или забрать выплату.',
      roulette: 'Поставьте на число или группу чисел. После остановки колеса выигрывают ставки на выпавший сектор. Коэффициенты зависят от типа ставки.',
      baccarat: 'Поставьте на игрока, банкира или ничью. Цель руки — приблизиться к девяти очкам. Десятки и картинки дают ноль, учитывается последняя цифра суммы; добор карт выполняется по правилам игры.',
      plinko: 'Выберите риск и ставку, запустите шарик. Итоговая ячейка определяет коэффициент выплаты. Несколько шариков считаются отдельными ставками внутри запуска.',
      tower: 'Выберите сложность, ставку и безопасную клетку на очередном уровне. Поднимайтесь выше или заберите выплату. Небезопасная клетка завершает раунд.',
      keno: 'Выберите числа и ставку. После розыгрыша выплата зависит от количества совпадений. Таблица коэффициентов показывается в игре.',
      dragon: 'Выберите сторону Dragon или Tiger. Побеждает сторона с более высокой картой. Итог и выплата рассчитываются сервером.',
    };
    if (rules[id]) return rules[id];
    const game = typeof CasinoRules !== 'undefined' ? CasinoRules.games[id] : null;
    const table = game?.table?.map(([label, value]) => `${label}: ${value}×`).join('; ');
    return [game?.rules || game?.subtitle || game?.description || `Выберите ставку и параметры в ${GameCatalog.names[id]}. Результат и выплата определяются сервером.`, table ? `Коэффициенты: ${table}.` : 'Доступные коэффициенты и условия показаны на игровом экране до ставки.'].join(' ');
  }
  function entered(tab) {
    if (tab === 'bonuses') referrals();
    if (tab === 'gamehistory') gamesHistory();
    if (tab === 'wallet') renderWallet();
  }
  function init() {
    for (const id of ['topup-card', 'payout-card']) $('wallet-content').appendChild($(id));
    const note = document.createElement('p'); note.id = 'wallet-unavailable'; note.className = 'cp-muted hidden'; note.textContent = 'Этот способ оплаты пока недоступен.'; $('wallet-content').appendChild(note);
    $('topup-card').querySelector('h2').textContent = 'Способ пополнения'; $('payout-card').querySelector('h2').textContent = 'Способ вывода';
    for (const name of ['topup', 'payout']) { const label = document.createElement('label'); label.className = 'cp-amount-label'; label.htmlFor = name + '-amount'; label.textContent = 'Сумма'; $(name + '-card').appendChild(label); }
    for (const name of ['topup', 'payout']) {
      const input = $(name + '-amount'), field = document.createElement('div'); field.className = 'cp-money-input';
      input.parentNode.insertBefore(field, input); field.innerHTML = '<span aria-hidden="true">$</span>'; field.appendChild(input);
      input.step = '0.01';
    }
    $('topup-amount').value = '25'; $('payout-amount').value = '25';
    $('operations-content').appendChild($('history-card')); $('history-card').querySelector('.card-head').classList.add('hidden');
    $('info-faq').innerHTML = faq.map(([q, a]) => `<details class="cp-faq"><summary>${q}</summary><p>${a}</p></details>`).join('');
    on('profile-wallet', 'click', () => wallet()); on('wallet-back', 'click', () => showTab(walletBack));
    on('wallet-deposit', 'click', () => wallet('deposit')); on('wallet-withdraw', 'click', () => wallet('withdraw'));
    on('wallet-history', 'click', () => operations()); on('profile-gamehistory', 'click', () => showTab('gamehistory'));
    on('history-game', 'change', () => gamesHistory()); on('bets-more', 'click', () => { betPage++; gamesHistory(false); });
    on('operations-more', 'click', () => { operationPage++; send({ type: 'history', page: operationPage }); });
    on('ref-claim', 'click', () => { if (!state.connected) return toast('Дождитесь подключения'); $('ref-claim').disabled = true; send({ type: 'referral_claim' }); });
    on('ref-period', 'change', () => referrals()); on('ref-search', 'input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => referrals(), 250); });
    on('ref-more', 'click', () => { refPage++; referrals(false); });
    on('ref-copy', 'click', async () => { if (!refData?.link) return; try { await navigator.clipboard.writeText(refData.link); toast('Ссылка скопирована'); } catch { toast('Не удалось скопировать ссылку'); } });
    on('ref-invite', 'click', () => { if (refData?.link) openExternal('https://t.me/share/url?url=' + encodeURIComponent(refData.link) + '&text=' + encodeURIComponent('Присоединяйся к Croco')); });
    on('ref-list', 'click', e => { const button = e.target.closest('[data-ref-id]'); if (!button) return; const panel = button.nextElementSibling; panel.classList.toggle('hidden'); button.setAttribute('aria-expanded', String(!panel.classList.contains('hidden'))); });
    on('bet-history-list', 'click', e => { const button = e.target.closest('[data-round-id]'); button?.nextElementSibling?.classList.toggle('hidden'); });
    for (const [id, key] of [['info-payments', 'payments'], ['info-referrals', 'referrals'], ['info-security', 'security']]) on(id, 'click', () => detail(key));
    on('info-search', 'input', () => { const query = $('info-search').value.toLowerCase().trim(); let count = 0; document.querySelectorAll('#info-sections>button,#info-faq>details').forEach(el => { const visible = el.textContent.toLowerCase().includes(query); el.classList.toggle('hidden', !visible); if (visible) count++; }); $('info-empty').classList.toggle('hidden', !!count); });
    document.addEventListener('click', e => {
      if (e.target.closest('[data-support]')) support();
      const help = e.target.closest('[data-help]'); if (help) detail(help.dataset.help);
      if (e.target.closest('[data-profile-back]')) showTab('profile');
      if (e.target.closest('[data-history-back]')) historyBack === 'wallet' ? wallet(walletMode) : showTab('profile');
      if (e.target.closest('[data-info-back]')) showTab(infoBack);
    });
    for (const key of ['sound', 'vibration']) {
      const field = $('profile-' + key); field.checked = localStorage.getItem('croco:' + key) !== 'off';
      field.addEventListener('change', () => { localStorage.setItem('croco:' + key, field.checked ? 'on' : 'off'); if (key === 'sound') applySound(); });
    }
    applySound();
  }
  function balanceUpdate(message) {
    if (Number.isFinite(message.refBalance)) { $('ref-balance').textContent = cash(message.refBalance); $('ref-claim').disabled = !message.refBalance; }
    if (state.tab === 'bonuses') { clearTimeout(searchTimer); searchTimer = setTimeout(() => referrals(), 200); }
    if (state.tab === 'operations') send({ type: 'history', page: 0 });
  }
  function applySound() {
    const muted = localStorage.getItem('croco:sound') === 'off';
    for (const name of ['AbyssAudio', 'FeatureSlotAudio', 'CryoAudio', 'MidnightAudio']) globalThis[name]?.configure?.({ muted });
    document.querySelectorAll('audio,video').forEach(el => { el.muted = muted; });
  }
  init();
  return { balanceUpdate, wallet, renderWallet, updateAccount, entered, receiveRef, receiveBets, receiveOperations, referrals, operations, detail, support, providerMarkup, providerOptions };
})();
