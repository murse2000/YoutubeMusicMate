"""CI 비밀키로 플랫폼별 릴리즈 정보를 서명한다. 비밀키는 출력하지 않는다."""
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization

folder = Path(sys.argv[1])
assets = [json.loads(path.read_text()) for path in folder.glob('*.json') if path.name != 'latest.json']
versions = {asset['version'] for asset in assets}
if len(versions) != 1 or {asset['platform'] for asset in assets} != {'macos-arm64', 'macos-x64', 'windows-x64'}:
    raise SystemExit('모든 플랫폼의 같은 버전 빌드가 필요합니다.')
version = versions.pop()
manifest = {'version': version, 'platforms': {asset['platform']: {
    'url': f"https://github.com/murse2000/YoutubeMusicMate/releases/download/v{version}/{asset['name']}",
    'sha256': asset['sha256'], 'size': asset['size'],
} for asset in assets}}
payload = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
key = serialization.load_pem_private_key(os.environ['UPDATE_SIGNING_KEY'].encode(), password=None)
(folder / 'latest.json').write_text(json.dumps({
    'payload': base64.b64encode(payload).decode(),
    'signature': base64.b64encode(key.sign(payload)).decode(),
}), encoding='utf-8')
checksums = []
for path in sorted(folder.iterdir()):
    if path.name.endswith(('.zip', '.tar.gz')) or path.name == 'latest.json':
        with path.open('rb') as stream:
            checksums.append(f"{hashlib.file_digest(stream, 'sha256').hexdigest()}  {path.name}")
(folder / 'SHA256SUMS.txt').write_text('\n'.join(checksums) + '\n')
