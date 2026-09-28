"""Автоматические шесть пар, отправка и повтор загруженного задания."""
from symbol_matching import match_symbols, overlaps, MATCHER_VERSION, MAX_SHAPE_COST, MIN_MATCH_MARGIN
from pathlib import Path
from datetime import datetime
import json
import os
import re
from time import monotonic
import cv2
import numpy as np
from playwright.sync_api import Error as PlaywrightError

MATCHER_RUNTIME = {}

def configure_matcher_runtime(tab_id=None, heartbeat=None, stage_callback=None):
    MATCHER_RUNTIME["tab_id"] = tab_id
    MATCHER_RUNTIME["heartbeat"] = heartbeat
    MATCHER_RUNTIME["stage_callback"] = stage_callback

def matcher_progress(stage):
    tab_id = MATCHER_RUNTIME.get("tab_id")
    prefix = f"[Вкладка {tab_id}] " if tab_id is not None else ""
    print(prefix + stage, flush=True)
    callback = MATCHER_RUNTIME.get("stage_callback")
    if callback is not None:
        try:
            callback(stage)
        except Exception:
            pass
    hb = MATCHER_RUNTIME.get("heartbeat")
    if hb is not None and tab_id is not None:
        try:
            now = monotonic()
            info = dict(hb.get(str(tab_id)) or {})
            info["phase"] = "PROTECTED_CHECK"
            info["matcher_stage"] = stage
            info["matcher_time"] = now
            info["time"] = now
            hb[str(tab_id)] = info
        except Exception:
            pass


CAPTCHA_SYMBOL_COUNT = 6
CAPTCHA_MAX_ATTEMPTS = 5
CAPTCHA_FRAME_SELECTOR = '[data-testid="advanced-iframe"]'
RETRY_MESSAGE = re.compile(
    r'(?:нужна|требуется|необходима)\s+дополнительная\s+проверка'
    r'|(?:ответ|решение)\s+неверн|неверн\w*\s+(?:ответ|решение)'
    r'|попробуйте\s+(?:ещ[её]\s+раз|снова)', re.I)

def normalize(mask, size=64):
    ys, xs = np.where(mask > 0)
    if len(xs) < 5:
        raise ValueError("Слишком мало пикселей символа. Выдели область точнее.")
    crop = mask[ys.min():ys.max()+1, xs.min():xs.max()+1]
    scale = (size - 16) / max(crop.shape)
    w, h = max(1, round(crop.shape[1]*scale)), max(1, round(crop.shape[0]*scale))
    crop = cv2.resize(crop, (w, h), interpolation=cv2.INTER_NEAREST)
    out = np.zeros((size, size), dtype=np.uint8)
    out[(size-h)//2:(size-h)//2+h, (size-w)//2:(size-w)//2+w] = crop
    return out

def significant_holes(mask):
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return 0
    return sum(1 for c, h in zip(contours, hierarchy[0])
               if h[3] >= 0 and cv2.contourArea(c) >= 12)

def reference_ink(strip):
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    total, labels, stats, _ = cv2.connectedComponentsWithStats(ink)
    for label in range(1, total):
        if stats[label, cv2.CC_STAT_AREA] <= 2:
            ink[labels == label] = 0
    return ink

def _clean_reference_strokes(ink):
    """Очистка проверяется для каждого образца, а не всей полосы вместе."""
    kernel = np.ones((2, 2), np.uint8)
    cleaned = cv2.dilate(cv2.erode(ink, kernel, anchor=(0, 0)), kernel, anchor=(1, 1))
    before = np.count_nonzero(ink)
    after = np.count_nonzero(cleaned)
    if not before or after / before < .85:
        return ink.copy()
    before_components = cv2.connectedComponentsWithStats(ink)[0]
    after_components = cv2.connectedComponentsWithStats(cleaned)[0]
    if after_components > before_components:
        return ink.copy()
    # Отверстия проверяются в нормализованном масштабе.
    if significant_holes(normalize(ink)) != significant_holes(normalize(cleaned)):
        return ink.copy()
    return cleaned

def clean_reference(ink):
    """Remove isolated speckles per symbol before their bounds set its scale.

    Preserve the largest component and substantial disconnected strokes.
    This is deliberately not a largest-component-only filter.
    """
    ink = _clean_reference_strokes(ink)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink)
    if count <= 1:
        return ink
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    limit = max(3, .04 * np.count_nonzero(ink))
    cleaned = ink.copy()
    for label in range(1, count):
        if label != largest and stats[label, cv2.CC_STAT_AREA] <= limit:
            cleaned[labels == label] = 0
    return cleaned


