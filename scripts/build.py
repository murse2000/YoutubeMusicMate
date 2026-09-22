"""현재 운영체제용 앱과 독립 업데이트 프로그램을 만든다."""
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
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
