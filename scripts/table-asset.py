#!/usr/bin/env python3
"""Пересборка сукна стола из исходного ассета.

Ассет public/img/table-original.webp пришёл от стороннего продукта, и на сукне
запечён чужой логотип. Этот скрипт снимает его и собирает два файла:

  public/img/table.webp          чистое сукно (штатный вариант: свой знак
                                 лежит слоем .table-logo поверх холста)
  public/img/table-branded.webp  то же сукно со знаком «Poker ok 👌»,
                                 запечённым прямо в картинку

Размер и пропорции не меняются: 1086×1448, ровно 3:4 — от них считается
логический холст в app.js, поэтому трогать их нельзя.

Как снимается логотип: площадка заполняется «пятном Кунса» по цветам её
границы — это точно воспроизводит градиент сукна и совпадает с окружением
ровно на границе, — а поверх кладётся настоящая зернистость сукна, снятая
с чистого куска той же картинки. Маска скруглённая и растушёванная, поэтому
прямых швов не остаётся.

Запуск (нужны Pillow и numpy, в зависимости проекта они не входят):

    python3 scripts/table-asset.py
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, 'public', 'img')
SRC = os.path.join(IMG, 'table-original.webp')
SIZE = (1086, 1448)
WEBP = dict(quality=92, method=6)

# ── Чужой логотип на исходнике ───────────────────────────────────────────
# Измерено по картинке: пиксели логотипа — те, что заметно теплее и ярче
# сукна вокруг. Ядро знака (спада + POKERGENA + PLAY YOUR GAME) укладывается
# в x 423…657, y 345…502, то есть в долях 0.389…0.605 по ширине и
# 0.238…0.347 по высоте. Перекрашиваем с запасом на мягкие тени.
HOLE = (401, 323, 679, 524)          # left, top, right, bottom
BORDER = 10                          # полоса границы, по которой берём цвет
RADIUS, FEATHER = 46, 16             # скругление и растушёвка маски
GRAIN = (192, 438, 200, 150)         # чистый кусок сукна: x, y, w, h

# ── Свой знак ────────────────────────────────────────────────────────────
FONT = '/mnt/skills/examples/canvas-design/canvas-fonts/CrimsonPro-Bold.ttf'
EMOJI_FONT = '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf'
SS = 4                               # суперсэмплинг при отрисовке знака
CX = 540
WORD, TRACK, WORD_W, BASELINE = 'POKER OK', 0.17, 226, 466
EMOJI_H, EMOJI_TOP = 68, 348
RULE_Y, RULE_HALF = 486, 92
# Золото снято с исходной надписи: сверху светлое, снизу бронза.
GOLD = [(0.00, (248, 228, 170)), (0.40, (228, 194, 120)),
        (0.62, (198, 160, 88)), (1.00, (148, 117, 60))]
SHADOW = (6, 20, 12)


# ═══ Снятие логотипа ═════════════════════════════════════════════════════

def _coons(top, bottom, left, right):
    """Пятно Кунса по четырём краям: гладко внутри, точно совпадает по краю."""
    h, w = left.shape[0], top.shape[0]
    v = np.linspace(0, 1, h + 2)[1:-1][:, None, None]
    u = np.linspace(0, 1, w + 2)[1:-1][None, :, None]
    lc = (1 - v) * top[None, :, :] + v * bottom[None, :, :]
    lr = (1 - u) * left[:, None, :] + u * right[:, None, :]
    c00, c01, c10, c11 = top[0], top[-1], bottom[0], bottom[-1]
    bilinear = ((1 - u) * (1 - v) * c00 + u * (1 - v) * c01
                + (1 - u) * v * c10 + u * v * c11)
    return lc + lr - bilinear


def _smooth(arr, k=17):
    """Скользящее среднее вдоль оси 0: убирает зерно из краевых цветов."""
    pad = k // 2
    p = np.concatenate([arr[pad:0:-1], arr, arr[-2:-2 - pad:-1]], axis=0)
    ker = np.ones(k) / k
    return np.stack([np.convolve(p[:, c], ker, 'valid') for c in range(arr.shape[1])], axis=1)


def clean(im):
    """Возвращает картинку без чужого логотипа."""
    a = np.asarray(im).astype(np.float64)
    x0, y0, x1, y1 = HOLE
    w, h = x1 - x0, y1 - y0
    b = BORDER

    base = _coons(
        _smooth(a[y0 - b:y0, x0:x1].mean(axis=0)),
        _smooth(a[y1:y1 + b, x0:x1].mean(axis=0)),
        _smooth(a[y0:y1, x0 - b:x0].mean(axis=1)),
        _smooth(a[y0:y1, x1:x1 + b].mean(axis=1)),
    )

    gx, gy, gw, gh = GRAIN
    patch = im.crop((gx, gy, gx + gw, gy + gh))
    grain = (np.asarray(patch).astype(np.float64)
             - np.asarray(patch.filter(ImageFilter.GaussianBlur(4))).astype(np.float64))
    gm = np.concatenate([grain, grain[::-1]], axis=0)
    gm = np.concatenate([gm, gm[:, ::-1]], axis=1)
    tile = np.tile(gm, (h // gm.shape[0] + 2, w // gm.shape[1] + 2, 1))[:h, :w]

    # Амплитуду зерна подгоняем под соседний участок сукна.
    ring = a[y0 - b:y0, x0:x1] - np.asarray(
        im.crop((x0, y0 - b, x1, y0)).filter(ImageFilter.GaussianBlur(4))).astype(np.float64)
    k = float(np.clip(ring.std() / max(tile.std(), 1e-6), 0.7, 1.4))
    filled = base + tile * k

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    dx = np.maximum(np.abs(xx - (w - 1) / 2) - (w / 2 - RADIUS), 0)
    dy = np.maximum(np.abs(yy - (h - 1) / 2) - (h / 2 - RADIUS), 0)
    t = np.clip((RADIUS - np.hypot(dx, dy)) / FEATHER, 0, 1)
    m = (0.5 - 0.5 * np.cos(np.pi * t))[:, :, None]

    a[y0:y1, x0:x1] = m * filled + (1 - m) * a[y0:y1, x0:x1]
    return Image.fromarray(np.clip(a, 0, 255).round().astype(np.uint8))


# ═══ Запекание своего знака ══════════════════════════════════════════════

def _gold(size, box, shade=None):
    w, h = size
    top, bot = box
    ys = np.clip((np.arange(h) - top) / max(bot - top, 1), 0, 1)
    pos = np.array([s[0] for s in GOLD])
    cols = np.array([s[1] for s in GOLD], dtype=float)
    col = np.stack([np.interp(ys, pos, cols[:, c]) for c in range(3)], axis=1)
    g = np.repeat(col[:, None, :], w, axis=1)
    return g if shade is None else np.clip(g * shade[:, :, None], 0, 255)


def _paint(canvas, mask, shade=None, dy=2.5, alpha=0.55):
    bb = mask.getbbox()
    if not bb:
        return
    sm = mask.filter(ImageFilter.GaussianBlur(2.5 * SS)).point(lambda v: int(v * alpha))
    sh = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    sh.paste(Image.new('RGB', canvas.size, SHADOW), (0, round(dy * SS)), sm)
    canvas.alpha_composite(sh)
    g = _gold(canvas.size, (bb[1], bb[3]), shade)
    canvas.paste(Image.fromarray(g.round().astype('uint8'), 'RGB'), (0, 0), mask)


def brand(base):
    """Кладёт знак «Poker ok 👌» на чистое сукно."""
    canvas = Image.new('RGBA', (base.width * SS, base.height * SS), (0, 0, 0, 0))
    probe = ImageDraw.Draw(Image.new('L', (1, 1)))

    def measure(size):
        f = ImageFont.truetype(FONT, size)
        ws = [probe.textlength(c, font=f) for c in WORD]
        tr = TRACK * size
        return ws, tr, sum(ws) + tr * (len(WORD) - 1)

    lo, hi = 10, 400                       # кегль под заданную ширину надписи
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if measure(int(mid))[2] <= WORD_W * SS else (lo, mid)
    widths, track, total = measure(int(lo))
    f = ImageFont.truetype(FONT, int(lo))

    mask = Image.new('L', canvas.size, 0)
    dm = ImageDraw.Draw(mask)
    x = CX * SS - (total - track) / 2      # трекинг после последней буквы не считаем
    for ch, w in zip(WORD, widths):
        dm.text((x, BASELINE * SS), ch, font=f, fill=255, anchor='ls')
        x += w + track
    _paint(canvas, mask)

    # Эмблема: форму даёт альфа эмодзи, светотень — его же яркость.
    ef = ImageFont.truetype(EMOJI_FONT, 109)   # шрифт растровый, кегль фиксирован
    tmp = Image.new('RGBA', (220, 220), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((20, 20), '\U0001F44C', font=ef, embedded_color=True)
    tmp = tmp.crop(tmp.getbbox())
    h = EMOJI_H * SS
    em = tmp.resize((round(tmp.width * h / tmp.height), h), Image.LANCZOS)

    a = np.asarray(em).astype(float)
    lum, sel = a[:, :, :3].mean(axis=2), a[:, :, 3] > 8
    lo_l, hi_l = np.percentile(lum[sel], 5), np.percentile(lum[sel], 95)
    small = np.clip(0.62 + 0.52 * (lum - lo_l) / max(hi_l - lo_l, 1), 0.5, 1.18)

    pos = (CX * SS - em.width // 2, EMOJI_TOP * SS)
    emask = Image.new('L', canvas.size, 0)
    emask.paste(em.split()[3], pos)
    shade = np.ones(canvas.size[::-1])
    shade[pos[1]:pos[1] + em.height, pos[0]:pos[0] + em.width] = small
    _paint(canvas, emask, shade, dy=3, alpha=0.6)

    # Линейка с ромбом — как на исходном сукне под надписью.
    dc = ImageDraw.Draw(canvas)
    gap, th = 12, max(1, round(1.2 * SS))
    for x0, x1 in ((CX - RULE_HALF, CX - gap), (CX + gap, CX + RULE_HALF)):
        dc.rectangle([x0 * SS, RULE_Y * SS, x1 * SS, RULE_Y * SS + th], fill=(176, 142, 78, 205))
    r, cy = 3.6 * SS, RULE_Y * SS + th / 2
    dc.polygon([(CX * SS, cy - r), (CX * SS + r, cy), (CX * SS, cy + r), (CX * SS - r, cy)],
               fill=(216, 182, 110, 235))

    res = base.convert('RGBA')
    res.alpha_composite(canvas.resize(base.size, Image.LANCZOS))
    return res.convert('RGB')


def main():
    if not os.path.exists(SRC):
        sys.exit('Нет исходника %s' % SRC)
    original = Image.open(SRC).convert('RGB')
    if original.size != SIZE:
        sys.exit('Исходник должен быть %dx%d, а он %s' % (SIZE + (original.size,)))

    plain = clean(original)
    for img, name in ((plain, 'table.webp'), (brand(plain), 'table-branded.webp')):
        assert img.size == SIZE, img.size
        path = os.path.join(IMG, name)
        img.save(path, 'WEBP', **WEBP)
        print('%-20s %6.1f КБ' % (name, os.path.getsize(path) / 1024))


if __name__ == '__main__':
    main()
