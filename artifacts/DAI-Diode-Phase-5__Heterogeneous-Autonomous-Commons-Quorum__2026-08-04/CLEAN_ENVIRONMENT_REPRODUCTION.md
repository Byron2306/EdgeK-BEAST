# Clean reproduction

One-command path:

```bash
./reproduce_clean_environment.sh /path/to/clean/EdgeK-BEAST
```

The script verifies this fossil, installs a non-destructive source overlay into
a clean checkout, copies the bundled evidence, and reruns the offline Azure MAA
verifier plus shared quorum replay verifier paths. It does not perform network
installs and it does not mutate cloud resources.
