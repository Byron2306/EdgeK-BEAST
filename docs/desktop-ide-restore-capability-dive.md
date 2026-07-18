# Desktop IDE Restore Capability Dive

## Incident

Clicking the Tooling/Tools page could freeze the renderer and destabilize gateway probes. File loading could also appear blank after selecting a workspace when local enumeration failed or returned no rows.

## Confirmed Failure Modes

- Tooling page re-entry loop: entering the Tooling page triggered `refreshMcpOps()`, and `refreshMcpOps()` called `setDesktopPage('tooling')` again.
- Gateway readiness was too broad and expensive: `beast up` used the giant OpenAPI document as the first readiness source and did not require desktop IDE routes.
- File explorer fallback was brittle: renderer code assumed `window.beastDesktop` existed before checking `listFiles`, and an empty local result could leave the user with an unclear explorer state.

## Restore Changes

- Tooling entry is now single-flight, throttled, and no longer recursively re-enters the Tooling page.
- Tooling snapshot uses the desktop IPC snapshot first, with gateway as optional fallback.
- MCP operations fetch each gateway route independently and show partial results instead of failing the whole page.
- Renderer errors and unhandled promise rejections are contained and logged instead of taking down the whole shell.
- Workspace file loading uses guarded local IPC first and now shows a concrete empty/failure state.
- Gateway route readiness now includes critical desktop IDE routes:
  - `/edgek/workspace/files`
  - `/edgek/workspace/file`
  - `/edgek/ide/snapshot`
  - `/edgek/ide/actions/manifest`
  - `/edgek/ide/tooling-snapshot`
  - `/edgek/ide/system-snapshot`

## Verification

- `node -c desktop-ide/renderer/app.js`
- `node -c desktop-ide/main.js`
- `python3 -m pytest tests/test_desktop_ide_manifest.py -q`
- `npm run smoke --prefix desktop-ide`
- `npm run smoke:launch --prefix desktop-ide`

## Remaining Gateway Work

The foreground gateway can still be intermittent during immediate post-start probes. Next hardening step is to make Electron's gateway startup attach only after the desktop IDE route contract has passed, and to surface `deploy/run/gateway.log` directly in the Doctor page when readiness fails.
