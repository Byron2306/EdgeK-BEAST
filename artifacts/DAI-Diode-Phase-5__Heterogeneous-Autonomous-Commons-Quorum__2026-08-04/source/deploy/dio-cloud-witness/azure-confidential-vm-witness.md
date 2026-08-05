# Azure Confidential VM DIO witness setup

Target:

- Region: `southafricanorth`
- Small default SKU: `Standard_DC2as_v6`
- Image: `Canonical:0001-com-ubuntu-confidential-vm-jammy:22_04-lts-cvm:latest`
- Security type: `ConfidentialVM`
- vTPM: enabled
- Secure Boot: enabled
- OS disk security encryption: `VMGuestStateOnly`

This creates a remote hardware-rooted candidate for the DIO governance witness.
It does not by itself grant execution or production authority.

## Commands

Read-only preflight:

```bash
scripts/setup_dio_azure_confidential_vm.sh preflight
```

Read-only quota check:

```bash
scripts/setup_dio_azure_confidential_vm.sh quota
```

Read-only SKU visibility check:

```bash
scripts/setup_dio_azure_confidential_vm.sh skus
```

If the quota limit is `0`, print the exact request parameters:

```bash
scripts/setup_dio_azure_confidential_vm.sh request-quota-help
```

Create billable Azure resources:

```bash
scripts/setup_dio_azure_confidential_vm.sh create
```

Describe the VM:

```bash
scripts/setup_dio_azure_confidential_vm.sh describe
```

Print the in-guest attestation collection flow:

```bash
scripts/setup_dio_azure_confidential_vm.sh attest-help
```

After collecting the raw Azure guest-attestation / MAA token from inside the
Confidential VM, normalize it into BEAST evidence:

```bash
PYTHONNOUSERSITE=1 .venv/bin/python scripts/harvest_dio_azure_tee_attestation.py \
  --location southafricanorth \
  --resource-group dio-azure-witness-sa-rg \
  --vm dio-azure-tee-governance-01 \
  --raw-attestation-token-file /path/to/dio_azure_maa_token.jwt \
  --out evidence/dai-diode/phase2.1-cloud-witness/azure-sa-live-attested-001
```

## Evidence boundary

## South Africa North status

As of the current setup attempt, South Africa North exposes the required
`Standard_DC2as_v6` SKU and other `standardDCasv6Family` SKUs with availability
zones, but the subscription quota for `standardDCasv6Family` is `0`.

That means:

- region/SKU availability: yes;
- subscription quota grant: no;
- required quota request: `standardDCasv6Family`, limit `2`.

Azure account ownership and Azure VM inventory are not hardware attestation.

BEAST only admits a green Azure cloud TEE witness when the harvester sees:

- a Confidential VM inventory record;
- a raw guest-attestation / MAA token or report;
- pinned verifier digest;
- pinned measurement digest;
- pinned DIO witness public key;
- challenge nonce;
- governance epoch;
- freshness window.

The current harvester digest-binds the raw token and VM identity. Full MAA
JWT/x5c chain verification remains a publication-grade closure task.
