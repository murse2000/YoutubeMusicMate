## YoutubeMusicMate 0.1.3

- YouTube / YouTube Music의 개별 영상 음원을 MP3로 저장합니다.
- 제목·가수·앨범, 영상 표지, 일반 가사를 MP3 태그에 저장합니다.
- 기본 620×370의 소형 한국어 UI를 제공합니다.
- 시작 시 및 6시간마다 새 버전을 확인하며 수동 확인도 가능합니다.
- 새 버전은 **업데이트 설치 / 나중에**로 안내합니다. 동의 전에는 파일을 다운로드하지 않습니다.
- 다운로드 파일의 Ed25519 서명과 SHA-256을 검증합니다.
- 별도 설치 프로그램이 기존 앱·자식 프로세스 종료와 실행 잠금 해제를 확인한 뒤 교체합니다. 종료되지 않으면 설치하지 않습니다.
- 파일 교체에 실패하면 기존 앱을 복원합니다.

## 다운로드

- Apple Silicon Mac: `macos-arm64.zip`
- Intel Mac: `macos-x64.zip`
- Windows 10/11 x64: `windows-x64.zip`

ZIP을 풀어 사용하세요. Mac은 앱을 응용 프로그램 폴더에 옮기고, Windows는 `YoutubeMusicMate` 폴더 전체를 사용자 쓰기 권한이 있는 위치에 보관하세요. 폴더 이름을 바꾸면 자동 설치를 사용할 수 없습니다.

`.tar.gz`와 `latest.json`은 자동업데이트용입니다. `SHA256SUMS.txt`는 다운로드 검증용입니다.

이 릴리즈는 Apple Developer ID 공증 및 Windows 코드 서명이 적용되지 않았습니다. 업데이트 파일 자체는 별도의 Ed25519 키로 검증합니다. 기존 0.1.0 앱은 업데이트 기능이 없어 이 버전을 한 번 직접 설치해야 합니다.

## 검증

- Apple Silicon Mac, Intel Mac, Windows x64에서 각 24개 자동 테스트 및 빌드 성공
- 세 플랫폼에서 배포된 업데이트 실행 파일로 기존 프로세스 종료 대기 → 앱 교체 → 새 앱 재실행 확인
- 업로드된 파일의 Ed25519 서명, 크기, SHA-256 일치 확인
- [빌드 결과](https://github.com/murse2000/YoutubeMusicMate/actions/runs/35741171930) · [실제 업데이트 검증](https://github.com/murse2000/YoutubeMusicMate/actions/runs/35741911174)
