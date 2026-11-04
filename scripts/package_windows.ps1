param([switch]$ReuseModels)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$Root = (Get-Location).Path
$Iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
if (!(Test-Path $Iscc)) { throw 'Install Inno Setup 6 on the build machine.' }
function Run($Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed ($LASTEXITCODE)" }
}
Run python @('-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir','--name','VUPIO',
    '--distpath','build/windows/dist','--workpath','build/windows/temp','--specpath','build/windows',
    '--paths',$Root,'--add-data','web:web','--collect-all','certifi','--collect-all','_sounddevice_data',
    '--hidden-import','qrcode.image.svg','scripts/windows_entry.py')
$App = Join-Path $Root 'build/windows/dist/VUPIO'
Run python @('scripts/bundle_windows_tools.py', (Join-Path $App 'Tools'))
if (!$ReuseModels) {
    Run python @('scripts/bundle_models.py', (Join-Path $Root 'build/release-models'))
}
Copy-Item -Recurse -Force 'build/release-models' (Join-Path $App 'Models')
Copy-Item LICENSE,THIRD_PARTY.md,README.md $App
$Notices = Join-Path $App 'ThirdPartyLicenses'
Run python @('scripts/copy_python_notices.py', $Notices, 'qrcode','numpy','certifi','pyinstaller','sounddevice','cffi','pycparser')

$Process = Start-Process (Join-Path $App 'VUPIO.exe') -ArgumentList '--smoke-test' -Wait -PassThru
if ($Process.ExitCode -ne 0) { throw "VUPIO smoke test failed ($($Process.ExitCode))" }
Run $Iscc @("/DAppDir=$App","/O$Root/build/releases", "$Root/installer/windows.iss")
