#!/usr/bin/env python3
"""Exact-version integrated installer. Default is a no-write compatibility check."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

FILES = ('operator_runtime_io.py', 'test_beeline.py', 'server_controller.py', 'symbol_matching.py')

def digest(data):
    return hashlib.sha256(data).hexdigest()


def reconstruct(app, package):
    manifest = json.loads((package/'manifest.json').read_text('utf-8'))
    edits = json.loads((package/'edits.json').read_text('utf-8'))
    result = {}
    originals = {}
    for name in ('test_beeline.py', 'server_controller.py', 'symbol_matching.py'):
        path = app/name
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f'{path}: expected a regular file, not a link')
        raw = path.read_bytes()
        originals[name] = raw
        meta = manifest['files'][name]
        if digest(raw) == meta['output_sha256']:
            result[name] = raw
            continue
        accepted = {meta['input_sha256'], *meta.get('previous_output_sha256', [])}
        if digest(raw) not in accepted:
            raise RuntimeError(f'{name}: installed source is different; no code changed. Actual SHA256={digest(raw)}')
        # r2: the reviewed package copy is installed once the input checksum matched.
        updated = (package/name).read_bytes()
        if digest(updated) != meta['output_sha256']:
            raise RuntimeError(f'{name}: package copy checksum failed')
        result[name] = updated
    raw = (package/'operator_runtime_io.py').read_bytes()
    if digest(raw) != manifest['files']['operator_runtime_io.py']['output_sha256']:
        raise RuntimeError('Support module checksum failed')
    result['operator_runtime_io.py'] = raw
    for name, raw in result.items():
        compile(raw.decode('utf-8'), name, 'exec')
    return originals, result


def atomic_write(path, raw, mode=0o600):
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


class SystemService:
    def status(self):
        proc = subprocess.run(['systemctl', 'show', 'beeline', '-p', 'ActiveState', '-p', 'SubState',
                               '-p', 'MainPID', '-p', 'NRestarts'], check=True, text=True,
                              capture_output=True, timeout=15)
        return dict(line.split('=',1) for line in proc.stdout.splitlines() if '=' in line)
    def stop(self):
        subprocess.run(['systemctl','stop','beeline'], check=True, timeout=90)
    def start(self):
        subprocess.run(['systemctl','start','beeline'], check=True, timeout=45)
    def healthy(self):
        initial = self.status()
        time.sleep(6)
        final = self.status()
        return (initial.get('ActiveState') == final.get('ActiveState') == 'active'
                and initial.get('MainPID') == final.get('MainPID')
                and final.get('MainPID') not in {None,'0'}
                and initial.get('NRestarts') == final.get('NRestarts'))


def check_imports(app):
    python = app/'venv/bin/python'
    if not python.is_file():
        raise RuntimeError('venv/bin/python is missing')
    subprocess.run([str(python), '-B', '-c',
        'import test_beeline as a; import server_controller as c; import symbol_matching as s; '
        'assert a.IO_BUILD_VERSION == c.IO_BUILD_VERSION == "15.91-io"; '
        'assert a._io1591.VERSION == "15.91-io"; assert s.MATCHER_VERSION == "14.1"; print("IMPORT OK")'],
        cwd=app, check=True, timeout=45)


def apply_bundle(app, expected_inputs, output, service, restart=False, import_check=check_imports):
    before = service.status()
    active = before.get('ActiveState') == 'active'
    if before.get('ActiveState') not in {'active','inactive','failed'}:
        raise RuntimeError('Service is transitioning or its state is unknown; retry after checking it')
    if active and not restart:
        raise RuntimeError('Service is running. --restart is required; it will close its current browser processes.')
    previous = {}
    for name in FILES:
        file = app/name
        if file.is_symlink(): raise RuntimeError('Refusing to replace a symlink: '+name)
        previous[name] = (file.read_bytes(), file.stat().st_mode & 0o777) if file.exists() else None
    for name, raw in expected_inputs.items():
        if (app/name).read_bytes() != raw:
            raise RuntimeError('Source changed after preflight; no files replaced')
    if all(previous[n] is not None and previous[n][0] == output[n] for n in FILES):
        print('ALREADY INSTALLED. No restart performed.')
        return None
    backup = app/'code_backups'/('io1591_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
    backup.mkdir(parents=True, mode=0o700)
    state = {'version':'15.91-io', 'previous':{}, 'data_files_modified':False}
    for name, old in previous.items():
        if old is None:
            state['previous'][name] = None
        else:
            atomic_write(backup/name, old[0], old[1])
            state['previous'][name] = {'sha256':digest(old[0]), 'mode':old[1]}
    atomic_write(backup/'backup_manifest.json', json.dumps(state, indent=2).encode())
    writes_started = False
    stopped = False
    try:
        if active:
            service.stop(); stopped = True
        for name, raw in expected_inputs.items():
            if (app/name).read_bytes() != raw:
                raise RuntimeError('Source changed during service stop; refusing to overwrite it')
        writes_started = True
        for name in FILES:
            old = previous[name]
            atomic_write(app/name, output[name], old[1] if old else 0o600)
        import_check(app)
        if restart:
            service.start()
            if not service.healthy():
                raise RuntimeError('Controller failed the startup stability check')
        print('UPDATE APPLIED: 15.91-io')
        print('Code backup:', backup)
        print('Service:', 'active' if restart else 'left stopped')
        print('Browser/contract end-to-end checks were NOT performed by this installer.')
        return backup
    except BaseException:
        if writes_started:
            try: service.stop()
            except Exception: pass
            for name, old in previous.items():
                if old is None: (app/name).unlink(missing_ok=True)
                else: atomic_write(app/name, old[0], old[1])
        if active and (stopped or writes_started):
            try: service.start()
            except Exception as error:
                print('Old code restored, but service restart failed:', type(error).__name__, file=sys.stderr)
        print('INSTALL FAILED. Code restored where necessary; user data was not rolled back.', file=sys.stderr)
        raise


def offline_tests(package, output):
    with tempfile.TemporaryDirectory(prefix='io1591_test_') as name:
        stage = Path(name)
        for filename, raw in output.items(): (stage/filename).write_bytes(raw)
        for filename in ('test_update.py','manifest.json','install.py'):
            shutil.copy2(package/filename, stage/filename)
        env = os.environ.copy()
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        test_run = subprocess.run([sys.executable, '-m', 'unittest', '-q', 'test_update'],
                                  cwd=stage, env=env, text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=90)
        if test_run.returncode:
            print(test_run.stdout, file=sys.stderr)
            raise RuntimeError('Offline tests failed; no service operation performed')
        summary = next((line for line in test_run.stdout.splitlines() if line.startswith('Ran ')), 'Offline tests completed')
        print(summary + ' — OK', flush=True)


def ensure_proxy_configured(app):
    """r3: the code no longer embeds the Telegram proxy; it must be in telegram_config.json."""
    try:
        cfg = json.loads((app/'telegram_config.json').read_text('utf-8'))
    except (OSError, ValueError):
        cfg = {}
    if not str((cfg or {}).get('proxy') or '').strip():
        raise RuntimeError('telegram_config.json has no "proxy". Add "proxy": "socks5h://user:password@host:port" '
                           '(the value that was TELEGRAM_DEFAULT_PROXY in the old code) before installing; '
                           'this build does not embed it and would otherwise reach Telegram without the proxy.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, default=Path('/opt/beeline'))
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--restart', action='store_true', help='Explicitly permit stopping/starting beeline and its browser')
    args = parser.parse_args()
    app = args.app.resolve(); package = Path(__file__).resolve().parent
    original, output = reconstruct(app, package)
    ensure_proxy_configured(app)
    print('SOURCE CHECKSUMS OK. Running offline tests before any service operation.', flush=True)
    offline_tests(package, output)
    if not args.apply:
        print('CHECK OK. No source files or services changed.')
        return
    if app != Path('/opt/beeline'):
        raise SystemExit('Production apply is restricted to /opt/beeline')
    if os.geteuid() != 0:
        raise SystemExit('Run apply with sudo')
    import fcntl
    with (app/'.io1591_install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        apply_bundle(app, original, output, SystemService(), restart=args.restart)


if __name__ == '__main__':
    main()
