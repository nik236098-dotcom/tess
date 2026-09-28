#!/usr/bin/env python3
"""Revision 2 of the beeline_integrated_io_15_91 package. Run on the EXTRACTED package.

    python3 fix_package_1591.py /path/to/extracted/package

Changes made in place (idempotent, refuses any other package):
1. test_beeline.py: the separate SUCCESS push is no longer cut to 4000 characters.
   It goes through the durable outbox (split into confirmed parts by the 15.91 sender);
   if the queue is unavailable it is sent directly, split, never truncated.
2. test_update.py: the preserved-handler hashes no longer depend on ast.dump(), whose
   text changed in Python 3.13; the installer's preflight failed on Python <= 3.12.
3. install.py: the reviewed package copies are installed after the input checksum
   matches, instead of re-applying edits.json line ranges.
4. manifest.json, edits.json, SHA256SUMS.txt, verification.json, test_results.txt are
   regenerated so every checksum the installer verifies is consistent again.
"""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

MARKER = "SUCCESS_PUSH_DURABLE_1591R2"
EXPECTED_INPUT_OUTPUT_SHA = "9e216a70bb1e931c2e9568687c26564a0132bccd6b748dd42fef4eff9335fa50"

OLD_PUSH = '''            r, err = telegram_api(
                cfg,
                "sendMessage",
                {
                    "chat_id": chat,
                    "text": str(success_text)[:4000],
                    "disable_web_page_preview": "true",
                },
            )
            if not r:
                print(f"[Telegram] ОШИБКА отдельного SUCCESS push: {err}", flush=True)
'''
NEW_PUSH = '''            # SUCCESS_PUSH_DURABLE_1591R2: the whole text is queued and delivered in
            # confirmed parts by the durable sender; it is never cut to 4000 characters.
            success_text = str(success_text)
            if not success_text.strip():
                continue
            try:
                _io1591.enqueue_notice(globals(), chat, success_text)
                continue
            except Exception as exc:
                print(
                    "[Telegram] SUCCESS push не поставлен в очередь, отправляю напрямую: "
                    f"{_io1591.redact(exc)}",
                    flush=True,
                )
            for piece in _io1591.split_text(success_text):
                r, err = telegram_api(
                    cfg,
                    "sendMessage",
                    {
                        "chat_id": chat,
                        "text": piece,
                        "disable_web_page_preview": "true",
                    },
                )
                if not r:
                    print(f"[Telegram] ОШИБКА отдельного SUCCESS push: {err}", flush=True)
'''

# Version-independent structural hash: fields that are None or [] are omitted, which is
# what ast.dump() started doing by default in Python 3.13. Attributes are never included.
SIGNATURE_SOURCE = '''
def ast_signature(node):
    if isinstance(node, ast.AST):
        fields = []
        for name, value in ast.iter_fields(node):
            if value is None or (isinstance(value, list) and not value):
                continue
            fields.append((name, ast_signature(value)))
        return (type(node).__name__, tuple(fields))
    if isinstance(node, list):
        return tuple(ast_signature(x) for x in node)
    return repr(node)


def handler_hash(node):
    return hashlib.sha256(repr(ast_signature(node)).encode()).hexdigest()
'''
_ns: dict = {"ast": ast, "hashlib": hashlib}
exec(SIGNATURE_SOURCE, _ns)
ast_signature, handler_hash = _ns["ast_signature"], _ns["handler_hash"]

OLD_TEST_HASH = "            actual=hashlib.sha256(ast.dump(function(name),include_attributes=False).encode()).hexdigest()\n"
NEW_TEST_HASH = "            actual=handler_hash(function(name))\n"

