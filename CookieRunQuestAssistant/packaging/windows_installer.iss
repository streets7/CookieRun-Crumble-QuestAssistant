#ifndef SourceDir
  #error SourceDir must be supplied by build_windows.bat
#endif
#ifndef OutputDir
  #error OutputDir must be supplied by build_windows.bat
#endif
#ifndef Version
  #define Version "16.0"
#endif

[Setup]
AppId={{8DC49085-8E8F-4BA1-983A-D56FD6D95BC8}
AppName=CookieRun Crumble Quest Assistant
AppVersion={#Version}
AppPublisher=CookieRun Quest Assistant
DefaultDirName={localappdata}\Programs\CookieRun Crumble Quest Assistant
DefaultGroupName=CookieRun Crumble Quest Assistant
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=CookieRun-Crumble-QuestAssistant-Windows11-v16.0-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\CookieRun Crumble Quest Assistant.exe

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\CookieRun Crumble Quest Assistant"; Filename: "{app}\CookieRun Crumble Quest Assistant.exe"
Name: "{autodesktop}\CookieRun Crumble Quest Assistant"; Filename: "{app}\CookieRun Crumble Quest Assistant.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "바탕 화면 바로가기 만들기"; GroupDescription: "추가 바로가기:"; Flags: unchecked

[Run]
Filename: "{app}\CookieRun Crumble Quest Assistant.exe"; Description: "프로그램 실행"; Flags: nowait postinstall skipifsilent
