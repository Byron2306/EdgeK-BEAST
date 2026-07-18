[CmdletBinding()]
param(
    [string]$Model = "qwen2.5:0.5b",
    [string]$OutputDirectory = "$HOME\Downloads\beast-windows-full-replication"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Require-Command([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) { throw "Required command is unavailable: $Name" }
    return $command
}

Write-Host "[1/7] Checking Windows and Python"
if ($env:OS -ne "Windows_NT") { throw "This setup must run on Windows." }
$Python = Get-Command py -ErrorAction SilentlyContinue
if (-not $Python) { throw "Python Launcher is missing. Install Python 3 from python.org, enable the py launcher, then rerun." }
& py -3 --version

Write-Host "[2/7] Checking Ollama"
$Ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $Ollama) {
    $Installer = Join-Path $env:TEMP "OllamaSetup.exe"
    Write-Host "Downloading the official Ollama Windows installer..."
    Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $Installer
    $Signature = Get-AuthenticodeSignature $Installer
    if ($Signature.Status -ne "Valid") {
        Remove-Item $Installer -Force -ErrorAction SilentlyContinue
        throw "Ollama installer Authenticode signature is not valid: $($Signature.Status)"
    }
    Write-Host "Verified installer signer: $($Signature.SignerCertificate.Subject)"
    Write-Host "Complete the official Ollama installer window. No administrator account is normally required."
    Start-Process -FilePath $Installer -Wait
    $env:Path = "$env:LOCALAPPDATA\Programs\Ollama;$env:Path"
    $Ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $Ollama) { throw "Ollama was installed but is not visible yet. Open a new PowerShell and rerun this script." }
}
& ollama --version

Write-Host "[3/7] Waiting for the local Ollama API"
$Ready = $false
for ($i=0; $i -lt 30; $i++) {
    try { $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2; $Ready=$true; break } catch { Start-Sleep -Seconds 2 }
}
if (-not $Ready) { throw "Ollama is installed but its local API did not become ready on 127.0.0.1:11434." }

Write-Host "[4/7] Pulling exact experiment model $Model"
& ollama pull $Model
if ($LASTEXITCODE -ne 0) { throw "Ollama model pull failed." }

Write-Host "[5/7] Preparing receipt directory"
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$PortRunner = Join-Path $ScriptRoot "windows_port_crystal_replication.py"
$UpliftRunner = Join-Path $ScriptRoot "windows_ollama_uplift_replication.py"
if (-not (Test-Path $PortRunner) -or -not (Test-Path $UpliftRunner)) { throw "Replication bundle is incomplete." }

Write-Host "[6/7] Running independent physical port-domain receipt"
$PortReceipt = Join-Path $OutputDirectory "windows-port-crystal-receipt.json"
& py -3 $PortRunner --output $PortReceipt
if ($LASTEXITCODE -ne 0) { throw "Port-domain replication failed." }

Write-Host "[7/7] Running blinded Ollama baseline versus residual crystal"
$UpliftReceipt = Join-Path $OutputDirectory "windows-ollama-uplift-receipt.json"
& py -3 $UpliftRunner --model $Model --output $UpliftReceipt
if ($LASTEXITCODE -ne 0) { throw "Ollama uplift replication failed." }

$Manifest = @{
    object_type = "beast_windows_replication_manifest"
    version = "1.0"
    machine = $env:COMPUTERNAME
    model = $Model
    port_receipt = (Get-FileHash $PortReceipt -Algorithm SHA256).Hash.ToLower()
    uplift_receipt = (Get-FileHash $UpliftReceipt -Algorithm SHA256).Hash.ToLower()
    created_at = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
}
$ManifestPath = Join-Path $OutputDirectory "windows-replication-manifest.json"
$Manifest | ConvertTo-Json | Set-Content -Encoding UTF8 $ManifestPath

Write-Host "Complete. Attach these three files:"
Write-Host "  $PortReceipt"
Write-Host "  $UpliftReceipt"
Write-Host "  $ManifestPath"
