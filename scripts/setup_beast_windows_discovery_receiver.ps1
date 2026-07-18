[CmdletBinding()]
param(
    [string]$BundleRoot = (Split-Path -Parent $MyInvocation.MyCommand.Path),
    [string]$OutputDirectory = "$HOME\Downloads\beast-discovery-receiver",
    [string]$Scenario = "",
    [string]$ArdaPublicKey = "",
    [string]$VerifierPlan = "",
    [string]$Workspace = "",
    [string]$LocalVerifierCommand = "",
    [switch]$SkipOllama
)
$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "This setup must run on Windows." }
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { throw "Install Python 3 with the py launcher, then rerun." }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
if (-not $Scenario) { $Scenario = Join-Path $BundleRoot "examples\windows-receiver-fixture\scenario.json" }
if (-not (Test-Path $Scenario)) { throw "Scenario not found: $Scenario" }
if (-not $ArdaPublicKey) { $ArdaPublicKey = Join-Path $BundleRoot "examples\windows-receiver-fixture\arda-public.pem" }
if (-not (Test-Path $ArdaPublicKey)) { throw "ARDA public key not found: $ArdaPublicKey" }
if ($VerifierPlan) { $env:BEAST_RECEIVER_VERIFIER_PLAN = (Resolve-Path $VerifierPlan).Path }
if ($Workspace) { $env:BEAST_RECEIVER_WORKSPACE = (Resolve-Path $Workspace).Path }
if (-not $LocalVerifierCommand) { $LocalVerifierCommand = "py -3 `"$(Join-Path $BundleRoot 'scripts\windows_receiver_local_verifier.py')`"" }
if (-not $VerifierPlan) { $VerifierPlan = Join-Path $BundleRoot "examples\windows-receiver-fixture\verifier-plan.json" }
if (Test-Path $VerifierPlan) { $env:BEAST_RECEIVER_VERIFIER_PLAN = (Resolve-Path $VerifierPlan).Path }
Write-Host "Preparing isolated Python environment"
& py -3 -m venv (Join-Path $OutputDirectory "venv")
$venvPy = Join-Path $OutputDirectory "venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip | Out-Null
& $venvPy -m pip install cryptography | Out-Null
if (-not $SkipOllama) {
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) { Write-Warning "Ollama is not installed; receiver verifier must be supplied separately." }
}
$receipt = Join-Path $OutputDirectory "discovery-receiver-receipt.json"
$manifest = Join-Path $OutputDirectory "discovery-receiver-manifest.json"
Write-Host "Running sealed discovery-agnostic receiver"
& $venvPy (Join-Path $BundleRoot "scripts\run_discovery_agnostic_receiver.py") $Scenario --arda-public-key $ArdaPublicKey --local-verifier-command $LocalVerifierCommand --output $receipt
if ($LASTEXITCODE -ne 0) { throw "Receiver run failed." }
$hash = (Get-FileHash $receipt -Algorithm SHA256).Hash.ToLower()
@{ object_type="beast_windows_discovery_receiver_manifest"; version="1.0"; machine=$env:COMPUTERNAME; hardware_attestation="TPM evidence must be attached separately"; receipt_sha256=$hash; created_at=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds() } | ConvertTo-Json | Set-Content -Encoding UTF8 $manifest
Write-Host "Complete. Submit the receipt and manifest for independent verification."
Write-Host $receipt
Write-Host $manifest
