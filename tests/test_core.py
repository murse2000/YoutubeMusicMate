import io
import threading
import wave
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from mutagen.id3 import ID3
from PIL import Image

from musicmate.core import (Cancelled, Track, convert, filename, lookup_lyrics,
                            publish, save_track, validate_url, write_tags)


@pytest.mark.parametrize('url', ['https://example.com/watch?v=a', 'file:///etc/passwd',
                                  'https://youtube.com.evil.test/watch?v=a',
                                  'https://youtube.com/playlist?list=a'])
def test_reject_non_video_urls(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_real_mp3_tags_roundtrip(tmp_path):
    source = tmp_path / 'sample.wav'
    with wave.open(str(source), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(44100)
        audio.writeframes(b'\x00\x00' * 44100)
    target = tmp_path / 'sample.mp3'
    convert(source, target, threading.Event())
    cover = io.BytesIO()
    Image.new('RGB', (32, 32), '#6958d5').save(cover, 'JPEG')
    track = Track('https://youtu.be/test', '한글 노래', '가수', '앨범', 1, cover.getvalue())
    write_tags(target, track, '첫 번째 가사\n두 번째 가사')
    tags = ID3(target)
    assert str(tags['TIT2']) == track.title
    assert str(tags['TPE1']) == track.artist
    assert str(tags['TALB']) == track.album
    assert tags.getall('USLT')[0].text == '첫 번째 가사\n두 번째 가사'
    assert tags.getall('APIC')[0].data == track.cover
    assert tags.version == (2, 3, 0)


def test_publish_never_overwrites(tmp_path):
    source = tmp_path / 'source'
    source.write_bytes(b'new')
    original = tmp_path / 'song.mp3'
    original.write_bytes(b'old')
    result = publish(source, tmp_path, 'song.mp3')
    assert original.read_bytes() == b'old'
    assert result.name == 'song (1).mp3'
    assert result.read_bytes() == b'new'


def test_lyrics_not_found_and_unavailable(monkeypatch):
    track = Track('', '제목', '가수', '', 180)
    monkeypatch.setattr('musicmate.core.requests.get', lambda *a, **kw: Mock(status_code=404))
    assert lookup_lyrics(track) == ('', '일치하는 가사가 없습니다.')
    def failure(*args, **kwargs):
        raise requests.Timeout()
    monkeypatch.setattr('musicmate.core.requests.get', failure)
    assert lookup_lyrics(track) == ('', '가사 서비스에 연결하지 못했습니다.')


def test_cancel_does_not_create_output(tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        save_track(Track('', '노래', '', '', 1), tmp_path, cancel, lambda *a: None)
    assert not list(tmp_path.iterdir())


def test_failed_download_cleans_temporary_files(tmp_path, monkeypatch):
    downloader = Mock()
    downloader.__enter__ = Mock(return_value=downloader)
    downloader.__exit__ = Mock(return_value=False)
    downloader.extract_info.side_effect = RuntimeError('network unavailable')
    monkeypatch.setattr('musicmate.core.options', lambda: {})
    monkeypatch.setattr('musicmate.core.yt_dlp.YoutubeDL', lambda config: downloader)
    with pytest.raises(RuntimeError, match='network unavailable'):
        save_track(Track('', '노래', '', '', 1), tmp_path, threading.Event(), lambda *a: None)
    assert not list(tmp_path.iterdir())


def test_windows_safe_filename():
    assert filename(Track('', 'CON', '', '', 1)) == '_CON.mp3'
    assert filename(Track('', 'a/b:c?', '가수', '', 1)) == '가수 - a_b_c_.mp3'


def test_korean_filename_fits_filesystem_limit():
    name = filename(Track('', '가' * 200, '나' * 100, '', 1))
    assert len(name.encode('utf-8')) < 255
