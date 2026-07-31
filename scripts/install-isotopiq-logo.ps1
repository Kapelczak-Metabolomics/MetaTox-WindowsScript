param(
    [string]$SourcePath = "C:\Users\ekapelczak\Downloads\isotopiq-logo.png",
    [string]$DestinationPath = (Join-Path $PSScriptRoot "..\web_app\static\img\isotopiq-logo.png")
)

$resolvedSource = Resolve-Path -LiteralPath $SourcePath -ErrorAction Stop
$resolvedDestination = [System.IO.Path]::GetFullPath($DestinationPath)
$destinationDir = Split-Path -Parent $resolvedDestination

if (-not (Test-Path -LiteralPath $destinationDir)) {
    New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
}

Copy-Item -LiteralPath $resolvedSource -Destination $resolvedDestination -Force
Write-Host "Installed Isotopiq logo:"
Write-Host "  from: $resolvedSource"
Write-Host "  to:   $resolvedDestination"
