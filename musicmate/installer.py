"""앱 종료를 확인한 뒤 동일 볼륨에서 앱을 교체하는 독립 설치 프로그램."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import psutil
from filelock import Timeout

from musicmate.updater import decode_manifest, instance_lock, select_asset, state_dir


def alive(identity: dict) -> bool:
    try:
        process = psutil.Process(identity['pid'])
        return process.create_time() == identity['created'] and process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def wait_for_exit(identities: list[dict], timeout: float = 60):
    deadline = time.monotonic() + timeout
    while any(alive(identity) for identity in identities):
        if time.monotonic() >= deadline:
            raise TimeoutError('앱이 완전히 종료되지 않아 설치를 중단했습니다. 기존 앱은 유지됩니다.')
        time.sleep(0.1)



def wait_for_target_exit(target: Path, timeout: float = 60):
    deadline = time.monotonic() + timeout
    while True:
        active = False
        for process in psutil.process_iter():
            try:
                executable = Path(process.exe())
                if executable.is_relative_to(target):
                    active = True
                    break
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
            except psutil.AccessDenied:
                try:
                    if process.name().lower() in ('youtubemusicmate', 'youtubemusicmate.exe'):
                        raise RuntimeError('다른 앱 프로세스의 종료를 확인할 권한이 없어 설치하지 않습니다.')
                except psutil.NoSuchProcess:
                    pass
        if not active:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError('설치 대상 앱이 아직 실행 중이어서 설치하지 않습니다.')
        time.sleep(0.2)


def extract_package(package: Path, destination: Path, root_name: str):
    with tarfile.open(package, 'r:gz') as archive:
        for member in archive.getmembers():
            if not member.name.startswith(root_name + '/') and member.name != root_name:
                raise ValueError('업데이트 압축 파일의 구조가 올바르지 않습니다.')
        # data 필터가 경로 탈출, 외부 심볼릭 링크, 장치 파일을 거부한다.
        archive.extractall(destination, filter='data')


def replace_app(prepared: Path, target: Path, backup: Path):
    if backup.exists():
        raise RuntimeError('이전 복구용 앱이 남아 있습니다. 업데이트를 중단합니다.')
    target.rename(backup)
    try:
        prepared.rename(target)
    except BaseException:
        backup.rename(target)
        raise


def start_app(target: Path):
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1')
    command = ['open', '-n', str(target)] if sys.platform == 'darwin' else [str(target / 'YoutubeMusicMate.exe')]
    subprocess.Popen(command, env=env, cwd=target.parent, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_plan(plan_path: Path):
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    stage = plan_path.parent
    target = Path(plan['target'])
    expected = 'YoutubeMusicMate.app' if plan['platform'].startswith('macos-') else 'YoutubeMusicMate'
    if target.name != expected or not target.is_dir() or target.is_symlink():
        raise ValueError('업데이트 설치 위치가 올바르지 않습니다.')
    manifest = decode_manifest(plan['envelope'].encode())
    asset = select_asset(manifest, plan['platform'])
    package = stage / 'package.tar.gz'
    with package.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if package.stat().st_size != asset['size'] or digest != asset['sha256']:
        raise ValueError('업데이트 파일이 변경되어 설치를 중단했습니다.')
    (stage / 'ready').touch()
    wait_for_exit(plan['processes'])
    lock = instance_lock()
    try:
        lock.acquire(timeout=15)
    except Timeout as error:
        raise RuntimeError('다른 앱 인스턴스가 실행 중이어서 설치하지 않았습니다.') from error
    try:
        wait_for_target_exit(target)
        # 종료 후 단일 실행 잠금을 확보한 동안만 파일을 교체한다.
        with tempfile.TemporaryDirectory(prefix='.musicmate-install-', dir=target.parent) as temporary:
            work = Path(temporary)
            extract_package(package, work, expected)
            prepared = work / expected
            executable = prepared / ('Contents/MacOS/YoutubeMusicMate' if sys.platform == 'darwin' else 'YoutubeMusicMate.exe')
            if not executable.is_file():
                raise ValueError('업데이트 앱 실행 파일이 없습니다.')
            if sys.platform == 'darwin':
                subprocess.run(['codesign', '--verify', '--deep', '--strict', str(prepared)], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            backup = target.with_name(target.name + '.previous')
            replace_app(prepared, target, backup)
        (state_dir() / 'update-result.json').write_text(json.dumps({
            'ok': True, 'message': f"{manifest['version']} 버전으로 업데이트했습니다.",
        }), encoding='utf-8')
    finally:
        lock.release()
    start_app(target)
    # 실행 요청까지 성공한 뒤 복구 사본과 다운로드 파일을 정리한다.
    shutil.rmtree(backup, ignore_errors=True)
    package.unlink(missing_ok=True)


def main():
    plan_path = Path(sys.argv[1])
    try:
        run_plan(plan_path)
    except Exception as error:
        (state_dir() / 'update-result.json').write_text(json.dumps({
            'ok': False, 'message': f'업데이트 실패: {error}',
        }), encoding='utf-8')
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        if not any(alive(identity) for identity in plan['processes']):
            start_app(Path(plan['target']))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
