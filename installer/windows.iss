#ifndef AppDir
#error AppDir must point to the frozen Windows application
#endif
#ifndef AppIcon
#error AppIcon must point to the Windows application icon
#endif
[Setup]
AppId=VUPIO
AppName=VUPIO
AppVersion=0.4.3
AppPublisher=VUPIO
DefaultDirName={autopf}\VUPIO
DefaultGroupName=VUPIO
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.22000
PrivilegesRequired=admin
OutputBaseFilename=VUPIO-Windows-x64-Setup
Compression=lzma2/fast
SolidCompression=yes
UninstallDisplayIcon={app}\VUPIO.exe
SetupIconFile={#AppIcon}
CloseApplications=force
RestartIfNeededByRun=yes

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\VUPIO"; Filename: "{app}\VUPIO.exe"

[Tasks]
Name: "discord"; Description: "Скачать VB-CABLE с сайта VB-Audio и открыть установщик драйвера для Discord"; Flags: unchecked

[Run]
Filename: "{app}\VUPIO.exe"; Description: "Открыть VUPIO"; Flags: nowait postinstall skipifsilent

[Code]
function PowerShellQuote(Value: String): String;
begin
  StringChangeEx(Value, '''', '''''', True);
  Result := '''' + Value + '''';
end;

function RunPowerShell(Command: String; var Code: Integer): Boolean;
begin
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -Command "' + Command + '"', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Installed: Cardinal;
  Code: Integer;
  Runtime, Command: String;
begin
  Result := '';
  if RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed) and (Installed = 1) then
    exit;
  try
    DownloadTemporaryFile('https://aka.ms/vc14/vc_redist.x64.exe', 'vupio-vc-redist.exe', '', nil);
    Runtime := ExpandConstant('{tmp}\vupio-vc-redist.exe');
    Command := '$s=Get-AuthenticodeSignature -LiteralPath ' + PowerShellQuote(Runtime) +
      '; if ($s.Status -ne ''Valid'' -or $s.SignerCertificate.Subject -notmatch ''Microsoft Corporation'') { exit 1 }';
    if not RunPowerShell(Command, Code) or (Code <> 0) then begin
      Result := 'Не удалось проверить подпись Microsoft Visual C++ Runtime.';
      exit;
    end;
    if not Exec(Runtime, '/install /quiet /norestart', '', SW_HIDE, ewWaitUntilTerminated, Code) then
      Result := 'Не удалось открыть установщик Microsoft Visual C++ Runtime.'
    else if Code = 3010 then NeedsRestart := True
    else if (Code <> 0) and (Code <> 1638) then
      Result := 'Установщик Microsoft Visual C++ Runtime вернул ошибку ' + IntToStr(Code) + '.';
  except
    Result := 'Не удалось загрузить Microsoft Visual C++ Runtime. Проверьте подключение к интернету.';
  end;
end;

procedure CurStepChanged(Step: TSetupStep);
var
  Code: Integer;
  Folder, Setup, Command: String;
begin
  if (Step <> ssPostInstall) or WizardSilent or not WizardIsTaskSelected('discord') then
    exit;
  try
    DownloadTemporaryFile('https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip',
      'vbcable.zip', 'b950e39f01af1d04ea623c8f6d8eb9b6ea5c477c637295fabf20631c85116bfb', nil);
    Folder := ExpandConstant('{tmp}\VBCable');
    Setup := Folder + '\VBCABLE_Setup_x64.exe';
    Command := 'Expand-Archive -ErrorAction Stop -LiteralPath ' + PowerShellQuote(ExpandConstant('{tmp}\vbcable.zip')) +
      ' -DestinationPath ' + PowerShellQuote(Folder) + '; $s=Get-AuthenticodeSignature -LiteralPath ' +
      PowerShellQuote(Setup) + '; if ($s.Status -ne ''Valid'' -or $s.SignerCertificate.Subject -notmatch ''BUREL VINCENT'') { exit 1 }';
    if not RunPowerShell(Command, Code) or (Code <> 0) then
      RaiseException('Не удалось проверить подпись установщика VB-Audio.');
    if not Exec(Setup, '', Folder, SW_SHOW, ewWaitUntilTerminated, Code) or (Code <> 0) then
      RaiseException('Установщик VB-Audio завершился с ошибкой.');
  except
    MsgBox(GetExceptionMessage + #13#10 + 'VUPIO установлен. Драйвер доступен отдельно на https://vb-audio.com/Cable/.', mbInformation, MB_OK);
  end;
end;