def split_references(strip, count):
    """Разделители могут изгибаться между близкими наклонными символами.

    Допускается один пиксельный мостик между соседями. Пиксели не
    удаляются и не дублируются: каждый принадлежит одному образцу.
    Более широкое пересечение требует ручной разметки.
    """
    if not 2 <= count <= 8:
        raise ValueError("Нужно от 2 до 8 символов.")
    ink = reference_ink(strip)
    h, w = ink.shape
    used = np.flatnonzero(np.any(ink > 0, axis=0))
    if len(used) < count * 3:
        raise ValueError("Недостаточно деталей в ряду образцов.")
    left, right = int(used[0]), int(used[-1]) + 1
    step = (right - left) / count
    separators = [np.full(h, left, dtype=int)]
    for k in range(1, count):
        target = left + k * step
        lo = max(left + 1, int(target - step * .43))
        hi = min(right - 1, int(target + step * .43) + 1)
        if hi <= lo:
            raise ValueError("Слишком узкий ряд образцов.")
        xs = np.arange(lo, hi)
        # Граница x проходит между колонками x-1 и x.
        crossings = ((ink[:, xs-1] > 0) & (ink[:, xs] > 0))
        energy = crossings.astype(float) * 1000
        energy += .015 * ((xs - target) / max(1, step)) ** 2
        cost = energy[0].copy()
        parents = np.zeros((h, len(xs)), dtype=np.int32)
        for y in range(1, h):
            options = np.stack((np.r_[np.inf, cost[:-1]] + .02,
                                cost, np.r_[cost[1:], np.inf] + .02))
            choice = options.argmin(axis=0)
            parents[y] = np.arange(len(xs)) + choice - 1
            cost = options[choice, np.arange(len(xs))] + energy[y]
        index = int(cost.argmin())
        seam = np.empty(h, dtype=int)
        for y in range(h-1, -1, -1):
            seam[y] = xs[index]
            if y:
                index = parents[y, index]
        crossings = ((ink[np.arange(h), seam-1] > 0) &
                     (ink[np.arange(h), seam] > 0))
        if np.count_nonzero(crossings) > 1:
            raise ValueError("Близкие образцы нельзя уверенно разделить автоматически.")
        separators.append(seam)
    separators.append(np.full(h, right, dtype=int))
    refs, spans = [], []
    grid = np.arange(w)[None, :]
    for first, last in zip(separators, separators[1:]):
        selected = (grid >= first[:, None]) & (grid < last[:, None])
        part = np.where(selected, ink, 0).astype(np.uint8)
        ys, xs = np.where(part > 0)
        if len(xs) < 5:
            raise ValueError("Получен пустой образец; нужна ручная разметка.")
        a, b = int(xs.min()), int(xs.max())+1
        refs.append(clean_reference(part[:, a:b]))
        spans.append((a, b))
    return refs, spans

def crop(image, roi):
    x, y, w, h = roi
    return image[y:y+h, x:x+w]

def select_image_boxes(boxes):
    # CSS-размеры: большая иллюстрация и отдельная полоска под ней.
    pictures = [b for b in boxes if b['width'] >= 200 and b['height'] >= 100
                and 1.2 <= b['width'] / b['height'] <= 3]
    if len(pictures) != 1:
        raise RuntimeError("Не удалось однозначно найти большую картинку капчи. Реши её вручную.")
    pic = pictures[0]
    strips = [b for b in boxes if b['width'] >= 70 and 12 <= b['height'] <= 90
              and b['width'] / b['height'] >= 2
              and pic['y'] + pic['height'] - 2 <= b['y'] <= pic['y'] + pic['height'] + 100
              and b['x'] >= pic['x'] - 2
              and b['x'] + b['width'] <= pic['x'] + pic['width'] + 2]
    if len(strips) != 1:
        raise RuntimeError("Не удалось однозначно найти ряд образцов капчи. Реши её вручную.")
    return pic, strips[0]

