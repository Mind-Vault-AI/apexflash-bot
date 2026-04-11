Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:ISO_GUARD_BYPASS -eq "1") {
    Write-Host "[ISO-GUARD] Bypass active (ISO_GUARD_BYPASS=1)."
    exit 0
}

$gitDir = git rev-parse --git-dir 2>$null
if (-not $gitDir) { exit 0 }
if (Test-Path (Join-Path $gitDir "rebase-merge")) { exit 0 }
if (Test-Path (Join-Path $gitDir "rebase-apply")) { exit 0 }
if (Test-Path (Join-Path $gitDir "MERGE_HEAD")) { exit 0 }

$staged = @(git diff --cached --name-only --diff-filter=ACMR)
if ($staged.Count -eq 0) { exit 0 }

$normalized = @($staged | ForEach-Object { ($_ -replace "\\", "/").Trim() })

$secretPattern = '(?i)(^|/)(\.env(\.|$)|ApexFlashAPI\.env$|id_ed25519(\.pub|\.tar\.gz)?$|private_key\.txt$|public_key\.txt$|.*\.(pem|key)$)'
$blocked = @($normalized | Where-Object { $_ -match $secretPattern })
if ($blocked.Count -gt 0) {
    Write-Host "[ISO-GUARD] BLOCKED: Secret file(s) staged:" -ForegroundColor Red
    $blocked | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    Write-Host "Unstage these files before commit." -ForegroundColor Yellow
    exit 1
}

$exempt = @(
    '^VERSION$',
    '^NOW\.md$',
    '^HANDOVER_GODMODE\.md$',
    '^\.gitignore$',
    '^\.gitattributes$',
    '^bump_version\.ps1$',
    '^\.githooks/',
    '^README(\.md)?$',
    '^docs/'
)

function Test-ExemptPath([string]$path) {
    foreach ($p in $exempt) {
        if ($path -match $p) { return $true }
    }
    return $false
}

$versionStaged = $normalized -contains "VERSION"
$requiresVersion = $false
foreach ($f in $normalized) {
    if (-not (Test-ExemptPath $f)) {
        $requiresVersion = $true
        break
    }
}

if ($requiresVersion -and -not $versionStaged) {
    Write-Host "[ISO-GUARD] BLOCKED: VERSION is not staged." -ForegroundColor Red
    Write-Host "Run .\bump_version.ps1 and stage VERSION + NOW.md." -ForegroundColor Yellow
    exit 1
}

if ((Test-Path "VERSION") -and (Test-Path "NOW.md")) {
    $version = (Get-Content "VERSION" -Raw).Trim()
    $now = Get-Content "NOW.md" -Raw
    $m = [regex]::Match($now, '(?m)^- Version:\s*v([0-9]+\.[0-9]+\.[0-9x]+)\s*$')
    if (-not $m.Success) {
        Write-Host "[ISO-GUARD] BLOCKED: NOW.md missing '- Version: vX.Y.Z'." -ForegroundColor Red
        exit 1
    }
    $nowVersion = $m.Groups[1].Value
    if ($version -ne $nowVersion) {
        Write-Host "[ISO-GUARD] BLOCKED: VERSION ($version) != NOW.md ($nowVersion)." -ForegroundColor Red
        exit 1
    }
}

Write-Host "[ISO-GUARD] OK" -ForegroundColor Green
exit 0
