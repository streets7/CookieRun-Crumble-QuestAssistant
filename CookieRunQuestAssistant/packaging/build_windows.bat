@echo off
chcp 65001 >nul
setlocal
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_DIR=%%~fI"
for %%I in ("%PROJECT_DIR%\..") do set "WORKSPACE_DIR=%%~fI"
set "BUILD_DIR=%WORKSPACE_DIR%\보관자료\빌드작업\windows"
set "OUTPUT_DIR=%WORKSPACE_DIR%\배포\windows"
set "APP_NAME=CookieRun Crumble Quest Assistant"
set "PYINSTALLER_CONFIG_DIR=%BUILD_DIR%\pyinstaller-cache"

cd /d "%PROJECT_DIR%"
if not exist "%PROJECT_DIR%\private_config.json" (
  echo private_config.json is required
  exit /b 1
)
if not exist "%BUILD_DIR%\venv\Scripts\python.exe" py -3 -m venv "%BUILD_DIR%\venv"
if errorlevel 1 exit /b 1
"%BUILD_DIR%\venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%BUILD_DIR%\venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
"%BUILD_DIR%\venv\Scripts\python.exe" -m unittest discover -q
if errorlevel 1 exit /b 1
if exist "%BUILD_DIR%\work" rmdir /s /q "%BUILD_DIR%\work"
if exist "%BUILD_DIR%\spec" rmdir /s /q "%BUILD_DIR%\spec"
if exist "%OUTPUT_DIR%" rmdir /s /q "%OUTPUT_DIR%"
mkdir "%BUILD_DIR%\work" "%BUILD_DIR%\spec" "%OUTPUT_DIR%"

"%BUILD_DIR%\venv\Scripts\pyinstaller.exe" ^
  --noconfirm --clean --windowed --onedir ^
  --name "%APP_NAME%" ^
  --icon "%SCRIPT_DIR%app_icon.ico" ^
  --version-file "%SCRIPT_DIR%windows_version.txt" ^
  --paths "%WORKSPACE_DIR%" ^
  --add-data "%PROJECT_DIR%\assets;assets" ^
  --add-data "%PROJECT_DIR%\vision_ocr_windows.ps1;." ^
  --add-data "%PROJECT_DIR%\private_config.json;." ^
  --hidden-import desktop_app ^
  --hidden-import release_update ^
  --workpath "%BUILD_DIR%\work" ^
  --specpath "%BUILD_DIR%\spec" ^
  --distpath "%OUTPUT_DIR%" ^
  app_entry.py
if errorlevel 1 exit /b 1

set "CQA_DATA_DIR=%BUILD_DIR%\self-test"
powershell.exe -NoProfile -Command "$p = Start-Process -FilePath '%OUTPUT_DIR%\%APP_NAME%\%APP_NAME%.exe' -ArgumentList '--self-test' -Wait -PassThru; exit $p.ExitCode"
if errorlevel 1 exit /b 1
copy "%SCRIPT_DIR%install-windows.txt" "%OUTPUT_DIR%\%APP_NAME%\설치안내.txt"
if errorlevel 1 exit /b 1
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 ISCC.exe was not found.
  exit /b 1
)
"%ISCC%" /DSourceDir="%OUTPUT_DIR%\%APP_NAME%" /DOutputDir="%OUTPUT_DIR%" /DVersion="16.0" "%SCRIPT_DIR%windows_installer.iss"
if errorlevel 1 exit /b 1
powershell.exe -NoProfile -Command "Get-FileHash '%OUTPUT_DIR%\CookieRun-Crumble-QuestAssistant-Windows11-v16.0-Setup.exe' -Algorithm SHA256 | ForEach-Object { $_.Hash + '  ' + [IO.Path]::GetFileName($_.Path) } | Set-Content -Encoding ascii '%OUTPUT_DIR%\SHA256.txt'"
if errorlevel 1 exit /b 1
echo Built: %OUTPUT_DIR%
endlocal
