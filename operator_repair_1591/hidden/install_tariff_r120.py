#!/usr/bin/env python3
"""Hidden revision 120: scroll to bee START and do not leave the tariff picker early.

Not published to GitHub, so the «Обновить бота» tab does not offer it.
The marker deliberately has no _1591R number, so the shown revision stays the published one.
"""
from pathlib import Path
import sys

PATH = Path("/opt/beeline/test_beeline.py")
MARKER = "# TARIFF_STAND_HIDDEN revision 120: долистать до bee START, не уходить из «выберите тариф», пока окно открыто. В «Обновить бота» не публикуется."

def main():
    text = PATH.read_text(encoding="utf-8")
    if "picker_open = header.count() > 0 and header.first.is_visible()" in text and "title.scroll_into_view_if_needed(timeout=1500)" in text:
        if MARKER not in text:
            text = text.rstrip() + "\n\n" + MARKER + "\n"
            PATH.write_text(text, encoding="utf-8")
        print("ALREADY INSTALLED r120-hidden")
        return
    old = '''            if not title.is_visible():
                continue
            card = title.locator(
'''
    new = '''            try:
                title.scroll_into_view_if_needed(timeout=1500)
            except Exception:
                pass
            if not title.is_visible():
                continue
            card = title.locator(
'''
    if text.count(old) != 1:
        sys.exit(f"title block found {text.count(old)} times, not patched")
    text = text.replace(old, new, 1)
    old = '''            button = card.get_by_role("button", name=_CHOOSE_BUTTON_RE)
            if button.count() > 0 and button.first.is_visible():
                return button.first
'''
    new = '''            button = card.get_by_role("button", name=_CHOOSE_BUTTON_RE)
            if button.count() > 0:
                try:
                    button.first.scroll_into_view_if_needed(timeout=1500)
                except Exception:
                    pass
                if button.first.is_visible():
                    return button.first
'''
    if text.count(old) != 1:
        sys.exit(f"button block found {text.count(old)} times, not patched")
    text = text.replace(old, new, 1)
    old = '''            try:
                choose_button.click(timeout=7000, no_wait_after=True)
                choose_clicked = True
            except Exception as exc:
                diagnostic.write(
                    "second_choose_click_exception",
                    attempt=choose_attempt,
                    error_type=type(exc).__name__,
                )

            # Даже если click() сообщил timeout, действие могло уже состояться.
            state_deadline = monotonic() + 8
            while monotonic() < state_deadline:
                try:
                    if page.locator('input#esim[name="sim"]').count() > 0:
                        choose_clicked = True
                        break
                    if page.get_by_text(TARIFF_NAME, exact=True).count() > 0:
                        choose_clicked = True
                        break
                except Exception:
                    pass
                page.wait_for_timeout(250)
'''
    new = '''            try:
                choose_button.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
            try:
                choose_button.click(timeout=7000, no_wait_after=True)
            except Exception as exc:
                diagnostic.write(
                    "second_choose_click_exception",
                    attempt=choose_attempt,
                    error_type=type(exc).__name__,
                )

            # Окно «выберите тариф» ещё открыто: корзина под ним не считается выбором.
            state_deadline = monotonic() + 8
            while monotonic() < state_deadline:
                picker_open = False
                try:
                    header = page.get_by_text(_TARIFF_PICKER_HEADER_RE_1591R32)
                    picker_open = header.count() > 0 and header.first.is_visible()
                except Exception:
                    picker_open = False
                if not picker_open:
                    try:
                        if page.locator('input#esim[name="sim"]').count() > 0:
                            choose_clicked = True
                            break
                    except Exception:
                        pass
                page.wait_for_timeout(250)
'''
    if text.count(old) != 1:
        sys.exit(f"choose loop found {text.count(old)} times, not patched")
    text = text.replace(old, new, 1)
    if MARKER not in text:
        text = text.rstrip() + "\n\n" + MARKER + "\n"
    bak = PATH.with_name("test_beeline.py.bak-r120-hidden")
    if not bak.exists():
        bak.write_bytes(PATH.read_bytes())
    PATH.write_text(text, encoding="utf-8")
    print("INSTALLED r120-hidden")

if __name__ == "__main__":
    main()
