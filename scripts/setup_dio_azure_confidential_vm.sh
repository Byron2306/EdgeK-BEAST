#!/usr/bin/env bash
set -Eeuo pipefail

# Create or inspect the Azure Confidential VM that will become the DIO
# hardware-rooted governance witness.
#
# Cost boundary:
#   `preflight` is read-only.
#   `quota` is read-only.
#   `request-quota-help` prints request commands/links; it does not submit.
#   `create` creates billable Azure resources.
#   `delete` removes the resource group named by DIO_AZURE_RESOURCE_GROUP.

MODE="${1:-preflight}"

DIO_AZURE_LOCATION="${DIO_AZURE_LOCATION:-southafricanorth}"
DIO_AZURE_RESOURCE_GROUP="${DIO_AZURE_RESOURCE_GROUP:-dio-azure-witness-sa-rg}"
DIO_AZURE_VM_NAME="${DIO_AZURE_VM_NAME:-dio-azure-tee-governance-01}"
DIO_AZURE_ADMIN_USER="${DIO_AZURE_ADMIN_USER:-azureuser}"
DIO_AZURE_VM_SIZE="${DIO_AZURE_VM_SIZE:-Standard_DC2as_v6}"
DIO_AZURE_QUOTA_FAMILY="${DIO_AZURE_QUOTA_FAMILY:-standardDCasv6Family}"
DIO_AZURE_REQUIRED_CORES="${DIO_AZURE_REQUIRED_CORES:-}"
DIO_AZURE_IMAGE="${DIO_AZURE_IMAGE:-Canonical:0001-com-ubuntu-confidential-vm-jammy:22_04-lts-cvm:latest}"
DIO_AZURE_OS_DISK_SECURITY_ENCRYPTION_TYPE="${DIO_AZURE_OS_DISK_SECURITY_ENCRYPTION_TYPE:-VMGuestStateOnly}"
DIO_AZURE_SSH_KEY="${DIO_AZURE_SSH_KEY:-$PWD/.beast/dio-cloud-witness/azure-witness-ssh-ed25519}"
PYTHON_BIN="${PYTHON_BIN:-$PWD/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

usage() {
  sed -n '1,34p' "$0"
  cat <<USAGE

Usage:
  $0 preflight   # inspect account, providers, candidate sizes and images
  $0 skus        # list visible Confidential VM SKUs in the configured region
  $0 quota       # inspect the VM-family quota needed by the configured SKU
  $0 request-quota-help
                 # print portal/CLI quota request parameters
  $0 create      # create billable Azure resources
  $0 describe    # show VM identity, IP and security profile
  $0 attest-help # print in-guest MAA token collection commands
  $0 delete      # delete the configured resource group

Environment overrides:
  DIO_AZURE_LOCATION=$DIO_AZURE_LOCATION
  DIO_AZURE_RESOURCE_GROUP=$DIO_AZURE_RESOURCE_GROUP
  DIO_AZURE_VM_NAME=$DIO_AZURE_VM_NAME
  DIO_AZURE_ADMIN_USER=$DIO_AZURE_ADMIN_USER
  DIO_AZURE_VM_SIZE=$DIO_AZURE_VM_SIZE
  DIO_AZURE_QUOTA_FAMILY=$DIO_AZURE_QUOTA_FAMILY
  DIO_AZURE_REQUIRED_CORES=${DIO_AZURE_REQUIRED_CORES:-<derived from VM size>}
  DIO_AZURE_IMAGE=$DIO_AZURE_IMAGE
  DIO_AZURE_SSH_KEY=$DIO_AZURE_SSH_KEY
USAGE
}

require_az() {
  command -v az >/dev/null 2>&1 || {
    echo "Azure CLI not found. Install Azure CLI, then run az login." >&2
    exit 2
  }
}

account() {
  az account show \
    --query '{subscription:id,name:name,tenant:tenantId,user:user.name,state:state}' \
    -o table
}

