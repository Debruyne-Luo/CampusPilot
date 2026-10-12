# Requires PowerShell 7. Reads the existing VPS tool token; never changes it.
[CmdletBinding()]
param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$sshCommand = Get-Command ssh -ErrorAction Stop
$projectDirectory = Split-Path -Parent $PSScriptRoot
$privateDirectory = Join-Path (Split-Path -Parent $projectDirectory) '.campuspilot-private'
$tokenPath = Join-Path $privateDirectory 'tool-token.txt'

if ($CheckOnly) {
    Write-Host 'Read-only export script ready. SSH password is entered locally; no token is printed.'
    exit 0
}

if (Test-Path -LiteralPath $tokenPath) {
    $existingToken = [IO.File]::ReadAllText($tokenPath).Trim()
    if ($existingToken -cmatch '^[A-Za-z0-9_-]{32,128}$') {
        Write-Host 'Tool token already saved in the private local directory. No SSH connection made.'
        exit 0
    }
    throw 'Existing local token file is invalid. It was not overwritten.'
}

# Lock the destination before any secret is received. Keep it outside the repository.
[IO.Directory]::CreateDirectory($privateDirectory) | Out-Null
if ((Get-Item -LiteralPath $privateDirectory).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Private directory must not be a link.'
}
$directoryAcl = [Security.AccessControl.DirectorySecurity]::new()
$directoryAcl.SetAccessRuleProtection($true, $false)
$localIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().User
foreach ($identity in @($localIdentity, 'S-1-5-18', 'S-1-5-32-544')) {
    $sid = if ($identity -is [Security.Principal.SecurityIdentifier]) {
        $identity
    } else {
        [Security.Principal.SecurityIdentifier]::new($identity)
    }
    $rule = [Security.AccessControl.FileSystemAccessRule]::new(
        $sid, 'FullControl', 'ContainerInherit, ObjectInherit', 'None', 'Allow'
    )
    $directoryAcl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $privateDirectory -AclObject $directoryAcl

$readOnlyCode = @'
import os
from pathlib import Path
import re
import stat
import sys

if os.geteuid() != 0:
    sys.exit("Expected root for the private environment file.")
path = Path("/etc/campuspilot/campuspilot.env")
if path.is_symlink() or not path.is_file():
    sys.exit("Expected an existing private regular environment file.")
info = path.stat()
if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
    sys.exit("Unexpected environment file ownership or permissions.")
values = [line.split("=", 1)[1].strip() for line in path.read_text().splitlines()
          if line.startswith("CAMPUSPILOT_API_TOKEN=")]
if len(values) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", values[0]):
    sys.exit("Expected one existing tool token.")
print(values[0])
'@

Write-Host 'Enter the VPS root SSH password at its prompt. This only reads the existing tool credential.'
$remoteTokenLines = ($readOnlyCode -replace "`r", '') | & $sshCommand.Source `
    -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -p 22 root@38.244.61.184 'python3 -'
if ($LASTEXITCODE -ne 0) {
    throw 'SSH read failed. No local token was saved.'
}
$remoteToken = ($remoteTokenLines -join "`n").Trim()
if ($remoteToken -cnotmatch '^[A-Za-z0-9_-]{32,128}$') {
    throw 'Unexpected SSH output. No local token was saved.'
}
[IO.File]::WriteAllText($tokenPath, $remoteToken, [Text.UTF8Encoding]::new($false))
$remoteToken = $null
$remoteTokenLines = $null
Write-Host 'Tool token saved in the private local directory. Do not paste or screenshot its contents.'
