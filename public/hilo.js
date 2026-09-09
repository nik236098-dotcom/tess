'use strict';
// Rendering only: cards, probabilities and payouts always come from the server.
function openHilo() {
  showLobby();
  state.hl.open = true; state.hl.busy = true;
  $('screen-lobby').classList.add('hidden');
  $('screen-hl').classList.remove('hidden');
  $('screen-hl').scrollTop = 0;
  stopRoomsPolling();
  if (tg && tg.BackButton) tg.BackButton.show();
  renderHilo(); send({ type: 'hl_open' });
}
function closeHilo() { showLobby(); }
function hlCard(card) {
  const rank = ({ 1: 'A', 11: 'J', 12: 'Q', 13: 'K' })[card.rank] || card.rank;
  const suit = SUITS[card.suit];
  return `<div class="hl-face ${suit.red ? 'hl-red' : ''}" aria-label="${rank} ${suit.symbol}"><span class="hl-corner">${rank}<small>${suit.symbol}</small></span><b class="hl-pip">${suit.symbol}</b><span class="hl-corner hl-bottom">${rank}<small>${suit.symbol}</small></span></div>`;
}
function hlRequest(action, extra = {}) {
  const hl = state.hl;
  if (hl.busy || hl.animating || !hl.info) return;
  if (!state.connected) { toast('Нет соединения. Подождите подключения'); return; }
  if (action === 'start') {
    const amount = toCents($('hl-amount').value);
    if (amount === null || amount < hl.info.minBet || amount > hl.info.maxBet) { toast('Ставка от $0.10 до $100 000'); return; }
    if (amount > state.balance) { toast('Недостаточно средств'); return; }
    hl.amount = amount; extra.amount = amount;
  }
  hl.busy = true; haptic('light'); renderHilo();
  send({ type: `hl_${action}`, revision: hl.info.revision, ...extra });
}
async function onHiloState(message) {
  const hl = state.hl;
  const previous = hl.info;
  const token = ++hl.token;
  const animate = hl.open && previous && message.revision > previous.revision &&
    (message.card.rank !== previous.card.rank || message.card.suit !== previous.card.suit ||
    message.history.length !== previous.history.length) && message.phase !== 'bet';
  const skipAnimate = hl.open && previous && message.revision > previous.revision && message.phase === 'bet';
  hl.busy = false; hl.animating = Boolean(animate || skipAnimate);
  state.balance = message.balance;
  // Keep odds and cashout locked to the old visible card until the transition ends.
  renderHilo();
  const deck = $('hl-deck');
  if (hl.animating && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const old = deck.querySelector('.hl-face');
    const next = document.createElement('div'); next.className = 'hl-incoming'; next.innerHTML = hlCard(message.card);
    deck.append(next);
    const timing = { duration: 480, easing: 'cubic-bezier(.22,.7,.2,1)', fill: 'both' };
    const animations = [next.animate([{ opacity: 0, transform: 'translate(22px, 12px) rotateY(-75deg) scale(.96)' }, { opacity: 1, transform: 'translate(0,0) rotateY(0) scale(1)' }], timing)];
    if (old) animations.push(old.animate([{ opacity: 1, transform: 'translateX(0) rotate(0)' }, { opacity: 0, transform: 'translateX(-65%) rotate(-10deg)' }], timing));
    await Promise.all(animations.map(a => a.finished.catch(() => {})));
    animations.forEach(a => a.cancel()); next.remove();
  }
  if (token !== hl.token) return;
  hl.info = message; hl.animating = false;
  renderHilo();
  if (hl.open && message.phase === 'done' && previous?.phase === 'play') haptic(message.result === 'win' ? 'success' : 'error');
}
function renderHilo() {
  const hl = state.hl;
  if (!hl.open) return;
  const info = hl.info;
  const locked = hl.busy || hl.animating || !state.connected || !info;
  const live = info?.phase === 'play';
  $('hl-balance').textContent = money(state.balance);
  if (!hl.animating) $('hl-deck').innerHTML = info ? hlCard(info.card) : '<div class="hl-loading">Загрузка…</div>';
  for (const [id, probability] of [['high', info?.high], ['low', info?.low]]) {
    $(`hl-${id}`).disabled = locked || !live || probability === 1;
    $(`hl-${id}-chance`).textContent = probability ? `${(probability * 100).toFixed(2).replace('.', ',')}%` : '—';
  }
  $('hl-skip').disabled = locked;
  $('hl-multiplier').textContent = `${(info?.multiplier || 1).toFixed(2)}×`;
  $('hl-win').textContent = money(info?.available || 0);
  const main = $('hl-main');
  main.disabled = locked;
  main.classList.toggle('is-cash', Boolean(live));
  main.textContent = live ? (info.multiplier === 1 ? `Вернуть ставку ${money(info.bet)}` : `Забрать ${money(info.available)}`) : 'Сделать ставку';
  $('hl-result').textContent = info?.phase === 'done' ? (info.result === 'win' ? `Забрано ${money(info.payout)}` : 'Не угадали. Попробуйте ещё раз') : (live ? 'Выберите направление следующей карты' : 'Сделайте ставку, чтобы начать');
  $('hl-result').classList.toggle('is-win', info?.result === 'win');
  for (const el of document.querySelectorAll('#hl-panel input, #hl-panel .mn-mod')) el.disabled = locked || live;
  const history = $('hl-history');
  history.innerHTML = (info?.history || []).map(item => `<div class="hl-history-item ${item.won === false ? 'is-loss' : ''}"><span class="hl-history-arrow">${({high:'↑',low:'↓',skip:'»',start:'•'})[item.direction]}</span>${hlCard(item.card)}<small>${item.direction === 'skip' ? 'Пропуск' : item.multiplier.toFixed(2) + '×'}</small></div>`).join('') || '<span class="hl-empty">Здесь появятся ваши карты</span>';
  history.scrollLeft = history.scrollWidth;
}
function bindHilo() {
  $('play-hilo').addEventListener('click', openHilo);
  $('hl-back').addEventListener('click', closeHilo);
  $('hl-main').addEventListener('click', () => hlRequest(state.hl.info?.phase === 'play' ? 'cashout' : 'start'));
  $('hl-high').addEventListener('click', () => hlRequest('pick', { direction: 'high' }));
  $('hl-low').addEventListener('click', () => hlRequest('pick', { direction: 'low' }));
  $('hl-skip').addEventListener('click', () => hlRequest('skip'));
  for (const el of document.querySelectorAll('[data-hl-mod]')) el.addEventListener('click', () => {
    const max = Math.min(state.balance, state.hl.info?.maxBet || 10000000);
    const current = toCents($('hl-amount').value) ?? 100;
    const amount = Math.max(10, Math.min(max, Math.round(el.dataset.hlMod === 'max' ? max : current * Number(el.dataset.hlMod))));
    $('hl-amount').value = (amount / 100).toFixed(2).replace('.', ',');
  });
}
