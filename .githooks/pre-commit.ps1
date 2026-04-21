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

# ── Hardcoded secret CONTENT scan (CEO/Erik policy: ALL secrets in .env) ──
# Patterns for known secret formats — extend as new providers are added.
$secretContentPatterns = @(
    @{ name = "Render API key";  pattern = 'rnd_[A-Za-z0-9]{15,}' },
    @{ name = "OpenAI/Stripe sk";pattern = '\bsk-[A-Za-z0-9]{20,}' },
    @{ name = "Stripe live key"; pattern = '\b(sk|pk|rk)_live_[A-Za-z0-9]{20,}' },
    @{ name = "GitHub PAT";      pattern = '\bghp_[A-Za-z0-9]{20,}' },
    @{ name = "GitHub fine PAT"; pattern = '\bgithub_pat_[A-Za-z0-9_]{40,}' },
    @{ name = "Google API key";  pattern = '\bAIza[A-Za-z0-9_-]{30,}' },
    @{ name = "Telegram token";  pattern = '\b[0-9]{9,}:AA[A-Za-z0-9_-]{30,}' },
    @{ name = "Slack token";     pattern = '\bxox[abpsr]-[A-Za-z0-9-]{10,}' },
    @{ name = "AWS access key";  pattern = '\b(AKIA|ASIA)[A-Z0-9]{16}\b' }
)

$contentViolations = @()
foreach ($f in $normalized) {
    if (-not (Test-Path $f)) { continue }
    if ($f -match '\.(png|jpg|jpeg|gif|pdf|zip|lock|sqlite|db|bin|exe|dll)$') { continue }
    if ($f -match '\.githooks/pre-commit\.ps1$') { continue }  # don't scan self
    try {
        $content = git show ":$f" 2>$null
        if (-not $content) { continue }
        foreach ($p in $secretContentPatterns) {
            if ([regex]::IsMatch($content, $p.pattern)) {
                $contentViolations += [pscustomobject]@{ file = $f; kind = $p.name }
            }
        }
    } catch { }
}

if ($contentViolations.Count -gt 0) {
    Write-Host "[ISO-GUARD] BLOCKED: Hardcoded secret detected in staged content:" -ForegroundColor Red
    $contentViolations | ForEach-Object {
        Write-Host " - $($_.file): $($_.kind)" -ForegroundColor Red
    }
    Write-Host "" -ForegroundColor Yellow
    Write-Host "Policy (CEO/Erik): ALL secrets MUST come from .env (Box Drive SSOT)." -ForegroundColor Yellow
    Write-Host "Replace with: value = os.getenv('NAME'); raise if missing." -ForegroundColor Yellow
    Write-Host "To bypass (emergencies ONLY): set ISO_GUARD_BYPASS=1" -ForegroundColor DarkYellow
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
