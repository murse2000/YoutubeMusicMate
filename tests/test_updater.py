import base64
import io
import json
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path

import psutil
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from musicmate import installer, updater


def signed_manifest():
    key = Ed25519PrivateKey.generate()
    payload = json.dumps({'version': '1.2.3', 'platforms': {}}).encode()
    raw = json.dumps({'payload': base64.b64encode(payload).decode(),
                      'signature': base64.b64encode(key.sign(payload)).decode()}).encode()
    return raw, base64.b64encode(key.public_key().public_bytes_raw()).decode()


def test_signed_manifest_rejects_tampering():
    raw, key = signed_manifest()
    assert updater.decode_manifest(raw, key)['version'] == '1.2.3'
    envelope = json.loads(raw)
    envelope['payload'] = base64.b64encode(b'{"version":"9.9.9"}').decode()
    with pytest.raises(InvalidSignature):
        updater.decode_manifest(json.dumps(envelope).encode(), key)


def test_semantic_version_order():
    assert updater.version_tuple('0.1.10') > updater.version_tuple('0.1.9')
    with pytest.raises(ValueError):
        updater.version_tuple('../latest')


def test_wait_does_not_install_while_process_is_alive():
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    identity = {'pid': child.pid, 'created': psutil.Process(child.pid).create_time()}
    try:
        with pytest.raises(TimeoutError, match='완전히 종료되지'):
            installer.wait_for_exit([identity], timeout=0.1)
    finally:
        child.terminate()
        child.wait()
    installer.wait_for_exit([identity], timeout=1)


def test_pid_reuse_is_not_treated_as_original_process():
    assert not installer.alive({'pid': psutil.Process().pid, 'created': 0})


def test_replace_rolls_back_on_failed_rename(tmp_path, monkeypatch):
    target = tmp_path / 'app'
    prepared = tmp_path / 'new'
    backup = tmp_path / 'backup'
    target.mkdir(); prepared.mkdir()
    (target / 'version').write_text('old')
    rename = Path.rename
    def fail_new(self, destination):
        if self == prepared:
            raise PermissionError('locked')
        return rename(self, destination)
    monkeypatch.setattr(Path, 'rename', fail_new)
    with pytest.raises(PermissionError):
        installer.replace_app(prepared, target, backup)
    assert (target / 'version').read_text() == 'old'
    assert not backup.exists()


@pytest.mark.parametrize('name,link', [('App/../../outside', None), ('App/link', '../../outside')])
def test_archive_rejects_path_escape(tmp_path, name, link):
    archive = tmp_path / 'test.tar.gz'
    with tarfile.open(archive, 'w:gz') as stream:
        member = tarfile.TarInfo(name)
        if link:
            member.type = tarfile.SYMTYPE
            member.linkname = link
        stream.addfile(member)
    destination = tmp_path / 'extract'
    destination.mkdir()
    with pytest.raises((ValueError, tarfile.FilterError)):
        installer.extract_package(archive, destination, 'App')
    assert not (tmp_path / 'outside').exists()


def test_asset_rejects_foreign_download_host():
    manifest = {'version': '1.0.0', 'platforms': {'windows-x64': {
        'url': 'https://example.org/app.exe', 'size': 1, 'sha256': 'a' * 64}}}
    with pytest.raises(ValueError):
        updater.select_asset(manifest, 'windows-x64')


def test_corrupt_download_never_launches_installer(tmp_path, monkeypatch):
    asset = {'url': 'https://example.org/file', 'size': 3, 'sha256': 'a' * 64}
    monkeypatch.setattr(updater, 'install_root', lambda: tmp_path / 'app')
    monkeypatch.setattr(updater, 'state_dir', lambda: tmp_path)
    monkeypatch.setattr(updater, 'decode_manifest', lambda data: {})
    monkeypatch.setattr(updater, 'select_asset', lambda *args: asset)
    monkeypatch.setattr(updater, 'platform_key', lambda: 'windows-x64')
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_content(self, size): yield b'bad'
    monkeypatch.setattr(updater.requests, 'get', lambda *args, **kwargs: Response())
    with pytest.raises(ValueError, match='검증에 실패'):
        updater.prepare_update({'envelope': '{}'}, threading.Event(), lambda *args: None)
    assert not list(tmp_path.iterdir())


def test_other_instance_in_install_directory_blocks_install(tmp_path, monkeypatch):
    class Process:
        def exe(self): return str(tmp_path / 'YoutubeMusicMate.exe')
    monkeypatch.setattr(installer.psutil, 'process_iter', lambda: [Process()])
    with pytest.raises(TimeoutError, match='아직 실행 중'):
        installer.wait_for_target_exit(tmp_path, timeout=0)
