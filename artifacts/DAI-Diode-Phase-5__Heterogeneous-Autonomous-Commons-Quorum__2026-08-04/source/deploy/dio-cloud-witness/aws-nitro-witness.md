# AWS Nitro DIO witness setup

This is the AWS leg of the DIO Phase-2.1 cloud witness path.

Honest target:

- AWS account and EC2 inventory prove account reachability only.
- NitroTPM support or Nitro Enclave enablement proves the instance was launched
  with an AWS attestation-capable runtime shape.
- A hardware-witness candidate requires a raw NitroTPM or Nitro Enclave
  attestation document captured inside the instance/enclave.
- Publication-grade authority still requires full COSE signature, certificate
  chain and PCR policy verification.

## Current local target

```text
region = af-south-1
```

Live attempt:

```text
receipt = evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-001/dio_aws_tee_attestation_harvest.json
blocked_reason = aws_ec2_describe_instances_unavailable_or_unauthorized
harvest_digest = sha256:b46c18ef16f91f2c6c0bedaf2e91bcbcc59f71f1493d76af75432ed870e2d882
```

STS identity is available, but the witness IAM user does not yet have
`ec2:DescribeInstances` in `af-south-1`. The harvester therefore stops before
claiming EC2/Nitro witness status.

Minimum read-only inventory permission for the next AWS attempt:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeRegions"
      ],
      "Resource": "*"
    }
  ]
}
```

The harvester:

```bash
PYTHONNOUSERSITE=1 .venv/bin/python scripts/harvest_dio_aws_tee_attestation.py \
  --region af-south-1 \
  --out evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-001
```

If more than one EC2 instance exists, pass:

```bash
--instance-id i-...
```

## In-guest attestation collection

For NitroTPM instance attestation, AWS documents the `nitro-tpm-attest` utility.
Run it inside a NitroTPM-enabled EC2 instance and save the CBOR/COSE
attestation document. Then rerun:

```bash
PYTHONNOUSERSITE=1 .venv/bin/python scripts/harvest_dio_aws_tee_attestation.py \
  --region af-south-1 \
  --instance-id i-... \
  --raw-attestation-document-file /path/to/aws-nitro-attestation.cbor \
  --out evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-attested-001
```

For Nitro Enclaves, collect the attestation document from the enclave through
the Nitro Secure Module API and pass the raw document with the same
`--raw-attestation-document-file` flag.

## Full document verification

The AWS Nitro document verifier performs the publication-grade cryptographic
checks before DIO admission:

- decode CBOR / COSE_Sign1;
- verify the AWS Nitro root fingerprint;
- verify the x509 chain;
- verify the ES384 COSE signature;
- verify nonce, user data, instance/module identity and PCR policy.

Example:

```bash
PYTHONNOUSERSITE=1 .venv/bin/python scripts/verify_dio_aws_nitro_attestation_document.py \
  evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008/nitro-tpm-attestation-document.cbor \
  --root-zip evidence/dai-diode/phase2.1-cloud-witness/aws-root/AWS_NitroEnclaves_Root-G1.zip \
  --expected-nonce-hex f009eb759d468a426a8365846840e72c9104b9781a558fca70f7c44c4ab78ff8 \
  --expected-user-data-file evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008/user-data.json \
  --expected-instance-id i-0b71289635c195cd0 \
  --expected-pcr-file evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008/nitro-tpm-pcr-policy-live-008.json
```

The harvester can require this verifier inline:

```bash
PYTHONNOUSERSITE=1 .venv/bin/python scripts/harvest_dio_aws_tee_attestation.py \
  --region af-south-1 \
  --instance-id i-0b71289635c195cd0 \
  --challenge-nonce f009eb759d468a426a8365846840e72c9104b9781a558fca70f7c44c4ab78ff8 \
  --raw-attestation-document-file evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008/nitro-tpm-attestation-document.cbor \
  --verify-nitro-document \
  --nitro-root-zip evidence/dai-diode/phase2.1-cloud-witness/aws-root/AWS_NitroEnclaves_Root-G1.zip \
  --expected-user-data-file evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008/user-data.json \
  --expected-pcr-file evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008/nitro-tpm-pcr-policy-live-008.json \
  --out evidence/dai-diode/phase2.1-cloud-witness/aws-af-south-1-live-008
```

## Boundary

`scripts/harvest_dio_aws_tee_attestation.py` normalizes and digest-binds raw AWS
Nitro attestation material. When `--verify-nitro-document` is supplied, green
harvest also means the AWS Nitro COSE signature, x509 chain, nonce/user-data
binding and configured PCR policy passed. DIO still keeps
`production_authority_allowed = false` until the broader quorum policy grants
production authority.
