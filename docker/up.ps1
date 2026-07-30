# Recommended MetaTox startup for Windows PowerShell.
param(
    [switch]$NoCache
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "Stopping any existing MetaTox container..."
docker compose down

if ($NoCache) {
    Write-Host "Rebuilding image without cache..."
    docker compose build --no-cache
} else {
    Write-Host "Rebuilding image..."
    docker compose build
}

Write-Host "Starting MetaTox with privileged mode enabled for nested Apptainer..."
docker compose up
