from __future__ import annotations

import io
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import imageio_ffmpeg
import requests
import yt_dlp
from mutagen.id3 import APIC, TALB, TIT2, TPE1, USLT
from mutagen.mp3 import MP3
from PIL import Image


class Cancelled(Exception):
    pass


@dataclass
class Track:
    url: str
    title: str
    artist: str
    album: str
    duration: float
    cover: bytes = b""
    notice: str = ""


def validate_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in {
        "youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com", "youtu.be"
    } or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
        raise ValueError("YouTube 또는 YouTube Music 영상 주소를 입력하세요.")
    if parsed.path not in ("/watch",) and not parsed.path.startswith(("/shorts/", "/live/")) and not (
        parsed.hostname == "youtu.be" and parsed.path.strip("/")
    ):
        raise ValueError("재생목록이나 채널 대신 개별 영상 주소를 입력하세요.")
    return url


def node_path() -> str:
    name = "node.exe" if sys.platform == "win32" else "node"
    bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent)) / "runtime" / name
    result = str(bundled) if bundled.is_file() else shutil.which(name)
    if not result:
        raise RuntimeError("YouTube 분석에 필요한 Node.js가 없습니다. Node.js 22 이상을 설치하세요.")
    return result


def options() -> dict:
    return {
        "quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True,
        "socket_timeout": 20, "retries": 2, "fragment_retries": 2,
        "js_runtimes": {"node": {"path": node_path()}},
    }


def check_cancel(cancel: threading.Event):
    if cancel.is_set():
        raise Cancelled("작업을 취소했습니다.")


def inspect_track(url: str, cancel: threading.Event) -> Track:
    url = validate_url(url)
    check_cancel(cancel)
    with yt_dlp.YoutubeDL(options()) as downloader:
        info = downloader.extract_info(url, download=False)
    check_cancel(cancel)
    if not info or info.get("_type") in ("playlist", "multi_video"):
        raise ValueError("개별 음악 영상 주소를 입력하세요.")
    if info.get("is_live"):
        raise ValueError("진행 중인 라이브 방송은 저장할 수 없습니다.")
    track = Track(url, info.get("track") or info.get("title") or "",
                  info.get("artist") or "", info.get("album") or "",
                  float(info.get("duration") or 0))
    if not track.artist:
        track.notice = "가수 정보가 없습니다. 가사 검색을 위해 직접 입력하세요."
    if info.get("thumbnail"):
        try:
            response = requests.get(info["thumbnail"], timeout=20)
            response.raise_for_status()
            with Image.open(io.BytesIO(response.content)) as source:
                source.thumbnail((1200, 1200))
                output = io.BytesIO()
                source.convert("RGB").save(output, format="JPEG", quality=90)
                track.cover = output.getvalue()
        except (requests.RequestException, OSError, Image.DecompressionBombError):
            track.notice += " 표지를 가져오지 못했습니다."
    else:
        track.notice += " 영상에 표지가 없습니다."
    check_cancel(cancel)
    return track


def lookup_lyrics(track: Track) -> tuple[str, str]:
    if not track.artist.strip():
        return "", "가수 정보가 없어 가사를 조회하지 못했습니다."
    try:
        response = requests.get("https://lrclib.net/api/get", params={
            "track_name": track.title, "artist_name": track.artist,
            "album_name": track.album, "duration": track.duration,
        }, headers={"User-Agent": "YoutubeMusicMate/0.1.0"}, timeout=20)
        if response.status_code == 404:
            return "", "일치하는 가사가 없습니다."
        response.raise_for_status()
        data = response.json()
        if data.get("instrumental"):
            return "", "연주곡으로 등록되어 있습니다."
        lyrics = data.get("plainLyrics") or ""
        return lyrics, "" if lyrics else "등록된 일반 가사가 없습니다."
    except (requests.RequestException, ValueError):
        return "", "가사 서비스에 연결하지 못했습니다."


def write_tags(path: Path, track: Track, lyrics: str):
    audio = MP3(path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    for key in ("TIT2", "TPE1", "TALB", "APIC", "USLT"):
        tags.delall(key)
    tags.add(TIT2(encoding=1, text=track.title))
    tags.add(TPE1(encoding=1, text=track.artist))
    tags.add(TALB(encoding=1, text=track.album))
    if track.cover:
        tags.add(APIC(encoding=1, mime="image/jpeg", type=3, desc="Cover", data=track.cover))
    if lyrics:
        tags.add(USLT(encoding=1, lang="und", desc="", text=lyrics))
    audio.save(v2_version=3)


def filename(track: Track) -> str:
    name = " - ".join(value for value in (track.artist.strip(), track.title.strip()) if value)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:120].rstrip(" .") or "음악"
    while len(name.encode("utf-8")) > 180:
        name = name[:-1]
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        name = "_" + name
    return name + ".mp3"


def publish(source: Path, folder: Path, name: str) -> Path:
    # 배타적 생성으로 기존 파일을 덮어쓰지 않는다.
    stem = Path(name).stem
    for index in range(10000):
        target = folder / (name if index == 0 else f"{stem} ({index}).mp3")
        try:
            output = target.open("xb")
        except FileExistsError:
            continue
        try:
            with output, source.open("rb") as stream:
                shutil.copyfileobj(stream, output)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target
    raise RuntimeError("같은 이름의 파일이 너무 많습니다.")


def convert(source: Path, target: Path, cancel: threading.Event):
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "error",
               "-i", str(source), "-vn", "-map_metadata", "-1", "-codec:a", "libmp3lame",
               "-q:a", "0", str(target)]
    with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                          creationflags=flags) as process:
        while True:
            try:
                _, error = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if cancel.is_set():
                    process.kill()
                    process.communicate()
                    raise Cancelled("작업을 취소했습니다.")
        if process.returncode:
            raise RuntimeError("MP3 변환 실패: " + error.decode("utf-8", errors="replace")[-1500:])


def save_track(track: Track, folder: Path, cancel: threading.Event, progress) -> tuple[Path, str]:
    check_cancel(cancel)
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".musicmate-", dir=folder) as temporary:
        work = Path(temporary)

        def hook(event):
            check_cancel(cancel)
            if event["status"] == "downloading":
                total = event.get("total_bytes") or event.get("total_bytes_estimate")
                percent = int(event.get("downloaded_bytes", 0) / total * 75) if total else 0
                progress(min(percent, 75), "음원을 다운로드하고 있습니다…")

        config = options() | {"format": "bestaudio/best", "outtmpl": str(work / "audio.%(ext)s"),
                              "progress_hooks": [hook]}
        progress(0, "음원 다운로드 준비 중…")
        with yt_dlp.YoutubeDL(config) as downloader:
            info = downloader.extract_info(track.url, download=True)
            source = Path(downloader.prepare_filename(info))
        check_cancel(cancel)
        progress(78, "MP3로 변환하고 있습니다…")
        mp3 = work / "tagged.mp3"
        convert(source, mp3, cancel)
        check_cancel(cancel)
        progress(90, "일반 가사를 조회하고 있습니다…")
        lyrics, warning = lookup_lyrics(track)
        check_cancel(cancel)
        progress(95, "표지와 가사를 MP3에 저장하고 있습니다…")
        write_tags(mp3, track, lyrics)
        check_cancel(cancel)
        result = publish(mp3, folder, filename(track))
    progress(100, "저장 완료")
    cover_state = "표지 포함" if track.cover else "표지 없음"
    lyric_state = "일반 가사 포함" if lyrics else warning
    return result, f"{cover_state} · {lyric_state}"
