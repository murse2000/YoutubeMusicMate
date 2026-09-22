# YoutubeMusicMate

YouTube / YouTube Music의 개별 영상 음원을 MP3로 저장하고, 영상 표지와 일반 가사를 ID3 태그에 넣는 한국어 데스크톱 앱입니다.

기본 창은 620×370이며 최소 540×350까지 줄일 수 있습니다.

## 사용 방법

1. 영상 주소를 붙여 넣고 **정보 조회**를 누릅니다.
2. 곡명·가수·앨범을 확인합니다. 영상에 가수 정보가 없으면 직접 입력합니다.
3. 저장 폴더를 선택하고 **MP3로 저장**을 누릅니다.
4. 결과 메시지에서 표지·가사 포함 여부를 확인합니다.

표지는 영상 썸네일이며 정식 앨범 표지와 다를 수 있습니다. 가사는 LRCLIB의 곡명·가수·앨범·재생 시간 조회 결과를 사용합니다. 등록된 일반 가사가 없거나 서비스 연결이 실패해도 음원은 저장하며, 그 이유를 결과에 표시합니다. 시간 동기화 가사 및 LRC 파일은 생성하지 않습니다.

고음질 VBR MP3로 변환합니다. 원본보다 음질이 좋아지는 것은 아닙니다. 같은 이름의 기존 파일은 보존하고 새 파일에 번호를 붙입니다. 재생목록 일괄 저장 및 진행 중인 라이브 방송은 지원하지 않습니다.

## 개발 실행

Python 3.12, Node.js 22 이상이 필요합니다. macOS 13 이상 및 Windows 10/11을 대상으로 합니다. FFmpeg는 imageio-ffmpeg 패키지에 포함됩니다.

macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python main.py
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py
```

## 테스트와 빌드

가상환경의 Python으로 실행합니다.

```sh
python -m pytest -q
python scripts/build.py
```

각 OS에서 해당 OS용 앱을 빌드합니다. macOS 결과는 `dist/YoutubeMusicMate.app`, Windows 결과는 `dist/YoutubeMusicMate/YoutubeMusicMate.exe`입니다. Windows 배포 시 exe가 들어 있는 폴더 전체가 필요합니다. Python, FFmpeg, Node.js를 앱에 포함합니다.

`.github/workflows/build.yml`에서 Apple Silicon Mac, Intel Mac, Windows x64 테스트·빌드를 실행합니다. 버전 태그를 푸시하면 모든 플랫폼 빌드 성공 후 서명된 업데이트 정보와 초안 릴리즈를 생성합니다. 배포용 Developer ID 서명·공증 및 Windows 코드 서명은 별도입니다.

## 검증 기록

- macOS Apple Silicon에서 자동 테스트 24개 통과: 실제 MP3 변환, 한글 ID3v2.3 제목·가수·앨범·일반 가사·JPEG 표지 재읽기, 파일 중복 보존, 실패 시 임시 파일 정리, 잘못된 주소 차단, 파일명 호환성.
- Blender의 공개 Big Buck Bunny 영상으로 실제 다운로드·597초 MP3 변환·표지 삽입 확인. 검증 파일: `build/verification/Big Buck Bunny.mp3`.
- LRCLIB 실서비스에서 일반 가사 응답 확인. 실제 음악 한 곡의 다운로드와 자동 가사 매칭을 연결한 검증은 미수행.
- macOS 패키지 앱에서도 실제 영상 정보·표지 조회 및 MP3 저장 완료 화면 확인. 출력 MP3의 597초 길이·제목·표지·ID3v2.3 태그 재확인.
- Windows 실기기 실행 검증은 미수행.

## 구성 및 참고

- [yt-dlp](https://github.com/yt-dlp/yt-dlp): 영상 정보·음원 다운로드
- [LRCLIB API](https://lrclib.net/docs): 일반 가사 조회
- [Mutagen](https://mutagen.readthedocs.io/en/latest/user/id3.html): ID3v2.3 태그
- [Qt for Python](https://doc.qt.io/qtforpython-6/): 공용 데스크톱 UI
- [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg): FFmpeg 실행 파일

YouTube 측 변경·접근 제한에 따라 다운로드가 실패할 수 있습니다. 의존성 갱신은 버전을 변경한 후 테스트와 빌드를 거쳐 배포합니다. 포함된 구성 요소의 배포 라이선스와 고지 사항은 공개 배포 전에 확인해야 합니다.

## 자동업데이트

시작 시와 6시간마다 새 버전을 확인합니다. 하단의 **업데이트 확인**으로 직접 확인할 수도 있습니다. 새 버전 안내에서 **업데이트 설치**에 동의한 경우에만 다운로드하며 **나중에**는 설치하지 않습니다. 음악 작업 중에는 업데이트를 설치하지 않습니다.

1. 내장된 Ed25519 공개키로 업데이트 정보의 서명을 확인합니다.
2. 동의 후 해당 OS 패키지를 다운로드하고 크기·SHA-256을 검증합니다.
3. 별도 설치 프로그램을 앱 폴더 밖에 실행하고 준비 신호를 확인합니다.
4. 앱 종료 후 기존 PID와 생성 시간, 자식 프로세스, 설치 위치의 실행 중인 프로세스 및 단일 실행 잠금을 확인합니다.
5. 종료 확인에 실패하면 기존 앱을 유지합니다. 성공하면 같은 볼륨에서 앱을 교체하며, 교체 실패 시 이전 앱으로 복원합니다.
6. 앱을 다시 시작하고 결과를 표시합니다.

다운로드 중에는 취소할 수 있습니다. 검증이 끝나 설치 프로그램에 넘긴 이후에는 앱을 종료하고 설치합니다. macOS는 앱을 응용 프로그램 폴더로 옮겨 사용하세요. Windows는 사용자 쓰기 권한이 있는 위치에 폴더 전체를 풀어 사용하세요. 읽기 전용 위치·macOS 앱 임시 실행 위치에서는 자동 설치를 시작하지 않습니다.

서명 비밀키는 Git에 포함하지 않으며 GitHub Actions의 `UPDATE_SIGNING_KEY` 비밀값으로 관리합니다. 공개 배포한 앱의 업데이트 호환성을 유지하려면 이 키를 보존해야 합니다. 0.1.0에는 자동업데이트 기능이 없으므로 0.1.3을 한 번 직접 설치해야 합니다.

### Intel Mac 빌드 의존성

cryptography 49 이후에는 Intel Mac용 사전 빌드 휠이 제공되지 않습니다. PyInstaller 안에서 Python의 OpenSSL과 충돌하지 않도록 정적 링크로 빌드해야 합니다. Homebrew의 OpenSSL과 Rust가 설치된 상태에서 가상환경을 사용해 다음 명령을 먼저 실행하세요. CI에는 이 설정이 적용되어 있습니다.

```sh
OPENSSL_STATIC=1 python -m pip install --force-reinstall --no-cache-dir --no-binary cryptography cryptography==50.0.1
```

[cryptography 공식 설치 안내](https://cryptography.io/en/latest/installation/)를 따르며, 빌드 스크립트도 동적 OpenSSL 연결이 남아 있으면 패키징을 중단합니다.
