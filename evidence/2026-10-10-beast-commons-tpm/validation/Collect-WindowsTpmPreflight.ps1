$ErrorActionPreference = 'Stop'
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script in PowerShell opened as Administrator.'
}
$proofDir = Join-Path $env:USERPROFILE 'Documents\BEAST-TPM-Proof'
New-Item -ItemType Directory -Path $proofDir -Force | Out-Null
$tpm = Get-Tpm
$record = [ordered]@{
    schema = 'beast.windows.tpm-preflight.v1'
    collected_at = (Get-Date).ToUniversalTime().ToString('o')
    claim_boundary = 'Host status and public material only; no nonce-bound quote or ARDA appraisal'
    tpm = [ordered]@{
        present = $tpm.TpmPresent
        ready = $tpm.TpmReady
        enabled = $tpm.TpmEnabled
        activated = $tpm.TpmActivated
        manufacturer = $tpm.ManufacturerIdTxt
        manufacturer_version = $tpm.ManufacturerVersion
    }
}
try { $record.secure_boot_enabled = Confirm-SecureBootUEFI }
catch { $record.secure_boot_error = $_.Exception.Message }
try {
    $ek = Get-TpmEndorsementKeyInfo -HashAlgorithm Sha256
    $record.ek_present = $ek.IsPresent
    $record.ek_public_key_hash = [string]$ek.PublicKeyHash
    $certIndex = 0
    foreach ($cert in $ek.ManufacturerCertificates) {
        [IO.File]::WriteAllBytes((Join-Path $proofDir ('ek-manufacturer-' + $certIndex + '.cer')), $cert.RawData)
        $certIndex++
    }
    $record.ek_manufacturer_certificate_count = $certIndex
} catch { $record.ek_error = $_.Exception.Message }
$tpmTool = Join-Path $env:WINDIR 'System32\tpmtool.exe'
if (Test-Path -LiteralPath $tpmTool) {
    & $tpmTool getdeviceinformation 2>&1 | Out-File (Join-Path $proofDir 'device-information.txt') -Encoding utf8
    $record.device_information_exit_code = $LASTEXITCODE
    & $tpmTool gatherlogs $proofDir 2>&1 | Out-File (Join-Path $proofDir 'gatherlogs-result.txt') -Encoding utf8
    $record.gatherlogs_exit_code = $LASTEXITCODE
}
$record | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $proofDir 'preflight.json') -Encoding utf8
Write-Host ('Saved public TPM preflight evidence to ' + $proofDir)
$record | ConvertTo-Json -Depth 6
