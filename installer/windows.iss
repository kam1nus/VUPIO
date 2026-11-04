#ifndef AppDir
#error AppDir must point to the frozen Windows application
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
CloseApplications=force
RestartIfNeededByRun=yes

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\VUPIO"; Filename: "{app}\VUPIO.exe"

[Run]
Filename: "https://vb-audio.com/Cable/"; Description: "Открыть официальную страницу VB-CABLE для Discord"; Flags: shellexec postinstall skipifsilent unchecked
Filename: "{app}\VUPIO.exe"; Description: "Открыть VUPIO"; Flags: nowait postinstall skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Installed: Cardinal;
  Code: Integer;
  Runtime, Literal, Params: String;
begin
  Result := '';
  if RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed) and (Installed = 1) then
    exit;
  try
    DownloadTemporaryFile('https://aka.ms/vc14/vc_redist.x64.exe', 'vupio-vc-redist.exe', '', nil);
    Runtime := ExpandConstant('{tmp}\vupio-vc-redist.exe');
    Literal := Runtime;
    StringChangeEx(Literal, '''', '''''', True);
    Params := '-NoProfile -NonInteractive -Command "$s=Get-AuthenticodeSignature -LiteralPath ''' +
      Literal + '''; if ($s.Status -ne ''Valid'' -or $s.SignerCertificate.Subject -notmatch ''Microsoft Corporation'') { exit 1 }"';
    if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      Params, '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then begin
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
