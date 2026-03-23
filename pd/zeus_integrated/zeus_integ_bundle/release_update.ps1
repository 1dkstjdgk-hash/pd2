param(
    [string]$Name = "ZeusIntegProtectedV1",
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$ManifestUrl,
    [string]$ZipUrl = "",
    [string]$ReleaseTag = "",
    [string]$Channel = "stable",
    [switch]$Clean,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$BuildScript = Join-Path $Root "build_protected.ps1"
$PackScript = Join-Path $Root "pack_protected_module.py"
$ManifestScript = Join-Path $Root "zeus_make_manifest.py"
$UpdateConfigPath = Join-Path $Root "zeus_update_config.json"
$VersionPath = Join-Path $Root "zeus_version.json"
$DistDir = Join-Path $Root ("dist\\" + $Name)
$ReleaseDir = Join-Path $Root "release"
$VersionSafe = ($Version -replace '[^0-9A-Za-z._-]', '_')
$ZipName = "${Name}_v${VersionSafe}_win64.zip"
$ZipPath = Join-Path $ReleaseDir $ZipName
$LatestZipName = "${Name}_win64.zip"
$LatestZipPath = Join-Path $ReleaseDir $LatestZipName
$ManifestOut = Join-Path $ReleaseDir "zeus_update_manifest.json"
$ExeName = "${Name}.exe"

if ([string]::IsNullOrWhiteSpace($ReleaseTag)) {
    # Default to the tag pattern currently used in zeus-updates releases.
    $ReleaseTag = "zeus_update_$VersionSafe"
}

if ([string]::IsNullOrWhiteSpace($ZipUrl)) {
    # Auto-build a sane GitHub release asset URL from ManifestUrl, so users
    # do not need to hand-edit tag/file names every release.
    try {
        $mu = [Uri]$ManifestUrl
    } catch {
        throw "invalid ManifestUrl: $ManifestUrl"
    }
    if ($mu.Host -ieq "raw.githubusercontent.com") {
        $parts = $mu.AbsolutePath.Trim("/").Split("/")
        if ($parts.Length -ge 2) {
            $owner = $parts[0]
            $repo = $parts[1]
            $ZipUrl = "https://github.com/$owner/$repo/releases/download/$ReleaseTag/$LatestZipName"
        }
    }
    if ([string]::IsNullOrWhiteSpace($ZipUrl)) {
        throw "ZipUrl missing and could not infer from ManifestUrl. Pass -ZipUrl explicitly."
    }
}

if (-not (Test-Path $BuildScript)) {
    throw "build script missing: $BuildScript"
}
if (-not (Test-Path $ManifestScript)) {
    throw "manifest script missing: $ManifestScript"
}

Write-Host "[step 1/4] update config for auto-update..."
$cfg = [ordered]@{
    enabled = $true
    manifest_url = $ManifestUrl
    channel = $Channel
    check_timeout_sec = 8
}
$cfg | ConvertTo-Json | Set-Content -Path $UpdateConfigPath -Encoding utf8

Write-Host "[step 2/4] protected build..."
if (-not $SkipBuild) {
    $buildArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", $BuildScript,
        "-Name", $Name,
        "-Version", $Version
    )
    if ($Clean) {
        $buildArgs += "-Clean"
    }
    & powershell @buildArgs
    if ($LASTEXITCODE -ne 0) {
        throw "build failed with exit code $LASTEXITCODE"
    }
    if (-not (Test-Path $DistDir)) {
        throw "dist folder missing after build: $DistDir"
    }
} else {
    Write-Host "[step 2/4] skip full build, refresh protected core + configs in existing dist..."
    if (-not (Test-Path $DistDir)) {
        throw "dist folder missing for -SkipBuild mode: $DistDir"
    }
    if (-not (Test-Path $PackScript)) {
        throw "pack script missing: $PackScript"
    }

    $packArgs = @($PackScript, "--in", "zeus_integ2.py", "--out", "zeus_integ2.pzb")
    $packed = $false
    $venvPy = Join-Path $Root ".venv\\Scripts\\python.exe"
    if (Test-Path $venvPy) {
        & $venvPy @packArgs
        if ($LASTEXITCODE -eq 0) { $packed = $true }
    }
    if (-not $packed) {
        & py -3 @packArgs
        if ($LASTEXITCODE -eq 0) { $packed = $true }
    }
    if (-not $packed) {
        throw "core pack failed in -SkipBuild mode"
    }

    $coreBlob = Join-Path $Root "zeus_integ2.pzb"
    if (-not (Test-Path $coreBlob)) {
        throw "packed core blob missing: $coreBlob"
    }
    $distInternal = Join-Path $DistDir "_internal"

    Copy-Item $coreBlob (Join-Path $DistDir "zeus_integ2.pzb") -Force
    if (Test-Path $distInternal) {
        Copy-Item $coreBlob (Join-Path $distInternal "zeus_integ2.pzb") -Force
    }

    Copy-Item $UpdateConfigPath (Join-Path $DistDir "zeus_update_config.json") -Force
    if (Test-Path $distInternal) {
        Copy-Item $UpdateConfigPath (Join-Path $distInternal "zeus_update_config.json") -Force
    }
    Copy-Item $VersionPath (Join-Path $DistDir "zeus_version.json") -Force
    if (Test-Path $distInternal) {
        Copy-Item $VersionPath (Join-Path $distInternal "zeus_version.json") -Force
    }
}

Write-Host "[step 3/4] zip release..."
if (-not (Test-Path $ReleaseDir)) {
    New-Item -ItemType Directory -Path $ReleaseDir | Out-Null
}
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
if (Test-Path $LatestZipPath) {
    Remove-Item $LatestZipPath -Force
}
& tar -a -c -f $ZipPath -C (Join-Path $Root "dist") $Name
if ($LASTEXITCODE -ne 0) {
    throw "zip create failed with exit code $LASTEXITCODE"
}
Copy-Item $ZipPath $LatestZipPath -Force

Write-Host "[step 4/4] create update manifest..."
$manifestArgs = @(
    $ManifestScript,
    "--zip", $ZipPath,
    "--url", $ZipUrl,
    "--version", $Version,
    "--exe-name", $ExeName,
    "--channel", $Channel,
    "--out", $ManifestOut
)

$manifestDone = $false
$venvPy = Join-Path $Root ".venv\\Scripts\\python.exe"
if (Test-Path $venvPy) {
    & $venvPy @manifestArgs
    if ($LASTEXITCODE -eq 0) {
        $manifestDone = $true
    }
}
if (-not $manifestDone) {
    & py -3 @manifestArgs
    if ($LASTEXITCODE -eq 0) {
        $manifestDone = $true
    }
}
if (-not $manifestDone) {
    throw "manifest generation failed (py -3 and .venv python failed)"
}

$zipHash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash
Write-Host ""
Write-Host "[release] done"
Write-Host "[release] dist: $DistDir"
Write-Host "[release] zip(versioned): $ZipPath"
Write-Host "[release] zip(latest):    $LatestZipPath"
Write-Host "[release] sha:  $zipHash"
Write-Host "[release] release-tag: $ReleaseTag"
Write-Host "[release] zip-url(manifest): $ZipUrl"
Write-Host "[release] manifest: $ManifestOut"
Write-Host ""
Write-Host "Upload these 2 files to your server:"
Write-Host "  1) $LatestZipName  (attach to GitHub Release tag: $ReleaseTag)"
Write-Host "  2) zeus_update_manifest.json"
Write-Host "Optional local archive for history: $ZipName"
