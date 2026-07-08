from pathlib import Path

from app.kernel.local.local_config import DEFAULT_ENV_PATH


def test_local_config_reads_repo_beast_env():
    repo_root = Path(__file__).resolve().parents[1]

    assert DEFAULT_ENV_PATH == repo_root / ".beast" / "beast.env"
