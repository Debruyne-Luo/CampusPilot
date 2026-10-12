param(
    [Parameter(Mandatory = $true)][string]$ArchivePath,
    [string]$AmapEnvPath,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$archive = (Resolve-Path -LiteralPath $ArchivePath).Path
$archiveName = Split-Path $archive -Leaf
if ($archiveName -notmatch '^campuspilot-\d{8}T\d{6}Z\.zip$') {
    throw 'Select a CampusPilot release archive.'
}
$archiveHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
$domain = 'campuspilot.38-244-61-184.sslip.io'
$sshTarget = 'root@38.244.61.184'
$amapFile = $AmapEnvPath
if ([string]::IsNullOrWhiteSpace($amapFile)) {
    $sharedPrivateFile = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) '.campuspilot-private/amap.env'
    $profilePrivateFile = Join-Path $env:LOCALAPPDATA 'CampusPilot/amap.env'
    if (Test-Path -LiteralPath $sharedPrivateFile -PathType Leaf) {
        $amapFile = $sharedPrivateFile
    } else {
        $amapFile = $profilePrivateFile
    }
}
if (-not (Test-Path -LiteralPath $amapFile -PathType Leaf)) {
    throw 'Amap configuration was not found. Use -AmapEnvPath with the saved private file; do not send keys to chat.'
}
$amapText = [IO.File]::ReadAllText($amapFile)
$settings = @{}
foreach ($key in @('AMAP_JS_KEY', 'AMAP_SECURITY_JS_CODE')) {
    $keyMatch = [regex]::Match($amapText, "(?m)^\s*$key\s*=\s*[`"']?([0-9a-fA-F]{32})[`"']?\s*$")
    if (-not $keyMatch.Success) { throw "Missing or invalid $key in the local configuration." }
    $settings[$key] = $keyMatch.Groups[1].Value
}
Get-Command ssh, scp -ErrorAction Stop | Out-Null
if ($CheckOnly) {
    Write-Host 'CHECK OK: archive, SSH tools and local Amap settings are ready; no connection made.'
    Write-Host "HTTPS address: https://$domain"
    return
}

$securePassword = Read-Host 'Choose the website visitor password (12-72 ASCII characters)' -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $visitorPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    if ($visitorPassword -notmatch '^[\x21-\x7e]{12,72}$') {
        throw 'Use 12-72 printable ASCII characters, without spaces.'
    }
    $settings['visitor_password'] = $visitorPassword
    $payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($settings | ConvertTo-Json -Compress)))
    $visitorPassword = $null
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    $securePassword.Dispose()
}

Write-Host 'Upload the source archive. Enter the VPS root password when SSH asks.'
& scp -P 22 $archive "${sshTarget}:/root/$archiveName"
if ($LASTEXITCODE -ne 0) { throw 'Upload failed; installation was not started.' }

# Credentials travel only in encrypted SSH stdin, never in argv, the archive or output.
$remoteScript = @'
set -euo pipefail
umask 077
if [ "$(id -u)" -ne 0 ] || [ "$(uname -m)" != x86_64 ]; then
    echo 'This first installer requires root on the approved amd64 VPS.' >&2; exit 1
fi
if [ -e /opt/campuspilot/current ] || [ -e /etc/systemd/system/campuspilot.service ]; then
    echo 'CampusPilot is already installed. Stop here and use its existing release.' >&2; exit 1
fi
if ss -lnt | awk '{print $4}' | grep -Eq '(^|:)(80|443|8766)$'; then
    echo 'A required port is occupied; existing services were left running.' >&2; exit 1
fi
if [ "$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)" -lt 409600 ] ||
   [ "$(df --output=avail -k /opt | tail -n 1 | tr -d ' ')" -lt 2097152 ]; then
    echo 'Less than 400 MB available RAM or 2 GB disk; no installation started.' >&2; exit 1
fi
python3 - /root/__ARCHIVE__ __SHA__ <<'PY'
import hashlib, pathlib, socket, sys, zipfile
p = pathlib.Path(sys.argv[1])
if hashlib.sha256(p.read_bytes()).hexdigest() != sys.argv[2]:
    raise SystemExit('Uploaded archive checksum mismatch')
addresses = {r[4][0] for r in socket.getaddrinfo('__DOMAIN__', 443, type=socket.SOCK_STREAM)}
if '38.244.61.184' not in addresses:
    raise SystemExit('Free hostname does not resolve to the approved VPS')
with zipfile.ZipFile(p) as archive:
    content = archive.read('deploy/bootstrap-local.sh').replace(b'\r\n', b'\n')
target = pathlib.Path('/root/campuspilot-bootstrap-first.sh')
if target.exists() and target.read_bytes() != content:
    raise SystemExit('An unrelated bootstrap file exists; refusing to replace it')
if not target.exists():
    with target.open('xb') as stream:
        stream.write(content)
    target.chmod(0o600)
PY
if [ ! -x /root/.local/bin/uv ]; then
    curl --proto '=https' --tlsv1.2 -fLsS https://astral.sh/uv/0.12.19/install.sh -o /root/campuspilot-install-uv.sh
    UV_NO_MODIFY_PATH=1 sh /root/campuspilot-install-uv.sh
fi
bash /root/campuspilot-bootstrap-first.sh /root/__ARCHIVE__ __SHA__
printf '%s' '__PAYLOAD__' | bash /opt/campuspilot/current/deploy/enable-https.sh __DOMAIN__
'@
$remoteScript = $remoteScript.Replace('__ARCHIVE__', $archiveName).Replace('__SHA__', $archiveHash).Replace('__DOMAIN__', $domain).Replace('__PAYLOAD__', $payload)
Write-Host 'Install the private backend and protected HTTPS gateway. Enter the VPS password again.'
$remoteScript | & ssh -T -p 22 $sshTarget 'tr -d "\r" | bash -s'
$installExit = $LASTEXITCODE
$payload = $null
$remoteScript = $null
$settings.Clear()
if ($installExit -ne 0) {
    throw 'Installation did not finish. Send only the error message, without passwords or config files.'
}
Write-Host "Open https://$domain with username campuspilot and the visitor password you chose."
Write-Host 'Dify chat still needs its independent application and tool credentials.'
