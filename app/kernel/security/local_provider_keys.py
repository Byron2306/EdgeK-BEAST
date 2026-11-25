"""Host-local provider credentials shared by all BEAST worktrees.

The store is owner-only plaintext on disk. The CLI never evaluates shell
assignments, displays keys, or asks for a key when launching a saved experiment.
"""

from __future__ import annotations

import argparse
import errno
import getpass
import os
from pathlib import Path
import stat
import tempfile
import warnings

from app.kernel.security.secret_vault import PROVIDER_ENV

MAX_KEY_BYTES = 8192


class KeyStoreError(ValueError):
    """Safe to show to an operator without including any key material."""


def _root(root: Path | None) -> Path:
    if root is not None:
        return root
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config").expanduser()
    if not config.is_absolute():
        config = Path.home() / ".config"
    return config / "beast" / "keys"


def _key_path(provider: str, root: Path | None) -> Path:
    if provider not in PROVIDER_ENV:
        raise KeyStoreError("Unknown BEAST provider")
    return _root(root) / provider


def _check_private(info: os.stat_result, *, directory: bool) -> None:
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise KeyStoreError("Credential data must belong to this user and be private (directory 0700, key 0600)")


def _encode(value: str) -> bytes:
    if not value or len(value) > MAX_KEY_BYTES or not value.isascii() or any(
        not 33 <= ord(char) <= 126 for char in value
    ):
        raise KeyStoreError("Enter one nonempty credential with no whitespace or control characters")
    return value.encode("ascii")


def load_key(provider: str, *, root: Path | None = None) -> str | None:
    path = _key_path(provider, root)
    try:
        _check_private(path.parent.lstat(), directory=True)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise KeyStoreError("Refusing a symlink credential file") from None
        raise KeyStoreError("Unable to open the local credential store") from None
    with os.fdopen(fd, "rb") as stream:
        _check_private(os.fstat(stream.fileno()), directory=False)
        raw = stream.read(MAX_KEY_BYTES + 1)
    try:
        value = raw.decode("ascii")
    except UnicodeError:
        raise KeyStoreError("Stored credential has invalid format") from None
    _encode(value)
    return value


def save_key(provider: str, value: str, *, root: Path | None = None) -> None:
    raw = _encode(value)
    path = _key_path(provider, root)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _check_private(path.parent.lstat(), directory=True)
    fd, temporary = tempfile.mkstemp(prefix=".new-key-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="operation", required=True)
    for operation in ("set", "status", "run"):
        command = subs.add_parser(operation)
        command.add_argument("provider", choices=sorted(PROVIDER_ENV))
        if operation == "run":
            command.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    try:
        if args.operation == "set":
            # Fail closed if getpass cannot disable terminal echo.
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                value = getpass.getpass(f"Enter replacement key for {args.provider}: ")
            save_key(args.provider, value)
            print(f"{args.provider}: saved")
            return 0

        value = load_key(args.provider)
        if args.operation == "status":
            print(f"{args.provider}: {'saved' if value else 'not configured'}")
            return 0 if value else 1
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not command:
            parser.error("run requires a command")
        if not value:
            raise KeyStoreError(f"No saved key for {args.provider}. Run set {args.provider} once.")
        env = dict(os.environ)
        env[PROVIDER_ENV[args.provider]] = value
        os.execvpe(command[0], command, env)
    except (KeyStoreError, OSError, EOFError, getpass.GetPassWarning) as exc:
        message = str(exc) if isinstance(exc, KeyStoreError) else "Credential operation could not complete"
        parser.exit(1, f"{message}\n")
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
