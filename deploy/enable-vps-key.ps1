#Requires -Version 7.0
# One-time key setup; the existing VPS password stays in the SSH prompt.
[CmdletBinding()]
param([switch]$CheckOnly, [switch]$PrepareOnly)

$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'Run this setup from Windows PowerShell 7.' }
$sshCommand = Get-Command ssh -ErrorAction Stop
$keygenCommand = Get-Command ssh-keygen -ErrorAction Stop
$projectDirectory = Split-Path -Parent $PSScriptRoot
$privateDirectory = Join-Path (Split-Path -Parent $projectDirectory) '.campuspilot-private'
$keyPath = Join-Path $privateDirectory 'campuspilot-vps-ed25519'
$publicPath = "$keyPath.pub"
$clientDirectory = Join-Path $env:USERPROFILE '.ssh'
$configPath = Join-Path $clientDirectory 'config'
$keyPathForSsh = $keyPath.Replace('\', '/')
$managedBlock = @"
# CampusPilot deployment key begin
Host campuspilot-vps 38.244.61.184
    HostName 38.244.61.184
    User root
    Port 22
    IdentityFile "$keyPathForSsh"
    IdentitiesOnly yes
    StrictHostKeyChecking yes
    ConnectTimeout 15
    ConnectionAttempts 1
# CampusPilot deployment key end
"@

if ($CheckOnly) {
    Write-Host 'CHECK OK: one-time SSH key setup is ready. No keys, files or server settings changed.'
    return
}
foreach ($path in @($privateDirectory, $clientDirectory, $keyPath, $publicPath, $configPath)) {
    if ((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Setup paths must not be links.'
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $clientDirectory 'known_hosts'))) {
    throw 'Use the existing trusted VPS host fingerprint before running this setup.'
}
$oldConfig = if (Test-Path -LiteralPath $configPath) { [IO.File]::ReadAllText($configPath) } else { '' }
if ($oldConfig.Contains('# CampusPilot deployment key begin') -and -not $oldConfig.Contains($managedBlock)) {
    throw 'Existing CampusPilot SSH configuration differs. It was not overwritten.'
}
if ($oldConfig -match '(?im)^\s*Host\s+[^\r\n]*\bcampuspilot-vps\b' -and -not $oldConfig.Contains($managedBlock)) {
    throw 'An existing campuspilot-vps alias was not overwritten.'
}

# Protect the destination before creating the private key, outside the repository.
[IO.Directory]::CreateDirectory($privateDirectory) | Out-Null
$directoryAcl = [Security.AccessControl.DirectorySecurity]::new()
$directoryAcl.SetAccessRuleProtection($true, $false)
$localIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().User
foreach ($identity in @($localIdentity, 'S-1-5-18', 'S-1-5-32-544')) {
    $sid = if ($identity -is [Security.Principal.SecurityIdentifier]) { $identity } else { [Security.Principal.SecurityIdentifier]::new($identity) }
    $directoryAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $sid, 'FullControl', 'ContainerInherit, ObjectInherit', 'None', 'Allow'
    ))
}
Set-Acl -LiteralPath $privateDirectory -AclObject $directoryAcl
if ((Test-Path -LiteralPath $keyPath) -ne (Test-Path -LiteralPath $publicPath)) {
    throw 'An incomplete key pair exists. It was not overwritten.'
}
if (-not (Test-Path -LiteralPath $keyPath)) {
    $keyProcessInfo = [Diagnostics.ProcessStartInfo]::new()
    $keyProcessInfo.FileName = $keygenCommand.Source
    $keyProcessInfo.UseShellExecute = $false
    $keyProcessInfo.CreateNoWindow = $true
    $keyProcessInfo.RedirectStandardOutput = $true
    $keyProcessInfo.RedirectStandardError = $true
    foreach ($argument in @('-q', '-t', 'ed25519', '-N', '', '-C', 'campuspilot-deploy', '-f', $keyPath)) {
        $keyProcessInfo.ArgumentList.Add($argument)
    }
    $keyProcess = [Diagnostics.Process]::Start($keyProcessInfo)
    $null = $keyProcess.StandardOutput.ReadToEnd()
    $null = $keyProcess.StandardError.ReadToEnd()
    $keyProcess.WaitForExit()
    if ($keyProcess.ExitCode -ne 0) { throw 'SSH key generation failed. No server settings changed.' }
    $keyProcess.Dispose()
}
$publicKey = [IO.File]::ReadAllText($publicPath).Trim()
if ($publicKey -cnotmatch '^ssh-ed25519 [A-Za-z0-9+/]+={0,3} campuspilot-deploy$') {
    throw 'Unexpected public key format. No server settings changed.'
}
$inspectProcessInfo = [Diagnostics.ProcessStartInfo]::new()
$inspectProcessInfo.FileName = $keygenCommand.Source
$inspectProcessInfo.UseShellExecute = $false
$inspectProcessInfo.CreateNoWindow = $true
$inspectProcessInfo.RedirectStandardOutput = $true
$inspectProcessInfo.RedirectStandardError = $true
foreach ($argument in @('-y', '-P', '', '-f', $keyPath)) { $inspectProcessInfo.ArgumentList.Add($argument) }
$inspectProcess = [Diagnostics.Process]::Start($inspectProcessInfo)
$derivedPublicKey = $inspectProcess.StandardOutput.ReadToEnd().Trim()
$null = $inspectProcess.StandardError.ReadToEnd()
$inspectProcess.WaitForExit()
$derivedKeyCore = (($derivedPublicKey -split ' ')[0..1] -join ' ')
$publicKeyCore = (($publicKey -split ' ')[0..1] -join ' ')
if ($inspectProcess.ExitCode -ne 0 -or $derivedKeyCore -cne $publicKeyCore) {
    throw 'The existing private and public key pair does not match. No server settings changed.'
}
$inspectProcess.Dispose()
if ($PrepareOnly) {
    Write-Host 'KEY PREPARED: protected local key pair validated. No SSH connection or client configuration change.'
    return
}
$commonSshOptions = @('-T', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15', '-o', 'ConnectionAttempts=1', '-p', '22')
$keySshOptions = @('-i', $keyPath, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'PreferredAuthentications=publickey')
# An already installed key does not ask for the password or change server files again.
& $sshCommand.Source @commonSshOptions @keySshOptions root@38.244.61.184 true 2>$null
if ($LASTEXITCODE -ne 0) {
    $encodedPublicKey = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($publicKey))
    $installCode = @'
import base64, fcntl, os, re, stat
from pathlib import Path
if os.geteuid() != 0:
    raise SystemExit('Expected root.')
public = base64.b64decode('__PUBLIC_KEY__').decode('ascii')
if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]+={0,3} campuspilot-deploy', public):
    raise SystemExit('Unexpected public key.')