def screenshot_roi(bounds, frame_bounds, image_shape):
    sx = image_shape[1] / frame_bounds['width']
    sy = image_shape[0] / frame_bounds['height']
    x = round((bounds['x'] - frame_bounds['x']) * sx)
    y = round((bounds['y'] - frame_bounds['y']) * sy)
    right = round((bounds['x'] + bounds['width'] - frame_bounds['x']) * sx)
    bottom = round((bounds['y'] + bounds['height'] - frame_bounds['y']) * sy)
    if x < 0 or y < 0 or right > image_shape[1] or bottom > image_shape[0]:
        raise RuntimeError("Изображение выходит за границы снимка капчи.")
    return x, y, right - x, bottom - y

def find_image_boxes(frame_box):
    frame = frame_box.content_frame
    reference = frame.locator('.AdvancedCaptcha-SilhouetteTask .TaskImage:visible')
    reference.wait_for(state='visible', timeout=15000)
    # Снимаем отображаемый блок целиком: сайт может скрыть img и рисовать на canvas.
    reference.evaluate("""el => new Promise((resolve, reject) => {
        const deadline = performance.now() + 15000;
        function ready() {
            const canvas = el.querySelector('canvas.TaskImage-Canvas');
            const img = el.querySelector('img.TaskImage-Img');
            const visible = node => node && node.getBoundingClientRect().width > 0
                && node.getBoundingClientRect().height > 0
                && getComputedStyle(node).visibility !== 'hidden'
                && getComputedStyle(node).display !== 'none'
                && Number(getComputedStyle(node).opacity) > 0;
            if ((el.classList.contains('TaskImage_painted') && visible(canvas)
                    && canvas.width > 0 && canvas.height > 0)
                    || (visible(img) && img.complete && img.naturalWidth > 0)) {
                requestAnimationFrame(() => requestAnimationFrame(resolve));
            } else if (performance.now() >= deadline) {
                reject(new Error('Блок образцов найден, но изображение не готово'));
            } else {
                setTimeout(ready, 100);
            }
        }
        ready();
    })""")
    frame.locator('body').evaluate("""body => new Promise((resolve, reject) => {
        const deadline = performance.now() + 15000;
        function ready() {
            const images = [...body.querySelectorAll('img:not(.TaskImage-Img)')]
                .filter(img => {
                    const r = img.getBoundingClientRect();
                    return r.width >= 200 && r.height >= 100
                        && getComputedStyle(img).visibility !== 'hidden';
                });
            if (images.length === 1 && images[0].complete && images[0].naturalWidth > 0) {
                requestAnimationFrame(() => requestAnimationFrame(resolve));
            } else if (performance.now() >= deadline) {
                reject(new Error('Основная картинка капчи не загрузилась'));
            } else {
                setTimeout(ready, 100);
            }
        }
        ready();
    })""")
    reference_box = reference.bounding_box()
    if not reference_box or reference_box['width'] <= 0 or reference_box['height'] <= 0:
        raise RuntimeError("Ряд образцов найден, но его размеры недоступны.")
    pictures = []
    images = frame.locator('img:not(.TaskImage-Img)')
    for i in range(images.count()):
        element = images.nth(i)
        if not element.is_visible():
            continue
        if not element.evaluate("img => img.complete && img.naturalWidth > 0"):
            continue
        bounds = element.bounding_box()
        if (bounds and bounds['width'] >= 200 and bounds['height'] >= 100
                and 1.2 <= bounds['width'] / bounds['height'] <= 3):
            pictures.append(bounds)
    if len(pictures) != 1:
        raise RuntimeError(f"Не удалось однозначно найти большую картинку капчи: найдено {len(pictures)}.")
    return pictures[0], reference_box


def click_plan(matches, pic_roi):
    if not matches or any(m.candidate is None for m in matches):
        return None
    boxes = [m.candidate.bounds for m in matches]
    for i, box in enumerate(boxes):
        if any(overlaps(box, other) for other in boxes[i+1:]):
            return None
    points = []
    for match in matches:
        x,y,w,h = match.candidate.bounds
        ys,xs = np.where(match.candidate.mask > 0)
        if not len(xs):
            return None
        closest = int(np.argmin((xs-w/2)**2 + (ys-h/2)**2))
        points.append((pic_roi[0]+x+int(xs[closest]), pic_roi[1]+y+int(ys[closest])))
    return points


