param([switch]$SkipFrontend, [string]$OutputDirectory = 'dist')
$ErrorActionPreference = 'Stop'
$menuPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $menuPython)) {
    $menuPython = Join-Path $PSScriptRoot 'Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $menuPython)) {
    throw 'Create .venv and install requirements-build.txt before building.'
}
Push-Location $PSScriptRoot
try {
    & (Join-Path $PSScriptRoot 'tools\build-hotkey-host.ps1')
    & (Join-Path $PSScriptRoot 'tools\build-menu-host.ps1')
    if (-not $SkipFrontend) {
        Push-Location (Join-Path $PSScriptRoot 'frontend')
        try {
            & npm ci
            if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
            & npm run build
            if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
        } finally { Pop-Location }
    }
    if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) {
        throw 'Missing frontend build.'
    }
    & $menuPython -m PyInstaller --noconfirm --distpath $OutputDirectory PhotoshopMenu.spec
    if ($LASTEXITCODE -ne 0) { throw 'EXE build failed.' }
    $menuExe = Join-Path $OutputDirectory 'PhotoshopMenu.exe'
    $menuDigest = (Get-FileHash -LiteralPath $menuExe -Algorithm SHA256).Hash.ToLowerInvariant()
    "$menuDigest  PhotoshopMenu.exe" | Set-Content -LiteralPath (Join-Path $OutputDirectory 'PhotoshopMenu.exe.sha256') -Encoding ascii
    Write-Host "Built: $menuExe"
} finally { Pop-Location }
