# Run with PowerShell 7. Credentials travel through SSH stdin, never arguments.
[CmdletBinding()]
param([switch]$CheckOnly, [switch]$DiagnoseOnly)
$ErrorActionPreference = 'Stop'
$sshCommand = Get-Command ssh -ErrorAction Stop
$helperName = if ($DiagnoseOnly) { 'diagnose_dify.py' } else { 'configure_dify.py' }
$helperPath = Join-Path $PSScriptRoot $helperName
if (-not (Test-Path -LiteralPath $helperPath -PathType Leaf)) { throw 'Missing Dify configuration helper.' }
if ($CheckOnly) {
    Write-Host 'Dify connection script ready. No credentials read and no SSH connection made.'
    exit 0
}
Write-Host 'Use the API key from CampusPilot-提交版候选, not the original RAG app or the tool token.'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$savedKeyPath = Join-Path (Join-Path (Split-Path -Parent $projectDirectory) '.campuspilot-private') 'dify-app-key.txt'
if (Test-Path -LiteralPath $savedKeyPath -PathType Leaf) {
    if ((Get-Item -LiteralPath $savedKeyPath).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Saved application key must be a regular file.'
    }
    $savedKey = [IO.File]::ReadAllText($savedKeyPath).Trim()
    $secureKey = ConvertTo-SecureString $savedKey -AsPlainText -Force
    $savedKey = $null
    Write-Host 'Using the dedicated application key saved in the private local directory.'
} else {
    $secureKey = Read-Host 'Paste the Dify application API key (input hidden)' -AsSecureString
}
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer).Trim()
    if ($key -cnotmatch '^app-[A-Za-z0-9_-]{16,240}$') { throw 'Invalid Dify application API key format.' }
    $payload = @{ dify_api_key = $key } | ConvertTo-Json -Compress
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload))
    $helper = [IO.File]::ReadAllText($helperPath)
    # Base64 contains no shell metacharacters; the entire program uses encrypted stdin.
    $remoteProgram = $helper + "`nimport base64`nrun(json.loads(base64.b64decode('$encoded')))`n"
    Write-Host 'Enter the VPS root password at the SSH prompt. Existing services are preserved.'
    $remoteCommand = '/opt/campuspilot/current/.venv/bin/python -'
    if ($DiagnoseOnly) {
        Write-Host 'Read-only diagnosis: no server configuration writes or service restarts.'
    } else {
        Write-Host 'The script validates the published API, then connects and tests the backend.'
    }
    ($remoteProgram -replace "`r", '') | & $sshCommand.Source `
        -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -p 22 root@38.244.61.184 $remoteCommand
    if ($LASTEXITCODE -ne 0) { throw 'Dify connection did not finish. Keep the controlled error shown above for diagnosis.' }
    if ($DiagnoseOnly) {
        Write-Host 'Read-only diagnosis complete. Share only the two client result lines above.'
    } else {
        Write-Host 'Connected. Refresh the CampusPilot page and start a new conversation.'
    }
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    $secureKey.Dispose()
    $key = $null
    $payload = $null
    $encoded = $null
    $remoteProgram = $null
}
