<#
.SYNOPSIS
    Porterminal installer for Windows
.DESCRIPTION
    Installs Porterminal via uv/uvx. Installs uv first if not present.
.EXAMPLE
    powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/lyehe/porterminal/main/install.ps1 | iex"
#>

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  ____             __                      _             __" -ForegroundColor Cyan
Write-Host " / __ \____  _____/ /____  _________ ___  (_)___  ____ _/ /" -ForegroundColor Cyan
Write-Host "/ /_/ / __ \/ ___/ __/ _ \/ ___/ __  __ \/ / __ \/ __  / / " -ForegroundColor Cyan
Write-Host "/ ____/ /_/ / /  / /_/  __/ /  / / / / / / / / / / /_/ / /  " -ForegroundColor Cyan
Write-Host "/_/    \____/_/   \__/\___/_/  /_/ /_/ /_/_/_/ /_/\__,_/_/   " -ForegroundColor Cyan
Write-Host "                                                      >_" -ForegroundColor Blue
Write-Host ""

# Check if uv is installed
$uvPath = Get-Command uv -ErrorAction SilentlyContinue

if (-not $uvPath) {
    Write-Host "[1/2] Installing uv..." -ForegroundColor Yellow

    # Install uv using their official installer
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    }
    catch {
        Write-Host "Failed to install uv: $_" -ForegroundColor Red
        Write-Host "Please install uv manually: https://docs.astral.sh/uv/" -ForegroundColor Red
        exit 1
    }

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

    Write-Host "[OK] uv installed" -ForegroundColor Green
}
else {
    Write-Host "[1/2] uv found" -ForegroundColor Green
}

Write-Host "[2/2] Installing Porterminal..." -ForegroundColor Yellow

# Install ptn using uv tool
try {
    & uv tool install --force ptn
}
catch {
    Write-Host "Failed to install Porterminal: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[OK] Porterminal installed!" -ForegroundColor Green
Write-Host ""
Write-Host "Run:" -ForegroundColor White
Write-Host "  ptn" -ForegroundColor Cyan
Write-Host ""
Write-Host "Or run without installing:" -ForegroundColor DarkGray
Write-Host "  uvx ptn" -ForegroundColor DarkGray
Write-Host ""
