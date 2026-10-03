# GCP Confidential Space DIO witness notes

Live target:

- Project: `dio-attested-witnesses`
- Zone: `africa-south1-a`
- Instance: `dio-gcp-phase2-witness-01`
- Instance ID: `4372098688263098400`
- Machine: `n2d-standard-2`
- Confidential config: `confidentialInstanceType = SEV`
- Workload image:
  `africa-south1-docker.pkg.dev/dio-attested-witnesses/dio-witnesses/phase2-attestation-smoke@sha256:1a9c250c7b806f77131b883b6db6b7901a89fc0237e9166ba39cd4023c87d592`
- Image digest:
  `sha256:1a9c250c7b806f77131b883b6db6b7901a89fc0237e9166ba39cd4023c87d592`

## What worked

The VM exists and the BEAST GCP harvester can now normalize the current GCP
`confidentialInstanceType` response shape into digest-bound DIO cloud evidence.

Current corrected inventory receipt:

```text
evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-live-003/dio_gcp_tee_attestation_harvest.json
```

Digest:

```text
sha256:954dba6e267576e888f3920035c988940d90967f0186184fa5adfdc605dbd60b
```

## What failed

The Confidential Space launcher terminated the workload with:

```text
logging redirection only allowed on debug environment by image
```

The instance metadata included:

```text
tee-container-log-redirect=cloud_logging
```

Google's Confidential Space metadata docs state that
`tee-container-log-redirect` interacts with the workload author's launch policy.
If the image policy disallows the selected redirect mode, the launcher refuses
the workload.

## Corrective launch

Recreate the Confidential Space VM without `tee-container-log-redirect`, or use
a workload image whose launch policy explicitly permits the selected logging
mode.

Minimum corrected metadata shape:

```bash
--metadata="^~^tee-image-reference=africa-south1-docker.pkg.dev/dio-attested-witnesses/dio-witnesses/phase2-attestation-smoke@sha256:1a9c250c7b806f77131b883b6db6b7901a89fc0237e9166ba39cd4023c87d592"
```

If logs are needed for development, use an authorized debug image/policy and a
debug Confidential Space image family. Do not claim production-grade
attestation from a debug run.

## Final BEAST harvest with raw token

After the workload writes or returns the raw Confidential Space attestation
token/JWT packet, run:

```bash
PYTHONNOUSERSITE=1 .venv/bin/python scripts/harvest_dio_gcp_tee_attestation.py \
  --project dio-attested-witnesses \
  --zone africa-south1-a \
  --instance dio-gcp-phase2-witness-01 \
  --raw-attestation-token-file /path/to/gcp_confidential_space_attestation.jwt \
  --out evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-attested-001
```

Current boundary:

- `raw_provider_attestation_token_present = false`
- `publication_grade_hardware_attestation = false`
- `production_authority_allowed = false`

## Witness-02 token-claims harvest

Witness `dio-gcp-phase2-witness-02` removed the forbidden log redirect and
successfully reached Confidential Space attestation refresh.

Serial evidence:

```text
evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-token/serial-port-1.txt
```

Extracted token-claims material:

```text
evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-token/gcp_confidential_space_attestation_token_from_serial.txt
```

Token-bound BEAST harvest:

```text
evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-token/dio_gcp_tee_attestation_harvest.json
```

Digest:

```text
sha256:a1280b31dc3102c76f1dffe861ddffdd8d97eb70bc289176c95cd665d248b069
```

Important boundary:

- `raw_provider_attestation_token_present = true`
- `raw_token_shape = opaque_text`
- `publication_grade_hardware_attestation = false`

This is stronger than inventory-only because it binds the Confidential Space
launcher's attestation token-claims material from serial output. It is still not
the final self-contained JWT/cert-chain verifier result.

## Witness-02 workload failure

The workload itself still exited non-zero after attestation setup. The launch
policy showed allowed operator env overrides:

```text
AllowedEnvOverride:[DIO_OUTPUT_BUCKET DIO_OUTPUT_OBJECT DIO_PHASE2_EVIDENCE_ROOT]
```

But witness-02 was launched with:

```text
operator_override_env_vars=[]
```

## Corrective witness-03 launch

Create a GCS output bucket/object, then pass the allowed env vars using
Confidential Space `tee-env-` metadata variables:

```bash
export PINNED_IMAGE="africa-south1-docker.pkg.dev/dio-attested-witnesses/dio-witnesses/phase2-attestation-smoke@sha256:1a9c250c7b806f77131b883b6db6b7901a89fc0237e9166ba39cd4023c87d592"
export DIO_GCP_OUTPUT_BUCKET="dio-gcp-phase2-witness-output"
export DIO_GCP_OUTPUT_OBJECT="witness-03/attestation-packet.json"
export DIO_PHASE2_EVIDENCE_ROOT="sha256:3119d9459d8a6d2a8d7703bcfa041af02ec5a0575ec25af0d6ec9434c69730b2"

gcloud storage buckets create "gs://${DIO_GCP_OUTPUT_BUCKET}" \
  --project=dio-attested-witnesses \
  --location=africa-south1 \
  --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding "gs://${DIO_GCP_OUTPUT_BUCKET}" \
  --member="serviceAccount:dio-gcp-witness@dio-attested-witnesses.iam.gserviceaccount.com" \
  --role="roles/storage.objectCreator"

gcloud compute instances create dio-gcp-phase2-witness-03 \
  --project=dio-attested-witnesses \
  --zone=africa-south1-a \
  --machine-type=n2d-standard-2 \
  --confidential-compute-type=SEV \
  --maintenance-policy=MIGRATE \
  --shielded-secure-boot \
  --image-project=confidential-space-images \
  --image-family=confidential-space \
  --metadata="^~^tee-image-reference=${PINNED_IMAGE}~tee-env-DIO_OUTPUT_BUCKET=${DIO_GCP_OUTPUT_BUCKET}~tee-env-DIO_OUTPUT_OBJECT=${DIO_GCP_OUTPUT_OBJECT}~tee-env-DIO_PHASE2_EVIDENCE_ROOT=${DIO_PHASE2_EVIDENCE_ROOT}" \
  --service-account=dio-gcp-witness@dio-attested-witnesses.iam.gserviceaccount.com \
  --scopes=cloud-platform
```