def result_preview(picture, strip, refs, spans, matches):
    if len(matches) != len(refs) or any(m.candidate is None for m in matches):
        raise ValueError('Для просмотра нужен полный набор пар.')
    width = max(900, 112*len(refs)+24)
    canvas = np.full((590,width,3),35,np.uint8)
    labelled = picture.copy()
    for i,m in enumerate(matches,1):
        x,y,w,h = m.candidate.bounds
        cv2.rectangle(labelled,(x,y),(x+w,y+h),(0,220,220),1)
        cv2.putText(labelled,str(i),(x,max(15,y)),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,255),1)
    scale = min((width-40)/picture.shape[1],250/picture.shape[0])
    shown=cv2.resize(labelled,None,fx=scale,fy=scale)
    canvas[20:20+shown.shape[0],20:20+shown.shape[1]]=shown
    cv2.putText(canvas,'FULL MATCH SET - REVIEW ALL PAIRS; BEST_EFFORT = GUESS',
                (20,293),cv2.FONT_HERSHEY_SIMPLEX,.48,(255,255,255),1)
    for i,(ref,span,m) in enumerate(zip(refs,spans,matches)):
        x=20+i*112;a,b=span
        canvas[310:358,x:x+64]=cv2.resize(strip[:,a:b],(64,48))
        canvas[370:434,x:x+64]=cv2.cvtColor(normalize(ref),cv2.COLOR_GRAY2BGR)
        canvas[446:510,x:x+64]=cv2.cvtColor(normalize(m.candidate.mask),cv2.COLOR_GRAY2BGR)
        cv2.putText(canvas,f'{i+1}: review',
                    (x,535),cv2.FONT_HERSHEY_SIMPLEX,.4,(255,255,255),1)
        cv2.putText(canvas,m.reason,(x,554),cv2.FONT_HERSHEY_SIMPLEX,.31,(200,200,200),1)
    return canvas


def save_last_match(picture,strip,preview,matches):
    # Four fixed filenames: repeated tests do not fill the disk with runs.
    folder=Path(__file__).resolve().parent/'last_match'/f'worker_{os.getpid()}'
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for name,im in [('picture.png',picture),('strip.png',strip),('preview.png',preview)]:
            ok,encoded=cv2.imencode('.png',im)
            if not ok:
                raise OSError('Не удалось закодировать снимок')
            (folder/name).write_bytes(encoded.tobytes())
        data={'schema_version':3,'matcher_version':MATCHER_VERSION,
              'assignment_policy':'complete_best_effort',
              'time':datetime.now().astimezone().isoformat(),
              'picture_size':[picture.shape[1],picture.shape[0]],
              'strip_size':[strip.shape[1],strip.shape[0]],
              'confidence_thresholds':{'max_shape_cost':MAX_SHAPE_COST,'min_match_margin':MIN_MATCH_MARGIN},
              'matches':[{'index':i+1,'status':m.reason,
                          'bounds':list(m.candidate.bounds) if m.candidate else None,
                          'best_candidate_bounds':list(m.proposed.bounds) if m.proposed else None,
                          'alternative_bounds':list(m.alternative.bounds) if m.alternative else None,
                          'distance':m.distance if np.isfinite(m.distance) else None,
                          'margin':m.margin if np.isfinite(m.margin) else None}
                         for i,m in enumerate(matches)]}
        (folder/'report.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Последнее сравнение сохранено в папке last_match.',flush=True)
    except (OSError,cv2.error) as exc:
        print(f'Не удалось сохранить сравнение: {exc}',flush=True)


def active_captcha_frame(page):
    """Reacquire the current iframe; a retry may replace its DOM element."""
    frames = page.locator(CAPTCHA_FRAME_SELECTOR)
    visible = [frames.nth(i) for i in range(frames.count()) if frames.nth(i).is_visible()]
    if len(visible) > 1:
        raise RuntimeError('Одновременно открыто несколько окон капчи.')
    return visible[0] if visible else None


def captcha_task_key(frame_box):
    # Source data excludes click markers and transient response messages.
    # A canvas reference can change while its hidden source image stays the same.
    return frame_box.content_frame.locator('body').evaluate("""body => {
        const images = [...body.querySelectorAll('img')].map(img =>
            [img.currentSrc || img.src, img.naturalWidth, img.naturalHeight]);
        const canvases = [...body.querySelectorAll('.TaskImage-Canvas')].map(canvas => {
            let pixels = '';
            try { pixels = canvas.toDataURL(); } catch (_) {}
            return [canvas.width, canvas.height, pixels];
        });
        return JSON.stringify([images, canvases]);
    }""", timeout=2000)


