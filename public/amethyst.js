'use strict';
// Native 768×1536 composition measured against the approved reference.
let amethystEnabled = true;
try { amethystEnabled = localStorage.getItem('poker-amethyst-v1') !== 'off'; } catch {}
function amethystActive() { return amethystEnabled && (!state.room || ['holdem', 'omaha'].includes(state.room.game)); }
function syncAmethyst() {
  const screen = $('screen-table'), canvas = $('table-canvas');
  const active = amethystActive();
  screen.classList.toggle('amethyst-theme', active);
  const header = screen.querySelector('.topbar'), footer = screen.querySelector('.controls');
  if (active && header.parentElement !== canvas) { canvas.append(header, footer); }
  else if (!active && header.parentElement === canvas) {
    screen.prepend(header); screen.querySelector('.table-wrap').after(footer);
  }
  if (!canvas.querySelector('.am-emblem')) {
    const emblem = document.createElement('div'); emblem.className = 'am-emblem'; emblem.setAttribute('aria-hidden', 'true'); canvas.append(emblem);
  }
}
function fitAmethyst() {
  const box = $('table-viewport').getBoundingClientRect();
  if (box.width < 2 || box.height < 2) return;
  const scale = Math.min(box.width / 768, box.height / 1536);
  const canvas = $('table-canvas');
  canvas.style.transform = `translateX(-50%) scale(${scale})`;
  canvas.style.top = `${Math.max(0, (box.height - 1536 * scale) / 2)}px`;
  document.documentElement.style.setProperty('--table-scale', String(scale));
  document.documentElement.style.setProperty('--table-px', `${768 * scale}px`);
}
const AM_SEATS = [
  [384,1150,0,-205,0,-254], [106,928,29,10,0,-89],
  [80,635,29,27,8,-88], [109,365,33,14,0,-84],
  [384,231,29,20,0,-84], [661,365,-86,14,0,-84],
  [685,635,-70,27,-4,-88], [661,928,-83,9,0,-89],
];
function amSeatPosition(position, count) {
  if (count === 9) {
    // Two seats across the top for the existing nine-seat room setting.
    return [[384,1150,0,-205,0,-254],[106,928,29,10,0,-89],[80,635,29,27,8,-88],
      [109,365,33,14,0,-84],[293,231,29,20,0,-84],[475,231,29,20,0,-84],
      [661,365,-86,14,0,-84],[685,635,-70,27,-4,-88],[661,928,-83,9,0,-89]][position];
  }
  const set = SEAT_SETS[count] || SEAT_SETS[8];
  return AM_SEATS[set[position]];
}
function renderAmethystSeats(room) {
  const container = $('seats'); container.replaceChildren();
  $('room-title').innerHTML = 'Poker<span>Gena</span><i aria-hidden="true">♛</i>';
  const count = room.seats.length, offset = room.you.seatIndex ?? 0;
  const winners = winnerIdSet(room);
  for (const seat of room.seats) {
    const position = (seat.index - offset + count) % count;
    const [x,y,cx,cy,bx,by] = amSeatPosition(position, count);
    const hero = !seat.empty && seat.userId === room.you.userId;
    const bottom = y === 1150;
    const node = document.createElement('article');
    node.className = `am-seat${hero ? ' me' : ''}${bottom ? ' bottom' : ''}${seat.folded ? ' folded' : ''}${seat.isActing ? ' acting' : ''}${seat.sittingOut || seat.connected === false ? ' away' : ''}${winners.has(seat.userId) ? ' winner' : ''}`;
    node.dataset.seat = seat.index;
    for (const [key,val] of Object.entries({x,y,cx,cy,bx,by})) node.style.setProperty(`--${key}`, `${val}px`);
    if (seat.empty) {
      const button = document.createElement('button'); button.className = 'am-empty'; button.textContent = '+';
      button.type = 'button'; button.setAttribute('aria-label', `Свободное место ${seat.index + 1}`);
      button.disabled = !state.isAdmin && room.you.seatIndex !== null;
      button.onclick = () => state.isAdmin ? openBotSheet(seat.index) : openBuyIn(seat.index);
      node.append(button); container.append(node); continue;
    }
    node.setAttribute('aria-label', `${seat.name}, ${money(seat.stack)}${seat.folded ? ', пас' : seat.isActing ? ', ходит' : ''}`);
    const avatar = document.createElement('button'); avatar.className = 'am-avatar';
    avatar.type = 'button'; avatar.setAttribute('aria-label', seat.name);
    const silhouette = () => { avatar.innerHTML = '<svg viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="36" r="19"/><path d="M14 100v-12c0-24 15-34 36-34s36 10 36 34v12z"/></svg>'; };
    if (seat.photoUrl) {
      const image = document.createElement('img'); image.src = seat.photoUrl; image.alt = '';
      image.onerror = silhouette; avatar.append(image);
    } else silhouette();
    if (state.isAdmin) avatar.onclick = () => seat.isBot ? openBotSheet(seat.index) : openChipsSheet(seat);
    const plate = document.createElement('div'); plate.className = 'am-plate';
    const name = document.createElement('div'); name.className = 'am-name'; name.textContent = seat.name;
    const stack = document.createElement('div'); stack.className = 'am-stack'; stack.textContent = seat.allIn ? 'ALL-IN' : money(seat.stack);
    plate.append(name, stack);
    if (state.isAdmin && seat.isBot) plate.onclick = () => openBotSheet(seat.index);
    node.append(avatar, plate);
    const cards = document.createElement('div'); cards.className = 'am-cards';
    if (seat.cards?.length && !seat.folded) {
      for (const code of seat.cards) cards.append(cardNode(code, false, false));
      cards.style.setProperty('--count', seat.cards.length); node.append(cards);
    }
    if (seat.bet > 0 || seat.folded) {
      const bet = document.createElement('div'); bet.className = 'am-bet';
      bet.textContent = seat.folded ? 'ПАС' : money(seat.bet); node.append(bet);
    }
    if (seat.isActing) {
      const turn = document.createElement('div'); turn.className = 'am-turn'; turn.textContent = 'ХОД'; node.append(turn);
      const ring = turnRing(room, bottom ? 63 : 49);
      if (ring) node.append(ring);
    }
    if (hero && seat.combination) {
      const combo = document.createElement('div'); combo.className = 'am-combination';
      combo.textContent = shortHand(seat.combination); combo.title = seat.combination; node.append(combo);
    }
    // Positional information remains readable without decorations above heads.
    if (seat.isDealer || seat.isSmallBlind || seat.isBigBlind) {
      const pos = document.createElement('span'); pos.className = 'am-position';
      pos.textContent = [seat.isDealer ? 'D' : '', seat.isSmallBlind ? 'SB' : '', seat.isBigBlind ? 'BB' : ''].filter(Boolean).join(' · ');
      pos.title = 'Баттон / блайнды'; node.append(pos);
    }
    container.append(node);
  }
}
function openBotSheet(index) {
  if (!state.isAdmin || !state.room) return;
  const seat = state.room.seats[index];
  if (!seat || (!seat.empty && !seat.isBot)) return;
  state.botSeat = index;
  $('bot-title').textContent = seat.isBot ? seat.name : `Место ${index + 1}`;
  $('bot-add-options').classList.toggle('hidden', !seat.empty);
  $('bot-remove-options').classList.toggle('hidden', seat.empty);
  $('bot-sit-self').classList.toggle('hidden', state.room.you.seatIndex !== null);
  const range = state.room.you.buyIn;
  $('bot-buyin').value = ((range?.default || 0) / 100).toFixed(2);
  $('bot-funds').textContent = `Ваш баланс ${money(state.room.you.balance)}. Вход от ${money(range?.min || 0)}. Стек бота списывается с вашего баланса; остаток возвращается при удалении.`;
  $('bot-add').disabled = !range?.enough;
  $('bot-sheet').classList.remove('hidden');
}
function bindBotControls() {
  on('bot-close', 'click', () => $('bot-sheet').classList.add('hidden'));
  on('bot-sit-self', 'click', () => { $('bot-sheet').classList.add('hidden'); openBuyIn(state.botSeat); });
  on('bot-add', 'click', () => {
    const raw = $('bot-buyin').value.trim().replace(',', '.');
    if (!/^\d+(?:\.\d{1,2})?$/.test(raw)) return toast('Укажите сумму, например 10.00');
    const amount = Math.round(Number(raw) * 100), range = state.room?.you.buyIn;
    if (!range || amount < range.min || amount > range.max) return toast('Сумма вне доступного диапазона входа');
    send({ type: 'admin_add_bot', seat: state.botSeat, amount });
    $('bot-sheet').classList.add('hidden');
  });
  on('bot-remove', 'click', () => { send({ type: 'admin_remove_bot', seat: state.botSeat }); $('bot-sheet').classList.add('hidden'); });
}