provider_state() {
  local ns="$1"
  az provider show --namespace "$ns" --query registrationState -o tsv 2>/dev/null || true
}

register_provider_if_needed() {
  local ns="$1"
  local state
  state="$(provider_state "$ns")"
  if [[ "$state" != "Registered" ]]; then
    echo "Registering provider $ns (current: ${state:-unknown})"
    az provider register --namespace "$ns" --wait
  fi
}

ensure_ssh_key() {
  if [[ ! -f "$DIO_AZURE_SSH_KEY" ]]; then
    mkdir -p "$(dirname "$DIO_AZURE_SSH_KEY")"
    ssh-keygen -t ed25519 -N "" -f "$DIO_AZURE_SSH_KEY" -C "dio-azure-witness"
  fi
}

preflight() {
  require_az
  echo "Azure account:"
  account
  echo
  echo "Provider states:"
  for ns in Microsoft.Compute Microsoft.Network Microsoft.Attestation; do
    printf '%-24s %s\n' "$ns" "$(provider_state "$ns")"
  done
  echo
  skus
  echo
  echo "Confidential Ubuntu image check:"
  timeout 20s az vm image show --location "$DIO_AZURE_LOCATION" \
    --urn "$DIO_AZURE_IMAGE" \
    --query "{architecture:architecture, urn:'$DIO_AZURE_IMAGE'}" \
    -o table || true
  echo
  echo "Planned create command target:"
  echo "  resource group: $DIO_AZURE_RESOURCE_GROUP"
  echo "  VM:             $DIO_AZURE_VM_NAME"
  echo "  location:       $DIO_AZURE_LOCATION"
  echo "  size:           $DIO_AZURE_VM_SIZE"
  echo "  image:          $DIO_AZURE_IMAGE"
  echo
  quota
}

create_vm() {
  require_az
  register_provider_if_needed Microsoft.Compute
  register_provider_if_needed Microsoft.Network
  register_provider_if_needed Microsoft.Attestation
  ensure_quota
  ensure_ssh_key

  az group create \
    --name "$DIO_AZURE_RESOURCE_GROUP" \
    --location "$DIO_AZURE_LOCATION"

  az vm create \
    --resource-group "$DIO_AZURE_RESOURCE_GROUP" \
    --name "$DIO_AZURE_VM_NAME" \
    --location "$DIO_AZURE_LOCATION" \
    --size "$DIO_AZURE_VM_SIZE" \
    --admin-username "$DIO_AZURE_ADMIN_USER" \
    --ssh-key-values "${DIO_AZURE_SSH_KEY}.pub" \
    --enable-vtpm true \
    --image "$DIO_AZURE_IMAGE" \
    --public-ip-sku Standard \
    --security-type ConfidentialVM \
    --os-disk-security-encryption-type "$DIO_AZURE_OS_DISK_SECURITY_ENCRYPTION_TYPE" \
    --enable-secure-boot true \
    --assign-identity

  describe_vm
}

required_cores() {
  if [[ -n "$DIO_AZURE_REQUIRED_CORES" ]]; then
    echo "$DIO_AZURE_REQUIRED_CORES"
    return
  fi
  local size="$DIO_AZURE_VM_SIZE"
  if [[ "$size" =~ _[A-Za-z]+([0-9]+)[A-Za-z]*_ ]]; then
    echo "${BASH_REMATCH[1]}"
    return
  fi
  echo 2
}

quota_limit() {
  az vm list-usage --location "$DIO_AZURE_LOCATION" \
    --query "[?name.value=='$DIO_AZURE_QUOTA_FAMILY'] | [0].{current:currentValue,limit:limit,unit:unit,name:name.value}" \
    -o json
}

