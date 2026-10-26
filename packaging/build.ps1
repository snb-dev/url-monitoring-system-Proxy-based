# Builds dist\URLMonitor\URLMonitor.exe and the installer
# dist\URLMonitor-Setup-<version>.exe.
#
# Run from the repository root on Windows:  pwsh packaging\build.ps1
#
# To sign the executables, set SIGN_PFX_BASE64 (a base64-encoded .pfx code
# signing certificate) and SIGN_PFX_PASSWORD.

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    & $args[0] @($args | Select-Object -Skip 1)
    if ($LASTEXITCODE) { throw "Command failed ($LASTEXITCODE): $args" }
}

function Invoke-Sign([string]$File) {
    $pfx = Join-Path ([IO.Path]::GetTempPath()) "urlmonitor-signing.pfx"
    [IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:SIGN_PFX_BASE64))
    try {
        $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" |
            Sort-Object FullName -Descending | Select-Object -First 1
        Invoke-Checked $signtool.FullName sign /f $pfx /p $env:SIGN_PFX_PASSWORD `
            /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $File
    }
    finally {
        Remove-Item $pfx -ErrorAction SilentlyContinue
    }
}

$version = (python -c "import urlmonitor; print(urlmonitor.__version__)").Trim()
Write-Host "Building URL Monitor $version"

Invoke-Checked python -m pip install --upgrade pip
Invoke-Checked python -m pip install . pyinstaller
Invoke-Checked pyinstaller --noconfirm --distpath dist --workpath build packaging\urlmonitor.spec
if ($env:SIGN_PFX_BASE64) { Invoke-Sign "dist\URLMonitor\URLMonitor.exe" }

$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) {
    Invoke-Checked choco install innosetup --yes --no-progress
}
Invoke-Checked $iscc "/DAppVersion=$version" packaging\installer.iss
$installer = "dist\URLMonitor-Setup-$version.exe"
if ($env:SIGN_PFX_BASE64) { Invoke-Sign $installer }

Write-Host "Built $installer"