OLD_INPUT_CHECK = '''        if digest(raw) != meta['input_sha256']:
            raise RuntimeError(f'{name}: installed source is different; no code changed. Actual SHA256={digest(raw)}')
'''
NEW_INPUT_CHECK = '''        accepted = {meta['input_sha256'], *meta.get('previous_output_sha256', [])}
        if digest(raw) not in accepted:
            raise RuntimeError(f'{name}: installed source is different; no code changed. Actual SHA256={digest(raw)}')
'''
OLD_RECONSTRUCT = '''        lines = raw.decode('utf-8').splitlines(keepends=True)
        for change in reversed(edits[name]):
            lines[change['start']:change['end']] = change['replacement']
        updated = ''.join(lines).encode('utf-8')
        if digest(updated) != meta['output_sha256']:
            raise RuntimeError(f'{name}: reconstruction checksum failed')
        result[name] = updated
'''
NEW_RECONSTRUCT = '''        # r2: the reviewed package copy is installed once the input checksum matched.
        updated = (package/name).read_bytes()
        if digest(updated) != meta['output_sha256']:
            raise RuntimeError(f'{name}: package copy checksum failed')
        result[name] = updated
'''

README_NOTE = '''

РЕВИЗИЯ 2 (fix_package_1591.py)
1. Отдельный SUCCESS push больше не обрезается до 4000 символов: текст целиком
   ставится в durable-очередь и доставляется частями с подтверждением; при
   недоступной очереди отправляется напрямую частями. Маркер в коде:
   SUCCESS_PUSH_DURABLE_1591R2. Редактируемые статусные сообщения (editMessageText)
   по-прежнему ограничены 4000 символами: часть edit-сообщения разделить нельзя.
2. Хэши защищённых обработчиков в test_update.py считаются по структуре AST без
   полей None/[] и не зависят от версии Python. Прежний ast.dump() давал другой
   текст на Python <= 3.12, из-за чего preflight установщика падал.
3. install.py ставит проверенные копии из пакета после совпадения входного хэша;
   edits.json сохранён как описание изменений. Сервер с уже установленной первой
   сборкой 15.91-io обновляется тем же путём.
Проверка после установки:
grep -c SUCCESS_PUSH_DURABLE_1591R2 /opt/beeline/test_beeline.py   # ожидается 1
'''


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str, what: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{what}: expected exactly one occurrence, found {text.count(old)}; nothing changed")
    return text.replace(old, new, 1)


