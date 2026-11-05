# End-to-end test of the TSF transport without Photoshop or administrator rights.
# Copies the test host as Photoshop.exe / PhotoshopMenu.exe, registers the COM
# class per user, and checks that InputService.dll attaches InputContext.dll to
# the fake Photoshop root window.
$ErrorActionPreference = 'Stop'
$menuRoot = Split-Path -Parent $PSScriptRoot
$service = Join-Path $menuRoot 'native\InputService.dll'
$context = Join-Path $menuRoot 'native\InputContext.dll'
$hostExe = Join-Path $PSScriptRoot 'test-input-service.exe'
foreach ($path in @($service, $context, $hostExe)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing $path; run the build first." }
}
$clsid = '{A4D1C7F2-5E3B-4C8D-9F01-6B2E8D4A7C15}'
$ownerKey = 'HKCU:\Software\PhotoshopMenu\InputService'
$classKey = "HKCU:\Software\Classes\CLSID\$clsid"
$folder = Join-Path $menuRoot '.runtime\input-service-test'
if (Test-Path -LiteralPath $folder) { Remove-Item -LiteralPath $folder -Recurse -Force }
New-Item -ItemType Directory -Path $folder | Out-Null

Copy-Item -LiteralPath $hostExe -Destination (Join-Path $folder 'Photoshop.exe')
Copy-Item -LiteralPath $hostExe -Destination (Join-Path $folder 'PhotoshopMenu.exe')
Copy-Item -LiteralPath $service -Destination (Join-Path $folder 'InputService.dll')
Copy-Item -LiteralPath $context -Destination (Join-Path $folder 'InputContext.dll')

$previousOwner = $null
try { $previousOwner = (Get-ItemProperty -Path $ownerKey -Name OwnerPid -ErrorAction SilentlyContinue).OwnerPid } catch { $previousOwner = $null }
$owner = $null
try {
    New-Item -Path $classKey -Force | Out-Null
    New-Item -Path "$classKey\InprocServer32" -Force | Out-Null
    Set-ItemProperty -Path $classKey -Name '(default)' -Value 'PhotoshopMenu Input Service (test)'
    Set-ItemProperty -Path "$classKey\InprocServer32" -Name '(default)' -Value (Join-Path $folder 'InputService.dll')
    Set-ItemProperty -Path "$classKey\InprocServer32" -Name 'ThreadingModel' -Value 'Apartment'

    $owner = Start-Process -FilePath (Join-Path $folder 'PhotoshopMenu.exe') -ArgumentList '--owner' -PassThru -WindowStyle Hidden
    Start-Sleep -Milliseconds 600
    New-Item -Path $ownerKey -Force | Out-Null
    Set-ItemProperty -Path $ownerKey -Name 'OwnerPid' -Value $owner.Id -Type DWord

    $result = & (Join-Path $folder 'Photoshop.exe') '--host' 2>&1
    $text = ($result | Out-String)
    Write-Host $text.Trim()
    if ($text -notmatch 'RESULT attached=1') { throw 'TSF transport did not attach' }
    Write-Host 'TSF transport test passed'
}
finally {
    if ($owner -and -not $owner.HasExited) { $owner.Kill() }
    if ($null -ne $previousOwner) {
        New-Item -Path $ownerKey -Force | Out-Null
        Set-ItemProperty -Path $ownerKey -Name 'OwnerPid' -Value ([int]$previousOwner) -Type DWord
    } else {
        Remove-Item -Path $ownerKey -Recurse -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -Path $classKey -Recurse -Force -ErrorAction SilentlyContinue
}
