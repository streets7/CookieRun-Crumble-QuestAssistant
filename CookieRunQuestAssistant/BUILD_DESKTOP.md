# macOS / Windows 데스크톱 빌드

배포본에는 Python과 Pillow가 포함되므로 사용자는 Python을 설치하지 않아도 됩니다.
두 운영체제의 실행 파일은 같은 소스에서 만들지만, PyInstaller 특성상 각 운영체제에서 각각 빌드해야 합니다.

## macOS

1. Python 3.11 이상이 설치된 Apple Silicon Mac에서 `packaging/build_macos.command`를 실행합니다.
2. 결과는 `배포/macos`에 `.app`, `.zip`, `.dmg`로 생성됩니다.
3. 최초 실행 때 macOS 손쉬운 사용의 키보드 제어 권한을 허용해야 보스 이동 키를 사용할 수 있습니다.

## Windows 11

1. Python 3.11 이상이 설치된 Windows 빌드 PC에서 `packaging\build_windows.bat`를 실행합니다.
2. 결과는 `배포\windows`에 실행 폴더와 설치형 Setup EXE로 생성됩니다.
3. 사용자 PC에서는 BlueStacks 5 설정 > 고급 > Android 디버그 브리지(ADB)를 켜야 합니다.
4. Windows의 한국어 OCR 언어 기능이 설치되어 있어야 숫자 판독 정확도가 유지됩니다.

설정과 오류 스크린샷은 설치 폴더가 아니라 사용자별 데이터 폴더에 저장됩니다.

- macOS: `~/Library/Application Support/CookieRunCrumbleQuestAssistant`
- Windows: `%APPDATA%\CookieRunCrumbleQuestAssistant`

Mac은 DMG, Windows는 Setup EXE를 전달합니다. GitHub 정식 태그 발행 시 두 설치 파일을 같은 Release에 등록합니다.
