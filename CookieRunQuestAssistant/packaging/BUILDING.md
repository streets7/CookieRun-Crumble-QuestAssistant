# v16.0 데스크톱 프로그램 정식 배포 빌드

- Mac: `zsh CookieRunQuestAssistant/packaging/build_macos.command`
- Windows: Inno Setup 6 설치 후 `CookieRunQuestAssistant\packaging\build_windows.bat`
- 결과: `배포/macos`, `배포/windows`. 빌드 임시 자료는 `보관자료/빌드작업`에 저장합니다.
- 두 빌드는 Python 검사와 번들 자체 검사를 실행하며 실패 시 배포 생성을 중단합니다.
- Mac DMG는 Applications 바로가기와 안내문을 포함합니다. Windows는 설치·제거 가능한 Setup EXE를 만듭니다.
- SHA256.txt로 배포 파일을 검증할 수 있습니다.
- GitHub 저장소에 올린 뒤 `v16.0` 같은 정식 태그를 푸시하면 `.github/workflows/release-desktop.yml`이 Mac DMG와 Windows Setup EXE를 검사·빌드한 후 하나의 정식 Release에 등록합니다.
- 사용자 settings.json, ui_layout.json, 오류 화면, 기존 배포본은 저장소에 올리지 마세요.
- Apple 공증 및 Windows 코드 서명은 포함되지 않습니다. Windows 11과 BlueStacks 5 실제 실행은 별도 검증이 필요합니다.

## 최초 GitHub 연결

1. 새 저장소의 이름과 공개/비공개 범위를 정합니다.
2. 현재 폴더를 최초 커밋하고 GitHub 원격 저장소를 연결합니다.
3. `main`을 푸시한 뒤 Actions의 수동 빌드로 두 운영체제를 확인합니다.
4. Windows 11에서 설치, 실행, BlueStacks 연결, 제거를 확인합니다.
5. 검증 후 `v16.0` 태그를 푸시해 정식 Release를 발행합니다.
