#Requires -Version 7.0
# Local hidden input only. This script never contacts Dify or the model gateway.
[CmdletBinding()]
param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$privateDirectory = Join-Path (Split-Path -Parent $projectDirectory) '.campuspilot-private'
$keyPath = Join-Path $privateDirectory 'model-api-key.txt'

if ($CheckOnly) {
    Write-Host 'Model key input script ready. No key read, file changed or network request made.'
    exit 0
}
if (-not $IsWindows) { throw 'This local credential entry script requires Windows.' }
if (Test-Path -LiteralPath $privateDirectory) {
    $directory = Get-Item -LiteralPath $privateDirectory
    if (-not $directory.PSIsContainer -or ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Private directory must be a regular directory.'
    }
}
if (Test-Path -LiteralPath $keyPath) {
    throw 'A model key file already exists. It was not read or overwritten.'
}

# Lock the directory before receiving credentials. Never save them in the repository.
[IO.Directory]::CreateDirectory($privateDirectory) | Out-Null
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
    $directoryAcl.AddAccessRule($rule) | Out-Null
}
Set-Acl -LiteralPath $privateDirectory -AclObject $directoryAcl

Write-Host 'Copy the API key from the Token platform. Do not use the Dify application key.'
Write-Host 'Input stays hidden and is saved only in the private local directory.'
$secureKey = Read-Host 'Paste the model API key (input hidden)' -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
$stream = $null
try {
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer).Trim()
    # Accept legacy gateway keys as well as sk-gw keys; prohibit header/control characters.
    if ($key -cnotmatch '^[A-Za-z0-9._~+/=-]{16,512}$' -or $key.StartsWith('app-')) {
        throw 'Unexpected model API key format. No key was saved.'
    }
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($key)
    $stream = [IO.FileStream]::new($keyPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush($true)
    Write-Host 'Model key saved privately. No network request was made. Do not screenshot its contents.'
} finally {
    if ($null -ne $stream) { $stream.Dispose() }
    if ($null -ne $bytes) { [Array]::Clear($bytes, 0, $bytes.Length) }
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    $secureKey.Dispose()
    $key = $null
}
