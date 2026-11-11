# 쿠키런: 크럼블 퀘스트 도우미

Mac과 Windows에서 BlueStacks의 반복 작업을 보조하는 데스크톱 프로그램입니다. v16.0부터 브라우저 대신 독립된 프로그램 창으로 실행됩니다.

## 설치

GitHub의 최신 정식 Release에서 운영체제에 맞는 파일을 선택합니다.

- Mac: `CookieRun-Crumble-QuestAssistant-macOS-v16.0.dmg`
- Windows 11: `CookieRun-Crumble-QuestAssistant-Windows11-v16.0-Setup.exe`

Windows 설치 파일은 GitHub의 Windows 빌드와 실제 BlueStacks 5 환경 검증이 완료된 뒤 제공합니다.

## 필요 환경

- 게임 화면 1080×1920
- Mac: Apple Silicon, BlueStacks Air
- Windows: Windows 11, BlueStacks 5, ADB 활성화

## 주의사항

프로그램 사용 여부는 사용자 본인이 결정합니다. 사용으로 발생할 수 있는 계정 정지, 이용 제한, 재화 또는 데이터 손실 등 문제에 대한 책임은 사용자에게 있습니다. 게임과 플랫폼의 이용약관 및 운영정책을 확인해 주세요.

## 개발과 배포

- Mac 빌드: `CookieRunQuestAssistant/packaging/build_macos.command`
- Windows 빌드: `CookieRunQuestAssistant/packaging/build_windows.bat`
- 정식 태그를 만들면 GitHub Actions가 두 운영체제를 검사한 뒤 하나의 Release로 발행합니다.
- 개인 설정과 관리자 비밀번호는 `private_config.json`에 저장하며 Git에 포함하지 않습니다.

자세한 내용은 [빌드 안내](CookieRunQuestAssistant/packaging/BUILDING.md)와 [변경 기록](CookieRunQuestAssistant/RELEASE_NOTES.md)을 확인해 주세요.
