param([string]$ConfigRoot = (Join-Path $env:LOCALAPPDATA 'CampusPilot'))
$ErrorActionPreference = 'Stop'
$ConfigRoot = [System.IO.Path]::GetFullPath($ConfigRoot)
$repoRoot = [System.IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
if ($ConfigRoot.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose a configuration directory outside the repository.'
}
$secretRoot = Join-Path $ConfigRoot 'secrets'
New-Item -ItemType Directory -Path $secretRoot -Force | Out-Null
foreach ($name in @('model-key.txt', 'openrouter-jev-key.txt', 'dify-dataset-key.txt')) {
    $target = Join-Path $secretRoot $name
    if (-not (Test-Path -LiteralPath $target)) {
        [System.IO.File]::WriteAllText($target, '', [System.Text.UTF8Encoding]::new($false))
    }
}
# Restrict this new secret directory to the current Windows identity and SYSTEM.
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = [System.Security.AccessControl.DirectorySecurity]::new()
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in @($identity, [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
    $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
        $sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $secretRoot -AclObject $acl
$template = @'
# Dot-source this file: . "C:\Users\21207\AppData\Local\CampusPilot\migration.ps1"
# Each key file contains exactly one key on one line, no quotes or KEY= prefix.
$env:CAMPUSPILOT_RUNTIME_MODE = 'legacy' # phase1 / phase2 after release gates
$env:CAMPUSPILOT_MODEL_BASE_URL = '' # HTTPS API base, e.g. https://openrouter.ai/api/v1
$env:CAMPUSPILOT_MODEL = '' # Generation model ID, separate from the Jev decision model
$env:CAMPUSPILOT_MODEL_KEY_FILE = '__SECRET_ROOT__\model-key.txt'
$env:CAMPUSPILOT_MODEL_INPUT_USD_PER_MILLION = '' # Known current input price required for batch
$env:CAMPUSPILOT_MODEL_OUTPUT_USD_PER_MILLION = ''
$env:CAMPUSPILOT_JEV_MODEL = 'typesafe/jev-1.13'
$env:CAMPUSPILOT_JEV_KEY_FILE = '__SECRET_ROOT__\openrouter-jev-key.txt'
$env:CAMPUSPILOT_JEV_INPUT_USD_PER_MILLION = '' # Verify price before batch; current documented 0.042
$env:CAMPUSPILOT_JEV_OUTPUT_USD_PER_MILLION = '' # Current documented 0
$env:DIFY_DATASET_BASE_URL = 'https://api.dify.ai/v1'
$env:DIFY_DATASET_IDS = '411a785a-6732-4e7f-838e-2720b19e60d9' # Audited CampusPilot dataset
$env:DIFY_DATASET_KEY_FILE = '__SECRET_ROOT__\dify-dataset-key.txt'
$env:CAMPUSPILOT_EVALUATION_DIR = '__CONFIG_ROOT__\evaluation'
$env:CAMPUSPILOT_DIRECT_RULES_REPORT = '' # Passing artifact-bound evaluation and independent QA
'@
$configPath = Join-Path $ConfigRoot 'migration.ps1'
if (-not (Test-Path -LiteralPath $configPath)) {
    $template = $template.Replace('__SECRET_ROOT__', $secretRoot).Replace('__CONFIG_ROOT__', $ConfigRoot)
    [System.IO.File]::WriteAllText($configPath, $template, [System.Text.UTF8Encoding]::new($false))
}
Write-Output "Configuration: $configPath"
Write-Output "Secret files: $secretRoot (existing contents preserved)"
