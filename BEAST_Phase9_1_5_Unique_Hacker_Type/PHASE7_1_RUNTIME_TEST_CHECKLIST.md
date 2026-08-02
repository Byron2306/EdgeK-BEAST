# Phase 7.1 Runtime Test Checklist

1. Launch the renderer with cache disabled once, or fully restart Electron.
2. Visit every sidebar route at 100% zoom.
3. Confirm command chips remain compact and text-first.
4. Confirm Review gates, Memory rows, Map nodes and file rows retain their intended grid alignment.
5. Trigger buttons that receive automatic icons, including Refresh, Scan, Assign Agent, Verify, Export and Run.
6. Confirm no action icon exceeds 28px unless it belongs to an explicitly designed component slot.
7. Resize to 1366×768 and confirm there is no document-level horizontal scrollbar.
8. Run in DevTools:

```js
BeastIconCoverage.audit()
```

Expected result: only intentionally large named hero emblems may be returned. No `.beast-auto-icon` should appear in the result.
