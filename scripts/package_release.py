"""OS별 업데이트 압축 파일과 해시 정보를 만든다."""
import hashlib
import json
import platform
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from musicmate import __version__
from musicmate.updater import platform_key

root = Path(__file__).resolve().parent.parent
key = platform_key()
app = root / 'dist' / ('YoutubeMusicMate.app' if sys.platform == 'darwin' else 'YoutubeMusicMate')
output = root / 'dist' / 'release'
output.mkdir(exist_ok=True)
name = f'YoutubeMusicMate-{__version__}-{key}.tar.gz'
package = output / name
with tarfile.open(package, 'w:gz') as archive:
    archive.add(app, arcname=app.name)
with package.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
(output / f'{key}.json').write_text(json.dumps({
    'platform': key, 'version': __version__, 'name': name,
    'sha256': digest, 'size': package.stat().st_size,
}), encoding='utf-8')
# 사용자가 직접 설치할 때는 운영체제에서 쉽게 풀 수 있는 ZIP도 제공한다.
import shutil
import subprocess
zip_path = output / f'YoutubeMusicMate-{__version__}-{key}.zip'
if sys.platform == 'darwin':
    subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(app), str(zip_path)], check=True)
else:
    shutil.make_archive(str(zip_path.with_suffix('')), 'zip', app.parent, app.name)