quota() {
  require_az
  local needed
  needed="$(required_cores)"
  echo "Quota check:"
  echo "  location:      $DIO_AZURE_LOCATION"
  echo "  quota family:  $DIO_AZURE_QUOTA_FAMILY"
  echo "  needed cores:  $needed"
  quota_limit
  echo
  echo "Confidential family quota rows:"
  az vm list-usage --location "$DIO_AZURE_LOCATION" \
    --query "[?contains(name.value, 'DC') || contains(name.value, 'EC')].{Name:name.localizedValue,Internal:name.value,Used:currentValue,Limit:limit}" \
    -o table
}

skus() {
  require_az
  local tmp
  tmp="$(mktemp)"
  if ! timeout 55s az vm list-skus \
      --location "$DIO_AZURE_LOCATION" \
      --resource-type virtualMachines \
      --size Standard_DC \
      --zone \
      --all \
      -o json > "$tmp"; then
    echo "Azure SKU query timed out or failed for $DIO_AZURE_LOCATION." >&2
    echo "Falling back to az vm list-sizes for visible DC/EC sizes:"
    timeout 20s az vm list-sizes --location "$DIO_AZURE_LOCATION" \
      --query "[?contains(name, 'DC') || contains(name, 'EC')].{Name:name,Cores:numberOfCores,MemoryMB:memoryInMB}" \
      -o table || true
    rm -f "$tmp"
    return 1
  fi
  "$PYTHON_BIN" - "$tmp" <<'PY'
import json
import sys

rows = json.load(open(sys.argv[1], encoding="utf-8"))
dcas = []
conf = []
for row in rows:
    name = row.get("name", "")
    family = row.get("family", "")
    zones = ",".join(((row.get("locationInfo") or [{}])[0].get("zones") or []))
    restrictions = row.get("restrictions") or []
    if "DC" in name and "as_v6" in name:
        dcas.append((name, family, zones, len(restrictions)))
    if ("DC" in name or "EC" in name) and name.endswith("_v6"):
        conf.append((name, family))

print("Visible DCasv6 SKUs:")
print(f"{'Name':24} {'Family':24} {'Zones':8} Restrictions")
for item in sorted(dcas):
    print(f"{item[0]:24} {item[1]:24} {item[2]:8} {item[3]}")
print()
print("Visible confidential DC/EC v6 families:")
print(f"{'Name':24} Family")
for item in sorted(conf):
    print(f"{item[0]:24} {item[1]}")
PY
  rm -f "$tmp"
}

ensure_quota() {
  local needed limit current
  needed="$(required_cores)"
  limit="$(az vm list-usage --location "$DIO_AZURE_LOCATION" --query "[?name.value=='$DIO_AZURE_QUOTA_FAMILY'] | [0].limit" -o tsv)"
  current="$(az vm list-usage --location "$DIO_AZURE_LOCATION" --query "[?name.value=='$DIO_AZURE_QUOTA_FAMILY'] | [0].currentValue" -o tsv)"
  limit="${limit:-0}"
  current="${current:-0}"
  if (( current + needed > limit )); then
    cat >&2 <<QUOTA_BLOCK
Azure quota gate failed before VM creation.

  location:      $DIO_AZURE_LOCATION
  VM size:       $DIO_AZURE_VM_SIZE
  quota family:  $DIO_AZURE_QUOTA_FAMILY
  current usage: $current
  current limit: $limit
  needed cores:  $needed

Run:
  scripts/setup_dio_azure_confidential_vm.sh request-quota-help

After Azure approves the quota increase, rerun:
  scripts/setup_dio_azure_confidential_vm.sh create
QUOTA_BLOCK
    exit 3
  fi
}

