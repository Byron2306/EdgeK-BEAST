# DIO Azure/GCP cloud TEE witness plan

This is the Phase-2.1C path: turn Azure or Google Cloud into a hardware-rooted
DIO witness.

The account alone gives no authority. A cloud witness is admitted only when a
provider-verified attestation is normalized into `DIOCloudTeeEvidence` and
matches a pinned `DIOCloudTeePolicy`.

## Azure target

Honest claim:

- Azure Confidential VM / confidential computing witness
- provider verification through Microsoft Azure Attestation or equivalent
  Azure guest-attestation flow
- hardware-rooted remote witness only after measurement, nonce and key bind

Pinned fields BEAST requires:

- `provider = azure`
- `tee_type = azure_sev_snp` or `azure_tdx`
- `service_verifier = azure_maa`
- DIO witness public-key fingerprint
- verifier source/build digest
- VM/container measurement digest
- challenge nonce
- governance epoch
- raw attestation digest
- Azure verification digest

## Google Cloud target

Honest claim:

- Google Confidential VM or Confidential Space witness
- provider verification through Google Cloud Attestation
- hardware-rooted remote witness only after measurement, nonce and key bind

Pinned fields BEAST requires:

- `provider = gcp`
- `tee_type = gcp_confidential_vm_vtpm` or `gcp_confidential_space`
- `service_verifier = google_cloud_attestation`
- DIO witness public-key fingerprint
- verifier source/build digest
- VM/container measurement digest
- challenge nonce
- governance epoch
- raw attestation digest
- Google verification digest

## Refusal cases

The admission law refuses:

- wrong provider;
- wrong TEE type;
- wrong service verifier;
- wrong node role;
- wrong challenge nonce;
- wrong governance epoch;
- unpinned verifier build;
- unpinned measurement;
- unpinned public key;
- expired evidence;
- authority greater than `hardware_rooted_governance_vote_only`.

## Next implementation step

Add vendor harvesters:

- `scripts/harvest_dio_azure_tee_attestation.py`
- `scripts/harvest_dio_gcp_tee_attestation.py`

Those scripts should perform the cloud-specific token/report request and write
normalized `DIOCloudTeeEvidence`. The BEAST admission law is already provider
agnostic and tested.
