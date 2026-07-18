# Remote Commons Space Node

BEAST now has a separately deployable Commons node that behaves like a small,
governed Hugging Face Hub: owners create buckets, upload immutable SHA-256
blobs, and commit named revisions whose manifests bind file paths, sizes and
digests. The node signs every revision receipt. Remote content never receives
execution authority; it remains a `remote_hypothesis` with `verify_only`
maximum authority until BEAST reproduces it locally.

## Trust boundaries

| Boundary | Enforcement |
|---|---|
| Desktop to BEAST | Existing loopback Electron gateway and workspace identity boundary |
| BEAST to node | Registered origin only, HTTPS outside loopback, Gate-of-Night host allowlist |
| Client request | Ed25519 signature over method, exact target, body digest, timestamp, nonce and monotonic counter |
| Replay state | Durable SQLite one-use nonce/counter transaction with a bounded concurrency reordering window |
| Discovery | Source-neutral signed envelope; HTTP well-known, static seeds, DNS-SD, peer exchange, registries and offline bootstrap are adapters, not trust |
| Native trust root | Crystal-compute lattice attestation over the exact node/workload/key/protocol/capability/authority subject |
| Endpoint possession | Fresh nonce challenge signed by the discovered node key before automatic registration |
| Hardware identity | Optional additive ARDA/TPM appraisal over the same exact subject |
| Stored bytes | Immutable `sha256:` blobs and manifest custody verification on read |
| Portable result | Node-signed revision receipt with `verify_only` authority |

The crystal-compute lattice is the Commons trust root. The verifier pins the
delegated lattice authority, policy generation, exact accepted lattice head,
and minimum checkpoint count; a merely hash-shaped claim is not accepted.
ARDA/TPM may strengthen this with substrate assurance, but is not required by
the normal `lattice` policy. The legacy caller-asserted TPM path remains
excluded. When ARDA is selected, its `request_digest` must equal the node
descriptor's `attestation_subject_digest`.

Discovery and admission are intentionally different states. An envelope may
be `observed_untrusted` or a `trusted_candidate`; automatic registration only
occurs after both lattice verification and a live endpoint-key challenge.
Discovery never silently replaces an existing node endpoint or key.

## Provision and start the local three-node lab

Provisioning has already been materialized under
`.beast/remote-commons-lab` in this workspace. To provision a fresh lab later:

```bash
python3 scripts/provision_remote_commons_lab.py \
  --root .beast/remote-commons-lab \
  --nodes 3 \
  --base-port 8111
```

The command creates one BEAST client identity, a unique identity for every
node, node-local public-key trust stores, and registration documents. It
refuses to overwrite existing private keys.

Delegate the verified local lattice head to those node subjects and emit the
lab trust store/evidence:

```bash
python3 scripts/attest_remote_commons_lab.py \
  --root .beast/remote-commons-lab \
  --lattice-root benchmarks/results/crystal_lattice_ledger
```

Start the nodes:

```bash
docker compose -f docker-compose.commons-lab.yml up --build -d
curl -sS http://127.0.0.1:8111/health
```

Discover all three static seed origins, verify their lattice evidence and live
nonce proofs, seed `edgek/verified-crystals`, verify its signed `bootstrap-v1`
revision, and import it into BEAST's local quarantine:

```bash
python3 scripts/bootstrap_remote_commons_lab.py \
  --root .beast/remote-commons-lab \
  --state-root .beast
```

The bootstrap also writes `.beast/commons-remote/client-config.json`, which
lets the next BEAST gateway start load the provisioned local client identity
without exposing that key to the desktop renderer.

Load the generated control-plane settings before starting the BEAST gateway:

```bash
set -a
. .beast/remote-commons-lab/gateway.env
set +a
bin/beast gateway
```

The lab uses `trust_policy=lattice`, so all three nodes reach
`lattice_attested` without pretending a container has host-hardware identity.
For deployments that need additive substrate assurance, choose `arda`,
`lattice_or_arda`, or `lattice_and_arda` and provision the ARDA verification
key/appraisal separately.

## Register and use a node

Open **Commons Forge** in the desktop IDE and use **Agnostic Discovery** with
one or more explicit origins. The IDE shows candidate provenance, lattice
authority/head, admission state, and optional ARDA substrate assurance. Manual
pinning remains an explicit fallback. Then:

1. Discovery verifies the node descriptor, lattice subject binding, pinned
   lattice head, and a fresh endpoint-key nonce proof before registration.
2. Select **Probe Identity** to refresh evidence and the short admission cache.
3. Select **Browse Buckets**. BEAST makes the request; the renderer never gets
   the client private key and never connects to the remote origin directly.
4. Create a bucket on the selected admitted node.

The control-plane API is also available at:

- `GET /edgek/control-plane/commons/remote`
- `POST /edgek/control-plane/commons/remote/nodes`
- `GET|POST /edgek/control-plane/commons/remote/discovery`
- `POST /edgek/control-plane/commons/remote/nodes/{node_id}/probe`
- `GET|POST /edgek/control-plane/commons/remote/nodes/{node_id}/buckets`
- `POST /edgek/control-plane/commons/remote/nodes/{node_id}/blobs`
- `PUT /edgek/control-plane/commons/remote/nodes/{node_id}/buckets/{owner}/{name}/revisions/{revision}`

All mutating management routes are restricted to the local BEAST operator
boundary. The small desktop blob bridge accepts base64 payloads up to 3 MiB;
larger artifacts should use a signed streaming client against the node's raw
`PUT /v1/blobs/{sha256:digest}` endpoint.

## Production deployment requirements

- Terminate TLS at the node and register only its HTTPS origin.
- Set `BEAST_COMMONS_REMOTE_ALLOWED_HOSTS` on BEAST to an explicit hostname
  allowlist.
- Mount `BEAST_COMMONS_NODE_SIGNING_KEY` and
  `BEAST_COMMONS_CLIENT_TRUST_STORE` read-only.
- Use unique client/node keys per environment; never reuse the lab identities.
- Pin the lattice authority, accepted head(s), checkpoint floor and policy
  generation in `BEAST_COMMONS_LATTICE_TRUST_STORE`; rotate deliberately.
- Keep evidence short-lived and renew after lattice advancement. If hardware
  identity matters, add an ARDA appraisal with matching subject and expiry.
- Place blob storage and SQLite metadata on durable encrypted storage and back
  them up together.
- Run local held-out reproduction before any artifact promotion. A valid
  remote signature proves custody and identity, not correctness.
