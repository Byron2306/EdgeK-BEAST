#!/usr/bin/env python3
"""Hardened public entry point for the DAI-Diode publication harness.

The implementation remains in ``dai_publication_core`` so the first audited
commit is preserved byte-for-byte. This shim applies compatibility and final-
evidence hardening without mutating that historical core.
"""

from __future__ import annotations

import stat
import zipfile

import dai_publication_core as _core
from dai_publication_core import *  # noqa: F401,F403


def _zip_entry_is_special_compat(info: zipfile.ZipInfo) -> bool:
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    if not unix_mode:
        return False
    file_type = stat.S_IFMT(unix_mode)
    if file_type == 0:
        return False
    return file_type not in {stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}


_core._zip_entry_is_special = _zip_entry_is_special_compat

# Imported only after the core compatibility gate is installed.
import dai_evidence as _evidence  # noqa: E402

_original_validate_candidate = _core.validate_candidate


def _validate_candidate_entry(candidate, *, stage):
    # The hardened validator reuses the original RC checks. Temporarily expose
    # the original function to avoid recursive dispatch through this shim.
    current = _core.validate_candidate
    _core.validate_candidate = _original_validate_candidate
    try:
        return _evidence.validate_candidate_hardened(candidate, stage=stage)
    finally:
        _core.validate_candidate = current


_core.validate_candidate = _validate_candidate_entry
validate_candidate = _validate_candidate_entry
main = _core.main


if __name__ == "__main__":
    raise SystemExit(main())
