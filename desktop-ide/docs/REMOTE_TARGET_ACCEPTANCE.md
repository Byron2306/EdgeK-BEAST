# Remote target acceptance

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
same declarative extension host for local, SSH, and container targets.
