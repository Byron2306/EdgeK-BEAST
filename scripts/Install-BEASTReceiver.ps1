[CmdletBinding()]
param([string]$Destination = "$HOME\BEAST-receiver")
$ErrorActionPreference = "Stop"
$zip = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "beast-windows-discovery-receiver.zip"
if (-not (Test-Path $zip)) { throw "Place this launcher beside beast-windows-discovery-receiver.zip" }
Expand-Archive -Force $zip $Destination
Set-Location (Join-Path $Destination "receiver")
Set-ExecutionPolicy -Scope Process Bypass
& .\scripts\setup_beast_windows_discovery_receiver.ps1
