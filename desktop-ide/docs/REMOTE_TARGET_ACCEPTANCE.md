# Remote target acceptance

## Target-local workspace extensions

Workspace extensions installed through BEAST remain local until an operator chooses **Deploy to Active Target** in Compatibility → Extension Runtime. Deployment is explicit, bounded to each validated manifest and entrypoint, and atomically replaces only matching extension files under the active target's `.beast/extensions/<id>/` folder. It does not remove unrelated target extensions. Capability grants remain local operator policy and apply when the target host starts.

Before BEAST starts a remote extension host, it verifies that the selected SSH workspace exists and can run `node --version`; container hosts receive the same Node.js check through `docker exec`. Startup and exit diagnostics preserve bounded target stderr, so a missing runtime or rejected remote command is shown as an actionable error instead of a generic stream timeout.

## Published Dev Container ports

Container inspection reads Docker's published TCP bindings and presents only loopback URLs such as `http://127.0.0.1:<port>` in the Compatibility workbench. Opening a port is constrained to a numeric local port through desktop IPC; BEAST does not expose a container service publicly or accept an arbitrary URL from the renderer.

The desktop host now uses the same mediated stdio protocol for local, SSH, and
container LSP/DAP sessions. The acceptance harnesses deliberately skip live
remote checks unless an operator supplies a verified target.

Run the contract checks locally:

```bash
npm run smoke:targets
npm run smoke:remote-dap
```

For a real SSH DAP handshake, configure a known-host entry and a remote Python
environment containing `debugpy`:

```bash
BEAST_PARITY_SSH_HOST=devbox \
BEAST_PARITY_SSH_ROOT=/workspace/project \
BEAST_PARITY_SSH_DAP_ADAPTER=debugpy \
npm run smoke:remote-dap
```

For a running Dev Container with `debugpy` installed:

```bash
BEAST_PARITY_CONTAINER_ID=beast-dev-project \
BEAST_PARITY_CONTAINER_WORKSPACE=/workspace \
BEAST_PARITY_CONTAINER_DAP_ADAPTER=debugpy \
npm run smoke:remote-dap
```

The bundled extensions are BEAST-native and target-aware: Code Health,
Crystal Lab, Remote Toolkit, and Companion. They are sandboxed through the
same declarative extension host for local, SSH, and container targets. For
SSH and container execution the extension host now receives the target's
workspace root and target-local `.beast/extensions` directory; it never
receives a desktop filesystem path that would be meaningless or unsafe on the
target. Grants remain persisted by the local workspace owner.

## Dev Container modes

BEAST manages image, Dockerfile, and safe workspace-local `dockerComposeFile`
configurations. For Compose configurations, `service` is required and the
Compose file must resolve inside the opened workspace (for example,
`../docker-compose.yml` from `.devcontainer/devcontainer.json` is accepted
when it resolves to the workspace root). Inspect, start, attach, stop,
rebuild, logs, terminal execution, and the LSP/DAP target all use the selected
Compose container.

Compose feature/mount parity with the full VS Code Dev Containers specification
is still an acceptance target; use the runtime check below before relying on a
new configuration:

```bash
BEAST_PARITY_CONTAINER_IMAGE=alpine:3.20 npm run smoke:targets
```
