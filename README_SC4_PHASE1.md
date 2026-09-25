# SC4 Phase 1 attachment

This phase does not execute SC4.

Run:

```bash
/srv/dio/presence/.venv/bin/python -m pytest \
  tests/test_sc4_live_attachment_registry.py \
  -q -s

/srv/dio/presence/.venv/bin/python \
  scripts/proof/sc4_live_attachment_registry.py
```

Expected status: `SC4_PHASE1_ATTACHMENT_READY`.

No provider call is made by this phase.
