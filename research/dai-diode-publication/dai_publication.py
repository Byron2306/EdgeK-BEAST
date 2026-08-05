#!/usr/bin/env python3
"""Hardened public entry point for the DAI-Diode publication harness.

The implementation remains in ``dai_publication_core`` so the first audited
commit is preserved byte-for-byte. This shim applies a compatibility correction
for ZIP tools that store POSIX permission bits without POSIX file-type bits.
Such entries are ordinary files, not special devices. Explicit symlink and
special-file type bits remain fail-closed.
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
main = _core.main


if __name__ == "__main__":
    raise SystemExit(main())
