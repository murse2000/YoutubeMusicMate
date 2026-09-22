"""현재 운영체제용 앱과 독립 업데이트 프로그램을 만든다."""
import shutil
import platform
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if sys.platform == 'darwin' and platform.machine() == 'x86_64':
    import cryptography.hazmat.bindings._rust as crypto_rust
    linked = subprocess.check_output(['otool', '-L', crypto_rust.__file__], text=True)
    if 'libssl.' in linked or 'libcrypto.' in linked:
        raise SystemExit('Intel Mac은 OpenSSL을 정적으로 링크한 cryptography가 필요합니다. README의 빌드 안내를 확인하세요.')
node = shutil.which('node')
if not node:
    raise SystemExit('빌드에는 Node.js 22 이상이 필요합니다.')
subprocess.run([
    sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--console',
    '--name', 'MusicMateUpdater', str(root / 'updater_main.py'),
], cwd=root, check=True)
helper = root / 'dist' / ('MusicMateUpdater.exe' if sys.platform == 'win32' else 'MusicMateUpdater')
subprocess.run([
    sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
    '--name', 'YoutubeMusicMate', '--collect-all', 'imageio_ffmpeg',
    '--collect-all', 'yt_dlp_ejs', '--collect-submodules', 'yt_dlp',
    '--add-binary', f'{node}:runtime', '--add-binary', f'{helper}:updater',
    '--osx-bundle-identifier', 'com.dalbear.youtubemusicmate', str(root / 'main.py'),
], cwd=root, check=True)
