# quickrun installer: build (if needed), copy to a permanent location, add to PATH.
$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$exe = Join-Path $root "dist\quickrun.exe"

if (-not (Test-Path $exe)) {
    Write-Host "dist\quickrun.exe not found - building with PyInstaller..."
    if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
        python -m pip install pyinstaller
    }
    Push-Location $root
    try { pyinstaller --onefile --name quickrun --console --noconfirm quickrun.py }
    finally { Pop-Location }
    if (-not (Test-Path $exe)) { throw "Build failed - no dist\quickrun.exe" }
}

$installDir = Join-Path $env:LOCALAPPDATA "Programs\quickrun"
New-Item -ItemType Directory -Force $installDir | Out-Null
Copy-Item $exe $installDir -Force
Write-Host "Installed to $installDir\quickrun.exe"

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ";") -notcontains $installDir) {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$installDir", "User")
    Write-Host "Added to user PATH. Open a NEW terminal to use 'quickrun'."
} else {
    Write-Host "Already on PATH."
}

# Make quickrun itself launchable from Win+R, using its own mechanism.
& (Join-Path $installDir "quickrun.exe") bind (Join-Path $installDir "quickrun.exe") quickrun --force | Out-Null
Write-Host "Done. Try: quickrun quickstart"
