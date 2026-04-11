param(
    [ValidateSet("patch", "minor", "major")]
    [string]$type = "patch",
    [Parameter(Mandatory = $true)]
    [string]$what
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$versionFile = Join-Path $root "VERSION"
$nowFile = Join-Path $root "NOW.md"

if (-not (Test-Path $versionFile)) {
    throw "VERSION not found: $versionFile"
}

$current = (Get-Content $versionFile -Raw).Trim()
$parts = $current.Split('.')
if ($parts.Count -ne 3) {
    throw "VERSION must be semver like 3.23.0"
}

[int]$major = $parts[0]
[int]$minor = $parts[1]
[int]$patch = $parts[2]

switch ($type) {
    "major" { $major++; $minor = 0; $patch = 0 }
    "minor" { $minor++; $patch = 0 }
    "patch" { $patch++ }
}

$new = "$major.$minor.$patch"
$today = Get-Date -Format "yyyy-MM-dd"

Set-Content $versionFile "$new`n" -NoNewline

if (Test-Path $nowFile) {
    $content = Get-Content $nowFile -Raw
    $content = $content -replace '(?m)(^# Last updated:\s*)\d{4}-\d{2}-\d{2}', "`${1}$today"
    $content = $content -replace '(?m)(^- Version:\s*)v[0-9]+\.[0-9]+\.[0-9x]+', "`${1}v$new"
    Set-Content $nowFile $content -NoNewline -Encoding UTF8
}

Write-Host "Version bumped: $current -> $new"
Write-Host "Change: $what"
