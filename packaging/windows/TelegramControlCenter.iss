#define MyAppName "Telegram Control Center"
#define MyAppVersion GetEnv("SITE_CONTROL_KIT_RELEASE_VERSION")
#if MyAppVersion == ""
#define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "Site Control Kit Contributors"
#define MyAppExeName "TelegramControlCenter.exe"
#define BuildRoot "..\\build\\windows"

[Setup]
AppId={{8C93114A-4380-49C5-9F2B-9E7E4E8E9A20}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\\Programs\\TelegramControlCenter
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\\dist\\windows
OutputBaseFilename=TelegramControlCenterSetup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64

[Files]
Source: "{#BuildRoot}\\dist\\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"
Name: "{userdesktop}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Dirs]
Name: "{userappdata}\\SiteControlKit\\config"
Name: "{localappdata}\\SiteControlKit\\data"
Name: "{localappdata}\\SiteControlKit\\logs"
Name: "{localappdata}\\SiteControlKit\\cache"

[Run]
Filename: "{app}\\{#MyAppExeName}"; Parameters: "--release-self-test"; Flags: runhidden waituntilterminated skipifdoesntexist
