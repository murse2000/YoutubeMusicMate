"""격리된 설치 폴더에서 실제 배포 업데이트 프로그램을 검증한다."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from musicmate.updater import decode_manifest, instance_lock, platform_key, select_asset

folder = Path(sys.argv[1]).resolve()
envelope = (folder / 'latest.json').read_text(encoding='utf-8')
manifest = decode_manifest(envelope.encode())
key = platform_key()
asset = select_asset(manifest, key)
package = folder / asset['url'].rsplit('/', 1)[1]
with package.open('rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == asset['sha256']
assert package.stat().st_size == asset['size']

from musicmate.installer import extract_package

with tempfile.TemporaryDirectory(prefix='musicmate-release-verify-') as temporary:
    work = Path(temporary)
    root_name = 'YoutubeMusicMate.app' if sys.platform == 'darwin' else 'YoutubeMusicMate'
    extract_package(package, work / 'reference', root_name)
    reference = work / 'reference' / root_name
    relative_exe = Path('Contents/MacOS/YoutubeMusicMate') if sys.platform == 'darwin' else Path('YoutubeMusicMate.exe')
    relative_helper = Path('Contents/Frameworks/updater/MusicMateUpdater') if sys.platform == 'darwin' else Path('_internal/updater/MusicMateUpdater.exe')
    helper = work / relative_helper.name
    shutil.copy2(reference / relative_helper, helper)
    shutil.copy2(package, work / 'package.tar.gz')
    target = work / root_name
    target.mkdir()
    marker = target / 'old-version-marker'
    marker.write_text('기존 앱 보존 확인', encoding='utf-8')
    lock_path = instance_lock().lock_file
    parent = subprocess.Popen([sys.executable, '-u', '-c',
        'import sys,time; from filelock import FileLock; lock=FileLock(sys.argv[1]); lock.acquire(); print("ready",flush=True); time.sleep(180)',
        lock_path], stdout=subprocess.PIPE, text=True)
    assert parent.stdout.readline().strip() == 'ready'
    plan = {'target': str(target), 'platform': key, 'envelope': envelope,
            'processes': [{'pid': parent.pid, 'created': psutil.Process(parent.pid).create_time()}]}
    plan_path = work / 'plan.json'
    plan_path.write_text(json.dumps(plan), encoding='utf-8')
    process = subprocess.Popen([str(helper), str(plan_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 30
        while not (work / 'ready').exists():
            if process.poll() is not None:
                raise RuntimeError(process.communicate())
            if time.monotonic() > deadline:
                raise TimeoutError('업데이트 프로그램 준비 시간 초과')
            time.sleep(.2)
        assert marker.exists() and parent.poll() is None
        print('PASS: 실행 중인 앱과 잠금이 있는 동안 설치하지 않음', flush=True)
        parent.terminate(); parent.wait(timeout=10)
        output = process.communicate(timeout=120)
        assert process.returncode == 0, output
        assert not marker.exists()
        installed_exe = target / relative_exe
        assert installed_exe.read_bytes() == (reference / relative_exe).read_bytes()
        if sys.platform == 'darwin':
            subprocess.run(['codesign', '--verify', '--deep', '--strict', str(target)], check=True)
        print('PASS: 프로세스 종료 후 실제 패키지 교체 및 실행 파일 일치', flush=True)
        deadline = time.monotonic() + 30
        launched = None
        while time.monotonic() < deadline:
            for candidate in psutil.process_iter():
                try:
                    if Path(candidate.exe()).resolve() == installed_exe.resolve():
                        launched = candidate
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            if launched:
                break
            time.sleep(.2)
        assert launched, '업데이트 후 앱 프로세스가 시작되지 않음'
        time.sleep(4)
        assert launched.is_running(), '업데이트 후 앱이 조기 종료됨'
        print('PASS: 교체된 배포 앱이 다시 실행되어 유지됨', flush=True)
    finally:
        if parent.poll() is None:
            parent.terminate(); parent.wait(timeout=10)
        if process.poll() is None:
            process.terminate(); process.wait(timeout=10)
        for candidate in psutil.process_iter():
            try:
                if Path(candidate.exe()).is_relative_to(target):
                    candidate.terminate()
                    candidate.wait(timeout=15)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