Then fetch the expected packet:

```bash
gcloud storage cp "gs://${DIO_GCP_OUTPUT_BUCKET}/${DIO_GCP_OUTPUT_OBJECT}" \
  evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-03/attestation-packet.json
```

## Compact provider JWT recovered

The repaired witness-02 run recovered a compact provider JWT and wrote a full
DIO Google attestation packet:

```text
evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-repair-20260804T190327Z/attestation-packet.json
```

Packet summary:

```text
packet_digest = sha256:c3118d58a8aed6d3c63c1c62a917603b00fd1d28bdca97a5b2b6856c57ef33cb
vote_digest   = sha256:b2d4ef2c6039cad816d26b158795fabdaa9296f2c9eb5f8027493566412ad9b7
binding       = sha256:655ba0a3b1d68b164db043591d081687b87e0ad40dd7329edda85352226b440d
evidence_root = sha256:3119d9459d8a6d2a8d7703bcfa041af02ec5a0575ec25af0d6ec9434c69730b2
world_state   = sha256:39c752c77235e737443085aca917b894410f6d3242d172259a76e431b3617b8f
authority     = attestation_test_only
```

The local packet verifier recomputes the packet digest, vote digest and binding,
then decodes the compact JWT and checks:

- issuer: `https://confidentialcomputing.googleapis.com`
- audience: `dio://phase2/quorum/v1`
- nonce: `eat_nonce == binding`
- software name: `CONFIDENTIAL_SPACE`
- hardware model: `GCP_AMD_SEV`
- secure boot: `true`
- pinned image digest:
  `sha256:1a9c250c7b806f77131b883b6db6b7901a89fc0237e9166ba39cd4023c87d592`
- GCP project / zone / instance:
  `dio-attested-witnesses`, `africa-south1-a`,
  `dio-gcp-phase2-witness-02`
- `DIO_PHASE2_EVIDENCE_ROOT` env override matches the vote evidence root.

Verification receipt:

```text
evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-repair-20260804T190327Z/attestation-packet-verification.json
```

Verification digest:

```text
sha256:4c32e3049f14459d0dfb37e371a0982f2634f2da213f4ff44e4a03dc1d4aed01
```

Boundary:

- `passed = true`
- `red_gates = []`
- `signature_verified = false`
- `production_authority_allowed = false`

That first receipt was an internal claim/binding verifier only.

## Google JWKS signature verification

The verifier now has a stronger provider-signature mode:

```bash
PACKET=evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-repair-20260804T190327Z/attestation-packet.json
JWKS=evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-repair-20260804T190327Z/google-confidential-space-jwks.json
OUT=evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-repair-20260804T190327Z/attestation-packet-verification-google-signature-offline-frozen.json

PYTHONNOUSERSITE=1 .venv/bin/python scripts/verify_dio_gcp_attestation_packet.py "$PACKET" \
  --expected-image-digest sha256:1a9c250c7b806f77131b883b6db6b7901a89fc0237e9166ba39cd4023c87d592 \
  --expected-image-reference africa-south1-docker.pkg.dev/dio-attested-witnesses/dio-witnesses/phase2-attestation-smoke@sha256:1a9c250c7b806f77131b883b6db6b7901a89fc0237e9166ba39cd4023c87d592 \
  --expected-evidence-root sha256:3119d9459d8a6d2a8d7703bcfa041af02ec5a0575ec25af0d6ec9434c69730b2 \
  --expected-instance dio-gcp-phase2-witness-02 \
  --expected-project dio-attested-witnesses \
  --expected-zone africa-south1-a \
  --verify-google-signature \
  --jwks-file "$JWKS" \
  --evaluation-time 2026-08-04T19:17:03+00:00 \
  --out "$OUT"
```

The live verifier fetched Google's Confidential Space JWKS and saved a frozen
copy for offline reproduction:

```text
google-confidential-space-jwks.json
jwks_digest = sha256:9aa5655c53bca510b2d13bcb9d7ebea9302b973bc50b35dae93ddadaa8968c17
```

Frozen offline verification result:

```text
receipt = evidence/dai-diode/phase2.1-cloud-witness/gcp-africa-south1-witness-02-repair-20260804T190327Z/attestation-packet-verification-google-signature-offline-frozen.json
receipt_file_sha256 = cb2d7fa3bb8ebe8b7fdf6a2520726e0845d47cd8236901f69e608d6153b91e45
verification_digest = sha256:966bf9fb70c48cd9b0cec71132ba6fc4ba90cc3e64e3a27da8ce3d85901c2edf
signature_verified = true
jwt_signature_rs256_google_jwks_valid = true
red_gates = []
```

Remaining boundary:

- The compact JWT signature is verified against Google Confidential Space JWKS.
- The claim is still bounded to Google-attested token semantics; this verifier
  does not independently reconstruct the lower-level SNP/TDX quote material.
- `production_authority_allowed = false`.
