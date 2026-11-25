# Skipped paths — three-leaf-gauntlet-20261125-a

These source paths were not copied into the tracked evidence tree.

| path | reason | bytes |
|---|---|---:|
| `trial-key.pem` | credential_file | 119 |
| `workspace/.beast/worktrees/three-leaf-reuse_bool-off-f232e091d91b-296d6eb6/` | worktree_copy_over_5mb | 14169236 |
| `workspace/.beast/worktrees/three-leaf-leaf_bool-c95f2945386b-4c765b38/` | worktree_copy_over_5mb | 9545630 |
| `workspace/.beast/worktrees/three-leaf-reuse_int-on-f252eeab7d18-301d048a/` | worktree_copy_over_5mb | 9827683 |
| `workspace/.beast/worktrees/three-leaf-reuse_bool-on-554f13b60da5-424bbaa1/` | worktree_copy_over_5mb | 15077540 |
| `workspace/.beast/worktrees/three-leaf-reuse_str-off-c881c87f1d6a-d62336dc/` | worktree_copy_over_5mb | 11464424 |
| `workspace/.beast/worktrees/three-leaf-reuse_str-on-c7a3060e2673-91f2f4dc/` | worktree_copy_over_5mb | 13277995 |
| `workspace/.beast/worktrees/three-leaf-leaf_int-6d1e1376125c-d7d1f7ed/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `workspace/.beast/worktrees/three-leaf-reuse_int-off-aa491807f37d-fc33bd71/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `workspace/.beast/worktrees/three-leaf-leaf_str-313533c5fb4f-401add43/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `workspace/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `nested-heldout/retries-prefix-anon-after-0/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `nested-heldout/window-status-open-after-1/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `nested-heldout/retries-prefix-anon-after-1/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `nested-heldout/ttl-label-guest-after-1/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `nested-heldout/window-status-open/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `nested-heldout/retries-prefix-anon/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `nested-heldout/ttl-label-guest-after-0/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `nested-heldout/window-status-open-after-0/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `nested-heldout/ttl-label-guest/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `triple-heldout/retries-prefix-anon-after-0/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `triple-heldout/window-status-open-after-1/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `triple-heldout/retries-prefix-anon-after-1/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `triple-heldout/ttl-label-guest-after-1/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `triple-heldout/window-status-open/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `triple-heldout/retries-prefix-anon/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `triple-heldout/ttl-label-guest-after-0/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `triple-heldout/window-status-open-after-0/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |
| `triple-heldout/ttl-label-guest/.beast/keys/residue/residue_ed25519.pem` | credential_file | 119 |

## Nested Git metadata

Each fixture/held-out `workspace` contained a private `.git` directory. Those were omitted from the tracked copy so Git records the files themselves instead of gitlinks/submodules. The run reports, lattice ledgers, and source trees remain.
