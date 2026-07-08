# quickrun installer.
#
# From the web (no clone needed):
#   irm https://raw.githubusercontent.com/Unknownuserfrommars/quickrun/main/install.ps1 | iex
#
# From a local clone:
#   .\install.ps1                 # per-user (recommended, no admin needed)
#   .\install.ps1 -SystemWide     # C:\Program Files + machine PATH (needs admin)
param([switch]$SystemWide)
$ErrorActionPreference = "Stop"
$repo = "Unknownuserfrommars/quickrun"

if ($SystemWide) {
    $principal = [Security.Principal.WindowsPrincipal]::new(
        [Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "-SystemWide requires an elevated shell (Run as administrator)."
    }
    $installDir = Join-Path $env:ProgramFiles "quickrun"
    $pathScope = "Machine"
} else {
    $installDir = Join-Path $env:LOCALAPPDATA "Programs\quickrun"
    $pathScope = "User"
}

New-Item -ItemType Directory -Force $installDir | Out-Null
$target = Join-Path $installDir "quickrun.exe"

# Exe source, in order of preference: local build > local source > GitHub release.
$localDist = if ($PSScriptRoot) { Join-Path $PSScriptRoot "dist\quickrun.exe" }
$localSrc  = if ($PSScriptRoot) { Join-Path $PSScriptRoot "quickrun.py" }

if ($localDist -and (Test-Path $localDist)) {
    Copy-Item $localDist $target -Force
    Write-Host "Installed from local build: $target"
} elseif ($localSrc -and (Test-Path $localSrc)) {
    Write-Host "No dist\quickrun.exe - building with PyInstaller..."
    if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
        python -m pip install pyinstaller
    }
    Push-Location $PSScriptRoot
    try { pyinstaller --onefile --name quickrun --console --noconfirm quickrun.py }
    finally { Pop-Location }
    Copy-Item $localDist $target -Force
    Write-Host "Built and installed: $target"
} else {
    Write-Host "Downloading latest release from github.com/$repo ..."
    $release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest" `
        -Headers @{ "User-Agent" = "quickrun-installer" }
    $asset = $release.assets | Where-Object name -eq "quickrun.exe"
    if (-not $asset) { throw "Latest release ($($release.tag_name)) has no quickrun.exe asset." }
    Invoke-WebRequest $asset.browser_download_url -OutFile $target
    Write-Host "Installed $($release.tag_name): $target"
}

$currentPath = [Environment]::GetEnvironmentVariable("Path", $pathScope)
if (($currentPath -split ";") -notcontains $installDir) {
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$installDir", $pathScope)
    Write-Host "Added to $pathScope PATH. Open a NEW terminal to use 'quickrun'."
} else {
    Write-Host "Already on PATH."
}

# Make quickrun itself launchable from Win+R, using its own mechanism.
& $target bind $target quickrun --force | Out-Null
Write-Host "Done. Try: quickrun quickstart"
