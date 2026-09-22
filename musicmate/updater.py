"""서명된 업데이트 조회와 사용자 동의 이후의 다운로드를 담당한다."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from filelock import FileLock

from musicmate import __version__
from musicmate.update_config import PUBLIC_KEY, REPOSITORY


FEED = f"https://github.com/{REPOSITORY}/releases/latest/download/latest.json"


def state_dir() -> Path:
    if sys.platform == 'win32':
        root = Path(os.environ['LOCALAPPDATA'])
    else:
        root = Path.home() / 'Library' / 'Application Support'
    path = root / 'YoutubeMusicMate'
    path.mkdir(parents=True, exist_ok=True)
    return path


def instance_lock() -> FileLock:
    return FileLock(str(state_dir() / 'application.lock'))


def platform_key() -> str:
    if sys.platform == 'darwin':
        return 'macos-arm64' if platform.machine() == 'arm64' else 'macos-x64'
    if sys.platform == 'win32':
        return 'windows-x64'
    raise RuntimeError('이 운영체제의 자동업데이트는 지원하지 않습니다.')


def version_tuple(version: str) -> tuple[int, ...]:
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('올바르지 않은 업데이트 버전입니다.')
    return tuple(map(int, version.split('.')))


def decode_manifest(raw: bytes, public_key: str = PUBLIC_KEY) -> dict:
    envelope = json.loads(raw)
    payload = base64.b64decode(envelope['payload'], validate=True)
    signature = base64.b64decode(envelope['signature'], validate=True)
    Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key)).verify(signature, payload)
    manifest = json.loads(payload)
    version_tuple(manifest['version'])
    return manifest


def select_asset(manifest: dict, key: str) -> dict:
    asset = manifest['platforms'][key]
    prefix = f"https://github.com/{REPOSITORY}/releases/download/v{manifest['version']}/"
    if not asset['url'].startswith(prefix) or not re.fullmatch(r'[a-f0-9]{64}', asset['sha256']):
        raise ValueError('업데이트 파일 정보가 올바르지 않습니다.')
    if not 0 < asset['size'] < 2_000_000_000:
        raise ValueError('업데이트 파일 크기가 올바르지 않습니다.')
    return asset


def check_update() -> dict | None:
    response = requests.get(FEED, timeout=20)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    manifest = decode_manifest(response.content)
    if version_tuple(manifest['version']) <= version_tuple(__version__):
        return None
    select_asset(manifest, platform_key())
    return {'manifest': manifest, 'envelope': response.text}


def install_root() -> Path:
    if not getattr(sys, 'frozen', False):
        raise RuntimeError('자동 설치는 배포된 앱에서 사용할 수 있습니다.')
    exe = Path(sys.executable).resolve()
    root = exe.parents[2] if sys.platform == 'darwin' else exe.parent
    if root.name not in ('YoutubeMusicMate.app', 'YoutubeMusicMate'):
        raise RuntimeError('기본 앱 폴더 이름을 유지한 상태에서 업데이트하세요.')
    if '/AppTranslocation/' in str(root) or str(root).startswith('/Volumes/'):
        raise RuntimeError('앱을 응용 프로그램 폴더로 옮긴 뒤 업데이트하세요.')
    # 대상 폴더의 옆에서 교체 준비가 가능한지 실제로 확인한다.
    with tempfile.TemporaryDirectory(prefix='.musicmate-check-', dir=root.parent):
        pass
    return root


def prepare_update(update: dict, cancel, progress) -> Path:
    target = install_root()
    manifest = decode_manifest(update['envelope'].encode())
    asset = select_asset(manifest, platform_key())
    stage = Path(tempfile.mkdtemp(prefix='update-', dir=state_dir()))
    try:
        package = stage / 'package.tar.gz'
        digest = hashlib.sha256()
        size = 0
        with requests.get(asset['url'], stream=True, timeout=(15, 30)) as response:
            response.raise_for_status()
            with package.open('wb') as stream:
                for chunk in response.iter_content(1024 * 256):
                    if cancel.is_set():
                        raise RuntimeError('업데이트 다운로드를 취소했습니다.')
                    size += len(chunk)
                    if size > asset['size']:
                        raise ValueError('업데이트 파일 크기가 일치하지 않습니다.')
                    stream.write(chunk)
                    digest.update(chunk)
                    progress(int(size / asset['size'] * 95), '업데이트 다운로드 중…')
        if cancel.is_set():
            raise RuntimeError('업데이트 다운로드를 취소했습니다.')
        if size != asset['size'] or digest.hexdigest() != asset['sha256']:
            raise ValueError('업데이트 파일 검증에 실패했습니다. 설치하지 않습니다.')
        helper_name = 'MusicMateUpdater.exe' if sys.platform == 'win32' else 'MusicMateUpdater'
        helper = Path(sys._MEIPASS) / 'updater' / helper_name
        shutil.copy2(helper, stage / helper_name)
        process = psutil.Process()
        processes = [process, *process.children(recursive=True)]
        plan = {
            'target': str(target), 'platform': platform_key(), 'envelope': update['envelope'],
            'processes': [{'pid': p.pid, 'created': p.create_time()} for p in processes],
        }
        (stage / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
        progress(100, '검증 완료. 앱 종료 후 업데이트를 설치합니다.')
        return stage
    except BaseException:
        shutil.rmtree(stage)
        raise


def launch_helper(stage: Path) -> None:
    helper_name = 'MusicMateUpdater.exe' if sys.platform == 'win32' else 'MusicMateUpdater'
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1')
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    process = subprocess.Popen([str(stage / helper_name), str(stage / 'plan.json')],
                               cwd=stage, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=flags, start_new_session=sys.platform != 'win32')
    # 준비 신호 전에는 앱을 종료하지 않아 실행 실패를 사용자에게 알릴 수 있게 한다.
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if (stage / 'ready').exists():
            return
        if process.poll() is not None:
            raise RuntimeError('업데이트 설치 프로그램을 실행하지 못했습니다.')
        time.sleep(0.1)
    process.terminate()
    raise RuntimeError('업데이트 설치 프로그램의 준비 시간이 초과되었습니다.')
