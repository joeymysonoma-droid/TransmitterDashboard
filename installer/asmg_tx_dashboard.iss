; ASMG TX Dashboard — Inno Setup 6 installer
; Wizard asks for HTTP port and writes it into %LOCALAPPDATA%\ASMG TX Dashboard\config\transmitters.yaml

#define MyAppName "ASMG TX Dashboard"
#define MyAppVersion "1.3.0"
#define MyAppPublisher "ASMG"
#define MyAppExeName "AsmgTxDashboard.exe"
#define MyAppDirName "ASMG TX Dashboard"

[Setup]
AppId={{8F3C2A91-6B4E-4D17-9C1A-7E2B5F0A4D83}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppDirName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=ASMG-TX-Dashboard-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"
Name: "autostart"; Description: "Start dashboard automatically when I log on"; GroupDescription: "Startup:"

[Files]
Source: "..\dist\AsmgTxDashboard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "StartDashboard.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "StopDashboard.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config\transmitters.example.yaml"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\StartDashboard.vbs"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Stop {#MyAppName}"; Filename: "{app}\StopDashboard.vbs"; WorkingDir: "{app}"
Name: "{group}\Open Config Folder"; Filename: "{localappdata}\{#MyAppDirName}\config"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\StartDashboard.vbs"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\StartDashboard.vbs"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: autostart

[Run]
Filename: "{app}\StartDashboard.vbs"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent shellexec

[Code]
var
  PortPage: TInputQueryWizardPage;

function IsValidPort(const S: String): Boolean;
var
  N, i: Integer;
  T: String;
begin
  Result := False;
  T := Trim(S);
  if T = '' then
    Exit;
  for i := 1 to Length(T) do
    if (T[i] < '0') or (T[i] > '9') then
      Exit;
  N := StrToIntDef(T, -1);
  Result := (N >= 1) and (N <= 65535);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (PortPage <> nil) and (CurPageID = PortPage.ID) then
  begin
    if not IsValidPort(PortPage.Values[0]) then
    begin
      MsgBox('Enter a TCP port between 1 and 65535 (recommended: 8090).', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure InitializeWizard;
begin
  PortPage := CreateInputQueryPage(
    wpSelectTasks,
    'Dashboard HTTP port',
    'Choose the local web port for {#MyAppName}.',
    'Browsers will open http://localhost:<port>/ after install.' + #13#10 +
    'Use 8090 unless another studio tool already needs that port.'
  );
  PortPage.Add('HTTP port:', False);
  PortPage.Values[0] := '8090';
end;

function GetSelectedPort: String;
begin
  Result := '8090';
  if PortPage <> nil then
    Result := Trim(PortPage.Values[0]);
  if Result = '' then
    Result := '8090';
end;

function EnsureConfigWithPort: Boolean;
var
  ConfigDir, ConfigPath, ExamplePath: String;
  Lines: TArrayOfString;
  i, Len: Integer;
  Found: Boolean;
  LineTrim: String;
begin
  Result := False;
  ConfigDir := ExpandConstant('{localappdata}\{#MyAppDirName}\config');
  ConfigPath := ConfigDir + '\transmitters.yaml';
  ExamplePath := ExpandConstant('{app}\transmitters.example.yaml');

  if not ForceDirectories(ConfigDir) then
    Exit;

  if not FileExists(ConfigPath) then
  begin
    if not FileExists(ExamplePath) then
      Exit;
    if not CopyFile(ExamplePath, ConfigPath, False) then
      Exit;
  end;

  if not LoadStringsFromFile(ConfigPath, Lines) then
    Exit;

  Found := False;
  Len := GetArrayLength(Lines);
  for i := 0 to Len - 1 do
  begin
    LineTrim := Trim(Lines[i]);
    if Pos('http_port:', LineTrim) = 1 then
    begin
      Lines[i] := 'http_port: ' + GetSelectedPort;
      Found := True;
      Break;
    end;
  end;

  if not Found then
  begin
    SetArrayLength(Lines, Len + 1);
    Lines[Len] := 'http_port: ' + GetSelectedPort;
  end;

  { Example YAML is ASCII-only; avoid non-ASCII so ANSI save stays valid. }
  Result := SaveStringsToFile(ConfigPath, Lines, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not EnsureConfigWithPort then
      MsgBox(
        'Installed, but could not write http_port into:' + #13#10 +
        ExpandConstant('{localappdata}\{#MyAppDirName}\config\transmitters.yaml') + #13#10 +
        'Edit that file manually if needed.',
        mbInformation,
        MB_OK
      );
  end;
end;
