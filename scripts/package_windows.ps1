param([switch]$ReuseModels)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$Root = (Get-Location).Path
$Icon = Join-Path $Root 'web/vupio.ico'
$Iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
if (!(Test-Path $Iscc)) { throw 'Install Inno Setup 6 on the build machine.' }
function Run($Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed ($LASTEXITCODE)" }
}
Run python @('-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir','--name','VUPIO',
    '--icon',$Icon,'--distpath','build/windows/dist','--workpath','build/windows/temp','--specpath','build/windows',
    '--paths',$Root,'--add-data',"$Root/web;web",'--collect-all','certifi','--collect-all','_sounddevice_data',
    '--hidden-import','qrcode.image.svg','scripts/windows_entry.py')
$App = Join-Path $Root 'build/windows/dist/VUPIO'
Run python @('scripts/bundle_windows_tools.py', (Join-Path $App 'Tools'))
if (!$ReuseModels) {
    Run python @('scripts/bundle_models.py', (Join-Path $Root 'build/release-models'))
}
$Build = (& python -c 'from mimic import BUILD; print(BUILD)').Trim()
if ($LASTEXITCODE -ne 0 -or $Build -notmatch '^[1-9][0-9]{0,8}$') { throw 'Invalid build number' }
Set-Content (Join-Path $App 'installed-build.txt') -Value $Build -NoNewline -Encoding ascii
$ModelHash = (Get-FileHash 'build/release-models/components.json' -Algorithm SHA256).Hash.ToLowerInvariant()
Copy-Item LICENSE,THIRD_PARTY.md,README.md $App
$Notices = Join-Path $App 'ThirdPartyLicenses'
Run python @('scripts/copy_python_notices.py', $Notices, 'qrcode','numpy','certifi','pyinstaller','sounddevice','cffi','pycparser')

$Process = Start-Process (Join-Path $App 'VUPIO.exe') -ArgumentList '--smoke-test' -Wait -PassThru
if ($Process.ExitCode -ne 0) { throw "VUPIO smoke test failed ($($Process.ExitCode))" }
$SetupArgs = @("/DAppDir=$App","/DAppIcon=$Icon","/DBuildNumber=$Build","/O$Root/build/releases", "$Root/installer/windows.iss")
Run $Iscc (@("/DModelHash=$ModelHash") + $SetupArgs)
Copy-Item -Recurse 'build/release-models' (Join-Path $App 'Models')
Run $Iscc $SetupArgs
