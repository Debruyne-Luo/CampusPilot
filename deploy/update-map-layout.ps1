# Run with PowerShell 7. Uses the configured SSH identity; never saves a root password.
[CmdletBinding()]
param([switch]$CheckOnly, [string]$RollbackId, [switch]$IncludeMapCandidates, [string]$RestoreMapCandidatesId)
$ErrorActionPreference = 'Stop'
$sshCommand = Get-Command ssh -ErrorAction Stop
$assetDirectory = Join-Path (Split-Path -Parent $PSScriptRoot) 'backend/src/campuspilot/web_assets'
$names = @('app.js', 'style.css', 'map-shell.css', 'map-frame.css', 'map-frame.html', 'map-frame.js', 'index.html')
$records = @{}
if (@($RollbackId, $RestoreMapCandidatesId, $IncludeMapCandidates.IsPresent).Where({$_}).Count -gt 1) { throw 'Use separate update and rollback operations.' }
if ($RestoreMapCandidatesId -and $RestoreMapCandidatesId -cnotmatch '^\d{8}T\d{6}Z-[a-f0-9]{8}$') { throw 'Use only the data backup ID printed by a completed campus map update.' }
if ($RollbackId -and $RollbackId -cnotmatch '^\d{8}T\d{6}Z-[a-f0-9]{8}$') {
    throw 'Use only the backup ID printed by a completed map layout update.'
}
foreach ($name in $(if ($RollbackId -or $RestoreMapCandidatesId) { @() } else { $names })) {
    $path = Join-Path $assetDirectory $name
    $item = Get-Item -LiteralPath $path -ErrorAction Stop
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -gt 200000) {
        throw 'Web assets must be regular files under 200 KB.'
    }
    $records[$name] = @{
        data = [Convert]::ToBase64String([IO.File]::ReadAllBytes($path))
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$helperPath = Join-Path $PSScriptRoot 'update_map_layout.py'
$helper = [IO.File]::ReadAllText($helperPath)
$placesRecord = $null
if ($IncludeMapCandidates) {
    $placesPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'data/cdut/places.json'
    $placesItem = Get-Item -LiteralPath $placesPath -ErrorAction Stop
    if ($placesItem.PSIsContainer -or ($placesItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $placesItem.Length -gt 200000) { throw 'Place snapshot must be a regular file under 200 KB.' }
    $placesRecord = @{
        data = [Convert]::ToBase64String([IO.File]::ReadAllBytes($placesPath))
        sha256 = (Get-FileHash -LiteralPath $placesPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
if ($CheckOnly) {
    Write-Host 'CHECK OK: requested map layout update or rollback is ready.'
    Write-Host 'No credentials read, SSH connection, server writes or service restarts during this check.'
    return
}
$settings = if ($RollbackId) { @{ rollback_id = $RollbackId } } elseif ($RestoreMapCandidatesId) { @{ data_rollback_id = $RestoreMapCandidatesId } } else { @{ files = $records } }
if ($IncludeMapCandidates) { $settings.places = $placesRecord }
$payload = $settings | ConvertTo-Json -Depth 5 -Compress
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload))
$remoteProgram = $helper + "`nrun(json.loads(base64.b64decode('$encoded')))`n"
Write-Host 'Update the existing map layout using the configured SSH login.'
Write-Host 'The helper checks the installed asset baseline, backs it up, then verifies the served files.'
if ($IncludeMapCandidates) {
    Write-Host 'Includes unconfirmed building coordinates. One backend restart loads the snapshot; failed verification restores old files.'
}
if ($RestoreMapCandidatesId) { Write-Host 'Restores only the backed-up place snapshot and restarts the backend; refuses later edits.' }
($remoteProgram -replace "`r", '') | & $sshCommand.Source `
    -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -p 22 root@38.244.61.184 `
    '/opt/campuspilot/current/.venv/bin/python -'
if ($LASTEXITCODE -ne 0) {
    throw 'Map layout update did not finish. Share only the controlled result above.'
}
Write-Host 'Open https://campuspilot.38-244-61-184.sslip.io and refresh once.'