def add_edit(edits: list, output_before: str, old_block: str, new_block: str) -> None:
    """Record the new change in edits.json using the ORIGINAL (input) line numbers."""
    out_lines = output_before.splitlines(keepends=True)
    old_lines = old_block.splitlines(keepends=True)
    starts = [i for i in range(len(out_lines)) if out_lines[i:i + len(old_lines)] == old_lines]
    if len(starts) != 1:
        raise SystemExit("edits.json: SUCCESS push block not unique in the package output")
    out_start = starts[0]
    delta = 0
    for change in edits:
        if change["start"] + delta + (len(change["replacement"]) - (change["end"] - change["start"])) <= out_start:
            delta += len(change["replacement"]) - (change["end"] - change["start"])
    in_start = out_start - delta
    for change in edits:
        if change["start"] < in_start + len(old_lines) and in_start < change["end"]:
            raise SystemExit("edits.json: the SUCCESS push block overlaps an existing edit")
    edits.append({"start": in_start, "end": in_start + len(old_lines),
                  "replacement": new_block.splitlines(keepends=True)})
    edits.sort(key=lambda c: c["start"])


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    package = Path(argv[1]).resolve()
    app = package / "test_beeline.py"
    for name in ("test_beeline.py", "server_controller.py", "operator_runtime_io.py", "install.py",
                 "test_update.py", "manifest.json", "edits.json", "SHA256SUMS.txt", "README.txt"):
        if not (package / name).is_file():
            raise SystemExit(f"{package / name}: missing; this is not the extracted 15.91 package")
    source = app.read_text("utf-8")
    if MARKER in source:
        print("Already revision 2; nothing changed.")
        return 0
    if sha(app) != EXPECTED_INPUT_OUTPUT_SHA:
        raise SystemExit(f"test_beeline.py SHA256 {sha(app)} is not the reviewed 15.91-io output; nothing changed")
    manifest = json.loads((package / "manifest.json").read_text("utf-8"))
    edits = json.loads((package / "edits.json").read_text("utf-8"))

    # 1. SUCCESS push
    new_source = replace_once(source, OLD_PUSH, NEW_PUSH, "test_beeline.py SUCCESS push")
    compile(new_source, "test_beeline.py", "exec")
    add_edit(edits["test_beeline.py"], source, OLD_PUSH, NEW_PUSH)

    # 2. Version-independent handler hashes
    test_src = (package / "test_update.py").read_text("utf-8")
    test_src = replace_once(test_src, OLD_TEST_HASH, NEW_TEST_HASH, "test_update.py hash line")
    test_src = replace_once(test_src, "\nclass SourceIntegrityTests(unittest.TestCase):\n",
                            "\n" + SIGNATURE_SOURCE + "\n\nclass SourceIntegrityTests(unittest.TestCase):\n",
                            "test_update.py SourceIntegrityTests")
    compile(test_src, "test_update.py", "exec")

    # 3. Installer uses the package copies
    install_src = (package / "install.py").read_text("utf-8")
    install_src = replace_once(install_src, OLD_INPUT_CHECK, NEW_INPUT_CHECK, "install.py input check")
    install_src = replace_once(install_src, OLD_RECONSTRUCT, NEW_RECONSTRUCT, "install.py reconstruct")
    compile(install_src, "install.py", "exec")

    # 4. Manifest and checksums
    tree = ast.parse(new_source)
    for name in manifest["preserved_handlers"]:
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(nodes) != 1:
            raise SystemExit(f"preserved handler {name}: found {len(nodes)}")
        manifest["preserved_ast_sha256"][name] = handler_hash(nodes[0])
    old_hashes = {n: handler_hash(next(x for x in ast.parse(source).body
                                        if isinstance(x, ast.FunctionDef) and x.name == n))
                  for n in manifest["preserved_handlers"]}
    if old_hashes != manifest["preserved_ast_sha256"]:
        raise SystemExit("A preserved handler changed; refusing to re-sign it")
    # A server that already runs the first 15.91 build is upgraded in place as well.
    manifest["files"]["test_beeline.py"]["previous_output_sha256"] = [EXPECTED_INPUT_OUTPUT_SHA]
    manifest["files"]["test_beeline.py"]["output_sha256"] = hashlib.sha256(new_source.encode("utf-8")).hexdigest()
    manifest["revision"] = 2

    app.write_text(new_source, "utf-8")
    (package / "test_update.py").write_text(test_src, "utf-8")
    (package / "install.py").write_text(install_src, "utf-8")
    (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    (package / "edits.json").write_text(json.dumps(edits, ensure_ascii=False, indent=2), "utf-8")
    readme = package / "README.txt"
    if "РЕВИЗИЯ 2" not in readme.read_text("utf-8"):
        readme.write_text(readme.read_text("utf-8").rstrip("\n") + README_NOTE, "utf-8")

    # Prove the package's own suite passes here, then record it.
    run = subprocess.run([sys.executable, "-m", "unittest", "-v", "test_update"], cwd=package,
                         text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    (package / "test_results.txt").write_text(run.stdout, "utf-8")
    if run.returncode:
        print(run.stdout)
        raise SystemExit("Package tests failed after the fix; review test_results.txt")
    ran = next((line for line in run.stdout.splitlines() if line.startswith("Ran ")), "")
    verification = json.loads((package / "verification.json").read_text("utf-8"))
    verification.update({"python": sys.version, "revision": 2, "result": "OK",
                         "tests": int(ran.split()[1]) if ran else None,
                         "exact_input_sha256": manifest["files"]})
    (package / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2), "utf-8")

    sums = [f"{sha(package / name)}  {name}" for name in
            ("test_beeline.py", "server_controller.py", "operator_runtime_io.py", "install.py", "test_update.py",
             "manifest.json", "edits.json", "README.txt", "verification.json", "test_results.txt",
             "install_preflight_results.txt") if (package / name).is_file()]
    (package / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", "utf-8")
    for line in ("__pycache__",):
        for cache in package.glob(line):
            for f in cache.iterdir():
                f.unlink()
            cache.rmdir()
    print(ran + " — OK")
    print("Revision 2 applied to", package)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
