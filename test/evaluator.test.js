'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { stringToCard } = require('../server/poker/cards');
const { bestHand, evaluate5, compareScores } = require('../server/poker/evaluator');

const hand = (s) => s.split(' ').map(stringToCard);

test('распознаёт основные комбинации', () => {
  assert.strictEqual(bestHand(hand('As Ks Qs Js Ts')).name, 'Флеш-рояль');
  assert.strictEqual(bestHand(hand('9c 9d 9h 9s 2c')).name, 'Каре 9');
  assert.strictEqual(bestHand(hand('Kc Kd Kh 4s 4c')).name, 'Фулл-хаус K на 4');
  assert.strictEqual(bestHand(hand('2c 7c 9c Jc Kc')).name, 'Флеш до K');
  assert.strictEqual(bestHand(hand('5c 6d 7h 8s 9c')).name, 'Стрит до 9');
  assert.strictEqual(bestHand(hand('Qc Qd Qh 4s 2c')).name, 'Тройка Q');
  assert.strictEqual(bestHand(hand('Ac Ad 8h 8s 2c')).name, 'Две пары A и 8');
  assert.strictEqual(bestHand(hand('Ac Ad 8h 5s 2c')).name, 'Пара A');
  assert.strictEqual(bestHand(hand('Ac Kd 8h 5s 2c')).name, 'Старшая A');
});

test('колесо A-2-3-4-5 считается стритом до пятёрки', () => {
  const wheel = evaluate5(hand('Ac 2d 3h 4s 5c'));
  const sixHigh = evaluate5(hand('2c 3d 4h 5s 6c'));
  assert.strictEqual(bestHand(hand('Ac 2d 3h 4s 5c')).name, 'Стрит до 5');
  assert.strictEqual(compareScores(sixHigh, wheel), 1, 'стрит до шестёрки сильнее колеса');
});

test('порядок категорий соблюдается', () => {
  const ordered = [
    'Ac Kd 8h 5s 2c',
    'Ac Ad 8h 5s 2c',
    'Ac Ad 8h 8s 2c',
    'Qc Qd Qh 4s 2c',
    '5c 6d 7h 8s 9c',
    '2c 7c 9c Jc Kc',
    'Kc Kd Kh 4s 4c',
    '9c 9d 9h 9s 2c',
    'As Ks Qs Js Ts',
  ].map((h) => evaluate5(hand(h)));

  for (let i = 1; i < ordered.length; i++) {
    assert.strictEqual(compareScores(ordered[i], ordered[i - 1]), 1, `комбинация ${i} должна быть сильнее`);
  }
});

test('из семи карт выбирается лучшая пятёрка', () => {
  const best = bestHand(hand('As Ah 7d 7c 7s 2d 3c'));
  assert.strictEqual(best.name, 'Фулл-хаус 7 на A');
});

test('кикеры сравниваются корректно', () => {
  const a = bestHand(hand('Ac Ad Kh 9s 4c 3d 2h'));
  const b = bestHand(hand('Ac Ad Qh 9s 4c 3d 2h'));
  assert.strictEqual(compareScores(a.score, b.score), 1);
});
