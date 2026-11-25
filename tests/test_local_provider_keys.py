import os
from pathlib import Path
import stat
import tempfile
import unittest

from app.kernel.security.local_provider_keys import KeyStoreError, load_key, save_key


class LocalProviderKeyTests(unittest.TestCase):
    def test_set_and_rotate_in_private_store(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Path(temp) / "keys"
            self.assertIsNone(load_key("nvidia_nim", root=store))
            save_key("nvidia_nim", "placeholder-first", root=store)
            save_key("fireworks", "placeholder-other", root=store)
            save_key("nvidia_nim", "placeholder-second", root=store)
            self.assertEqual(load_key("nvidia_nim", root=store), "placeholder-second")
            self.assertEqual(load_key("fireworks", root=store), "placeholder-other")
            self.assertEqual(stat.S_IMODE(store.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((store / "nvidia_nim").stat().st_mode), 0o600)

    def test_rejects_shared_or_symlink_key(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Path(temp)
            save_key("nvidia_nim", "placeholder", root=store)
            key = store / "nvidia_nim"
            os.chmod(key, 0o644)
            with self.assertRaises(KeyStoreError):
                load_key("nvidia_nim", root=store)
            key.rename(store / "target")
            key.symlink_to("target")
            with self.assertRaises(KeyStoreError):
                load_key("nvidia_nim", root=store)
