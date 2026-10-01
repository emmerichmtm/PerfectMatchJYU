param(
    [string]$Python = "$PSScriptRoot\.venv\Scripts\python.exe",
    [string]$Destination = "$PSScriptRoot\dist",
    [string]$BuildDirectory = "$PSScriptRoot\build"
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath $Python)) { throw 'Run setup_windows.bat first.' }
    & $Python -m PyInstaller --noconfirm --workpath $BuildDirectory --distpath $Destination PerfectMatch.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    $package = Join-Path $Destination 'PerfectMatch'
    Copy-Item -LiteralPath 'START HERE.txt', 'manual.pdf' -Destination $package
    New-Item -ItemType Directory -Force -Path (Join-Path $package 'templates') | Out-Null
    Copy-Item -LiteralPath 'examples\config.csv', 'examples\problem.csv' -Destination (Join-Path $package 'templates')
    & $Python package_notices.py $package
    if ($LASTEXITCODE -ne 0) { throw 'Dependency notice collection failed.' }
    # Python zipfile also retains files that PowerShell Compress-Archive may skip.
    & $Python -m zipfile -c (Join-Path $Destination 'PerfectMatchJYU-Windows.zip') $package
    if ($LASTEXITCODE -ne 0) { throw 'ZIP creation failed.' }
    Write-Host "Ready: $(Join-Path $Destination 'PerfectMatchJYU-Windows.zip')"
} finally {
    Pop-Location
}
