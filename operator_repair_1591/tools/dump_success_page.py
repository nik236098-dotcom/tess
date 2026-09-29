#!/usr/bin/env python3
"""Show what the bot can and cannot read on the open registration tabs.

Connects to the running Chromium over CDP (the port is taken from the beeline journal
or passed as an argument), and for every tab whose URL contains "registration" prints:
the URL, the length of body.innerText, the frames, and the visible text collected by
walking the DOM *including shadow roots*. Digits are replaced by X so the output can be
shared. Read-only: nothing is clicked or changed.

    /opt/beeline/venv/bin/python dump_success_page.py            # port from journalctl
    /opt/beeline/venv/bin/python dump_success_page.py 52495      # explicit CDP port
"""
import re
import subprocess
import sys

from playwright.sync_api import sync_playwright

WALK_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  const vis = el => {
    try {
      const r = el.getBoundingClientRect(), s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
    } catch (_) { return false; }
  };
  let shadowRoots = 0, inputs = 0;
  const walk = root => {
    const nodes = root.querySelectorAll ? root.querySelectorAll('*') : [];
    for (const el of nodes) {
      if (el.shadowRoot) { shadowRoots++; walk(el.shadowRoot); }
      const tag = el.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT') continue;
      if ((tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') && vis(el)) {
        inputs++;
        let label = '';
        try { const lab = el.id && root.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (lab) label = lab.textContent; } catch (_) {}
        out.push(`[${tag.toLowerCase()} name=${el.name || ''} id=${el.id || ''} placeholder=${el.placeholder || ''} label=${(label || '').trim()}] ${el.value || ''}`);
        continue;
      }
      if (el.children.length) continue;
      if (!vis(el)) continue;
      const t = (el.textContent || '').replace(/\s+/g, ' ').trim();
      if (!t || t.length > 200) continue;
      const key = tag + '|' + t;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(`<${tag.toLowerCase()}> ${t}`);
    }
  };
  walk(document);
  return {shadowRoots, inputs, lines: out.slice(0, 400),
          innerTextLength: ((document.body && document.body.innerText) || '').length,
          title: document.title};
}
"""


def mask(text):
    return re.sub(r"\d", "X", str(text))


def cdp_url_from_journal():
    try:
        log = subprocess.run(["journalctl", "-u", "beeline", "-n", "5000", "--no-pager", "-o", "cat"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception as exc:
        raise SystemExit(f"journalctl недоступен ({exc}); укажите порт CDP аргументом")
    hits = re.findall(r"Chromium #\d+ готов: (http://127\.0\.0\.1:\d+)", log)
    if not hits:
        raise SystemExit("В журнале нет строки «Chromium #1 готов: http://127.0.0.1:PORT»; укажите порт аргументом")
    return hits[-1]


def main(argv):
    cdp = f"http://127.0.0.1:{argv[1]}" if len(argv) > 1 else cdp_url_from_journal()
    print("CDP:", cdp)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp, timeout=20000)
        pages = [pg for ctx in browser.contexts for pg in ctx.pages]
        print(f"Вкладок всего: {len(pages)}")
        for pg in pages:
            url = pg.url
            if "registration" not in url and "esim" not in url:
                continue
            print("\n" + "=" * 78)
            print("URL:", mask(url))
            try:
                print("Фреймы:", [mask(f.url)[:100] for f in pg.frames])
            except Exception as exc:
                print("Фреймы: ошибка", type(exc).__name__, exc)
            for target in [pg] + [f for f in pg.frames if f != pg.main_frame]:
                try:
                    data = target.evaluate(WALK_JS)
                except Exception as exc:
                    print("  evaluate не удался:", type(exc).__name__, mask(exc))
                    continue
                if not data or not data.get("lines"):
                    continue
                print(f"-- frame {mask(getattr(target, 'url', ''))[:100]}")
                print(f"   title={mask(data.get('title'))!r} innerText={data.get('innerTextLength')} символов, "
                      f"shadowRoots={data.get('shadowRoots')}, inputs={data.get('inputs')}")
                for line in data["lines"]:
                    print("   ", mask(line)[:200])
        browser.close()  # closes only this CDP connection, not the browser
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