directory = Path('/root/.ssh')
if directory.is_symlink():
    raise SystemExit('SSH directory must not be a link.')
directory.mkdir(mode=0o700, exist_ok=True)
info = directory.stat()
if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
    raise SystemExit('Unexpected existing SSH directory permissions.')
path = directory / 'authorized_keys'
fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
try:
    fcntl.flock(fd, fcntl.LOCK_EX)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_size > 200000 or stat.S_IMODE(info.st_mode) & 0o022:
        raise SystemExit('Unexpected existing authorized_keys file.')
    existing = os.read(fd, 200001)
    key_type, key_blob, _ = public.split()
    if not any((key_type + ' ' + key_blob) in line.decode('utf-8') for line in existing.splitlines() if not line.lstrip().startswith(b'#')):
        addition = (b'\n' if existing and not existing.endswith(b'\n') else b'') + ('restrict ' + public + '\n').encode('ascii')
        os.lseek(fd, 0, os.SEEK_END)
        with os.fdopen(os.dup(fd), 'ab') as stream:
            stream.write(addition)
            stream.flush()
            os.fsync(stream.fileno())
    print('Dedicated deployment public key installed; existing keys preserved.')
finally:
    os.close(fd)
'@
    $installCode = $installCode.Replace('__PUBLIC_KEY__', $encodedPublicKey)
    $serverAuthHelper = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'enable_vps_key.py'))
    $installCode += "`n" + $serverAuthHelper + "`nenable_root_key_authentication()`n"
    Write-Host 'Enter the existing VPS root password once at the SSH prompt. It is not saved.'
    ($installCode -replace "`r", '') | & $sshCommand.Source @commonSshOptions `
        -o BatchMode=no -o PubkeyAuthentication=no -o PreferredAuthentications=password `
        -o NumberOfPasswordPrompts=1 root@38.244.61.184 'python3 -'
    if ($LASTEXITCODE -ne 0) { throw 'Key installation did not finish. Existing login remains available.' }
    & $sshCommand.Source @commonSshOptions @keySshOptions root@38.244.61.184 true
    if ($LASTEXITCODE -ne 0) { throw 'New key login did not pass after the server authentication check. Existing password login remains; client configuration was not changed.' }
}
if (-not $oldConfig.Contains($managedBlock)) {
    $currentConfig = if (Test-Path -LiteralPath $configPath) { [IO.File]::ReadAllText($configPath) } else { '' }
    if ($currentConfig -cne $oldConfig) { throw 'SSH configuration changed during setup. It was not overwritten.' }
    if ($oldConfig) {
        $configBackup = Join-Path $privateDirectory ('ssh-config-before-key-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '.txt')
        [IO.File]::WriteAllText($configBackup, $oldConfig, [Text.UTF8Encoding]::new($false))
    }
    [IO.File]::WriteAllText($configPath, $managedBlock + "`n`n" + $oldConfig, [Text.UTF8Encoding]::new($false))
}
& $sshCommand.Source -o BatchMode=yes campuspilot-vps true
if ($LASTEXITCODE -ne 0) { throw 'Client alias validation failed. Use the verified key path explicitly.' }
Write-Host 'SSH KEY READY: CampusPilot deployments can now log in without a password prompt.'
Write-Host 'The dedicated private key stays outside the repository. VPS password login and existing services are unchanged.'