def capture_captcha(frame_box):
    frame_box.wait_for(state='visible', timeout=15000)
    frame_box.scroll_into_view_if_needed()
    picture_box, reference_box = find_image_boxes(frame_box)
    box = frame_box.bounding_box()
    if not box:
        raise RuntimeError('Недоступно положение окна задания.')
    key = captcha_task_key(frame_box)
    # Keep source masks at CSS resolution even on a high-DPI display. Otherwise
    # a one-pixel bridge in the reference strip becomes two pixels and cannot split.
    image = cv2.imdecode(np.frombuffer(frame_box.screenshot(scale='css'), np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError('Снимок не удалось прочитать.')
    if captcha_task_key(frame_box) != key:
        raise RuntimeError('Задание сменилось во время получения снимка.')
    pic_roi = screenshot_roi(picture_box, box, image.shape)
    ref_roi = screenshot_roi(reference_box, box, image.shape)
    return dict(key=key, image=image, box=box, pic_roi=pic_roi, ref_roi=ref_roi,
                picture=crop(image, pic_roi), strip=crop(image, ref_roi))


def submit_captcha_points(page, frame_box, snapshot, points):
    if len(points) != CAPTCHA_SYMBOL_COUNT:
        raise ValueError('Для отправки нужны ровно шесть точек.')
    image, box = snapshot['image'], snapshot['box']
    if captcha_task_key(frame_box) != snapshot['key']:
        raise RuntimeError('Задание обновилось во время распознавания.')
    current = cv2.imdecode(np.frombuffer(frame_box.screenshot(scale='css'), np.uint8), cv2.IMREAD_COLOR)
    if current is None or current.shape != image.shape:
        raise RuntimeError('Размер задания изменился во время распознавания.')
    for roi in (snapshot['pic_roi'], snapshot['ref_roi']):
        if cv2.absdiff(crop(current, roi), crop(image, roi)).mean() > 2:
            raise RuntimeError('Содержимое задания изменилось во время распознавания.')
    for x, y in points:
        if page.is_closed():
            raise RuntimeError('Браузер закрыт.')
        if captcha_task_key(frame_box) != snapshot['key']:
            raise RuntimeError('Задание сменилось во время кликов.')
        current_box = frame_box.bounding_box()
        if not current_box or any(abs(current_box[k]-box[k]) > 1 for k in ('width','height')):
            raise RuntimeError('Размер окна задания изменился во время кликов.')
        page.mouse.click(current_box['x'] + x * current_box['width'] / image.shape[1],
                         current_box['y'] + y * current_box['height'] / image.shape[0])
        page.wait_for_timeout(300)
    if captcha_task_key(frame_box) != snapshot['key']:
        raise RuntimeError('Задание сменилось перед отправкой.')
    frame_box.content_frame.get_by_role(
        'button', name=re.compile(r'^\s*отправить\s*$', re.I)).click(timeout=10000)
    print('Нажаты все 6 символов и кнопка «отправить».', flush=True)


def solve_and_submit_captcha(page, frame_box):
    matcher_progress('CAPTURE_START')
    snapshot = capture_captcha(frame_box)
    matcher_progress('CAPTURE_DONE')
    matcher_progress('SPLIT_START')
    refs, spans = split_references(snapshot['strip'], CAPTCHA_SYMBOL_COUNT)
    matcher_progress('SPLIT_DONE')
    matcher_progress('MATCH_START')
    matches = match_symbols(snapshot['picture'], refs, matcher_progress)
    matcher_progress('MATCH_DONE')
    points = click_plan(matches, snapshot['pic_roi'])
    if points is None or len(points) != CAPTCHA_SYMBOL_COUNT:
        raise ValueError('Некорректные координаты полного набора из шести фигур.')
    # Keep the last diagnostic files without opening any preview window.
    preview = result_preview(snapshot['picture'], snapshot['strip'], refs, spans, matches)
    save_last_match(snapshot['picture'], snapshot['strip'], preview, matches)
    matcher_progress('SUBMIT_START')
    submit_captcha_points(page, frame_box, snapshot, points)
    matcher_progress('SUBMIT_DONE')
    return snapshot['key']


def wait_captcha_result(page, previous_key, timeout=25, clock=None):
    clock = clock or monotonic
    started = clock()
    hidden_since = None
    while clock() - started < timeout:
        if page.is_closed():
            return 'closed'
        frame_box = active_captcha_frame(page)
        if frame_box is None:
            if hidden_since is None:
                hidden_since = clock()
            # An iframe replacement can briefly remove the old element.
            if previous_key is not None and clock() - hidden_since >= 1:
                return 'passed'
        else:
            hidden_since = None
            try:
                if previous_key is None or captcha_task_key(frame_box) != previous_key:
                    return 'retry'
                text = frame_box.content_frame.locator('body').inner_text(timeout=1500)
                button = frame_box.content_frame.get_by_role(
                    'button', name=re.compile(r'^\s*отправить\s*$', re.I))
                # Give submission time to enter its loading state before reading
                # a message that may already have been visible above the task.
                if (clock() - started >= 2 and RETRY_MESSAGE.search(text)
                        and button.count() == 1 and button.is_visible() and button.is_enabled()):
                    return 'retry'
            except PlaywrightError:
                # The iframe may be replaced while the response is rendering.
                pass
        page.wait_for_timeout(250)
    raise RuntimeError(f'Сайт не подтвердил отправку капчи за {timeout:g} секунд; '
                       'следующий шаг не запущен.')


def refresh_captcha(page, previous_key, timeout=20, clock=None):
    """Use a fresh task; never click an unchanged, partly selected image again."""
    clock = clock or monotonic
    frame_box = active_captcha_frame(page)
    if frame_box is None or captcha_task_key(frame_box) != previous_key:
        return
    buttons = frame_box.content_frame.get_by_role(
        'button', name=re.compile(r'обнов|нов(?:ое|ую|ая)\s+(?:задание|картин)'
                                  r'|попробовать\s+(?:ещ[её]|снова)|повторить', re.I))
    for i in range(buttons.count()):
        button = buttons.nth(i)
        if button.is_visible() and button.is_enabled():
            button.click(timeout=5000)
            break
    else:
        raise RuntimeError('Капча запросила повтор, но кнопка нового задания недоступна.')
    deadline = clock() + timeout
    while clock() < deadline:
        if page.is_closed():
            return
        frame_box = active_captcha_frame(page)
        if frame_box is None:
            # Do not interpret this transient disappearance as a fresh task.
            page.wait_for_timeout(250)
            continue
        try:
            if captcha_task_key(frame_box) != previous_key:
                page.wait_for_timeout(400)
                return
        except PlaywrightError:
            pass
        page.wait_for_timeout(250)
    raise RuntimeError('После обновления новая картинка капчи не загрузилась.')


def try_local_captcha(page, frame_box=None):
    last_submitted_key = None
    for attempt in range(1, CAPTCHA_MAX_ATTEMPTS + 1):
        if page.is_closed():
            return False
        frame_box = active_captcha_frame(page)
        if frame_box is None:
            outcome = wait_captcha_result(page, last_submitted_key)
            if outcome == 'passed':
                return True
            if outcome == 'closed':
                return False
            frame_box = active_captcha_frame(page)
        matcher_progress(f'ATTEMPT_{attempt}/{CAPTCHA_MAX_ATTEMPTS}')
        previous_key = None
        try:
            previous_key = captcha_task_key(frame_box)
            previous_key = solve_and_submit_captcha(page, frame_box)
            last_submitted_key = previous_key
        except (ValueError, RuntimeError, cv2.error, PlaywrightError) as exc:
            if page.is_closed():
                return False
            if attempt == CAPTCHA_MAX_ATTEMPTS:
                raise RuntimeError(f'Капча: исчерпаны {CAPTCHA_MAX_ATTEMPTS} попыток: {exc}') from exc
            print(f'Повтор с новым заданием: {exc}', flush=True)
            refresh_captcha(page, previous_key)
            continue
        outcome = wait_captcha_result(page, previous_key)
        if outcome == 'passed':
            print('Капча закрылась. Продолжаю основной сценарий.', flush=True)
            return True
        if outcome == 'closed':
            return False
        if attempt == CAPTCHA_MAX_ATTEMPTS:
            raise RuntimeError(f'Капча не пройдена за {CAPTCHA_MAX_ATTEMPTS} попыток.')
        print('Сайт запросил дополнительную проверку. Повторяю...', flush=True)
        refresh_captcha(page, previous_key)
    raise RuntimeError('Капча не завершена.')