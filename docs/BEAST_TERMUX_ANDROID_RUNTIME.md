# BEAST on native Termux / Android

BEAST treats Android/Termux as a first-class local coding backend target.

## Runtime split

Native Termux owns the BEAST backend:

- gateway / AgentRun runtime;
- embedded provider/proxy and MCP gateway routes;
- MCP HTTP server;
- local Ollama;
- BEAST CLI and Textual TUI;
- durable evidence and worktree state.

The full Electron shell runs in Debian proot under Termux:X11 and attaches to
the native gateway over loopback. This is deliberate: normal Linux Electron
binaries target glibc, while native Termux uses Android/Bionic.

## Install the native CLI and backend

From the repository:

```bash
git switch agent/beast-phase4-termux-runtime
git pull --ff-only
chmod +x scripts/termux/*.sh
scripts/termux/install_native_runtime.sh
```

After that:

```bash
beast termux-status
beast ui
```

The Android-native profile requires these services:

```text
gateway
embedded proxy route
embedded MCP gateway route
provider state
desktop compatibility contract
MCP HTTP
Ollama
```

LiteLLM and nginx are optional in the Android profile because the coding
backend and desktop contract do not require them.

To request them explicitly:

```bash
beast termux-up --with-litellm true --with-nginx true
```

## Phase 4 Android gauntlet

With `qwen2.5:0.5b` already available in Ollama:

```bash
scripts/termux/run_phase4_android_gauntlet.sh
```

The gauntlet covers the hosted Phase 4 closure matrix plus Android-specific
desktop renderer ingress, real local Ollama exchange and planner endurance.
It writes JSON, Markdown and JUnit receipts below:

```text
benchmarks/results/beast_phase4_termux_android/<UTC timestamp>/
```

## Desktop IDE

Termux:X11 requires both its Android app and its companion Termux package.
Prepare the Debian Electron runtime:

```bash
scripts/termux/setup_desktop_debian.sh
```

Then start the X server and BEAST desktop shell:

```bash
scripts/termux/launch_desktop_ide.sh
```

The Debian shell uses a separate Electron runtime under
`/root/EdgeK-BEAST-desktop`, while the active workspace remains the native
Termux repository. It connects to:

```text
http://127.0.0.1:8101
```

No second BEAST backend is started in Debian.

## Manual service commands

```bash
beast termux-up
beast termux-status
beast termux-down
```

Logs and PID files remain under `deploy/run/`.