request_quota_help() {
  require_az
  local sub needed
  sub="$(az account show --query id -o tsv)"
  needed="$(required_cores)"
  cat <<QUOTA_HELP
Azure Confidential VM quota request needed.

Real failure from Azure:
  QuotaExceeded for $DIO_AZURE_QUOTA_FAMILY in $DIO_AZURE_LOCATION.

Request:
  Provider:      Microsoft.Compute
  Region:        $DIO_AZURE_LOCATION
  Quota name:    $DIO_AZURE_QUOTA_FAMILY
  New limit:     $needed
  Unit:          Count / vCPUs
  Subscription:  $sub

Portal:
  https://portal.azure.com/#view/Microsoft_Azure_Capacity/QuotaMenuBlade/~/myQuotas

Azure CLI, if the quota extension/API is enabled for your account:
  az quota create \\
    --scope "/subscriptions/$sub/providers/Microsoft.Compute/locations/$DIO_AZURE_LOCATION" \\
    --resource-name "$DIO_AZURE_QUOTA_FAMILY" \\
    --resource-type dedicated \\
    --limit-object value=$needed

Then verify:
  scripts/setup_dio_azure_confidential_vm.sh quota
QUOTA_HELP
}

describe_vm() {
  require_az
  az vm show \
    --resource-group "$DIO_AZURE_RESOURCE_GROUP" \
    --name "$DIO_AZURE_VM_NAME" \
    --show-details \
    --query '{name:name,resourceGroup:resourceGroup,location:location,powerState:powerState,publicIpAddress:publicIps,vmSize:hardwareProfile.vmSize,securityType:securityProfile.securityType,vtpm:securityProfile.uefiSettings.vTpmEnabled,secureBoot:securityProfile.uefiSettings.secureBootEnabled,identity:identity.type}' \
    -o json
  echo
  echo "SSH:"
  echo "  ssh -i \"$DIO_AZURE_SSH_KEY\" ${DIO_AZURE_ADMIN_USER}@\$(az vm show -d -g \"$DIO_AZURE_RESOURCE_GROUP\" -n \"$DIO_AZURE_VM_NAME\" --query publicIps -o tsv)"
}

attest_help() {
  cat <<'ATTEST'
Inside the Azure Confidential VM, run the Microsoft sample flow to produce a raw MAA JWT token:

  sudo apt-get update
  sudo apt-get install -y git build-essential cmake libcurl4-openssl-dev libjsoncpp-dev libboost-all-dev nlohmann-json3-dev jq
  git clone https://github.com/Azure/confidential-computing-cvm-guest-attestation.git
  cd confidential-computing-cvm-guest-attestation/cvm-attestation-sample-app

Then install the current azguestattestation package from Microsoft's package feed as described by Azure's CVM quickstart, build, and emit a token:

  sudo cmake . && make
  sudo ./AttestationClient -o token | tee /tmp/dio_azure_maa_token.jwt

Copy /tmp/dio_azure_maa_token.jwt back to BEAST, then run:

  PYTHONNOUSERSITE=1 .venv/bin/python scripts/harvest_dio_azure_tee_attestation.py \
    --location southafricanorth \
    --resource-group dio-azure-witness-sa-rg \
    --vm dio-azure-tee-governance-01 \
    --raw-attestation-token-file /path/to/dio_azure_maa_token.jwt \
    --out evidence/dai-diode/phase2.1-cloud-witness/azure-live-attested-001

Boundary: BEAST currently digest-binds the raw token and VM identity. Full MAA JWT/x5c chain verification is still a publication-grade closure task.
ATTEST
}

delete_rg() {
  require_az
  echo "Deleting resource group: $DIO_AZURE_RESOURCE_GROUP"
  az group delete --name "$DIO_AZURE_RESOURCE_GROUP" --yes --no-wait
}

case "$MODE" in
  preflight) preflight ;;
  skus) skus ;;
  quota) quota ;;
  request-quota-help) request_quota_help ;;
  create) create_vm ;;
  describe) describe_vm ;;
  attest-help) attest_help ;;
  delete) delete_rg ;;
  -h|--help|help) usage ;;
  *)
    echo "Unknown mode: $MODE" >&2
    usage
    exit 2
    ;;
esac
