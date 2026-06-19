from app.kernel.secret_vault import SecretVault


def test_secret_vault_imports_redacted_provider_env(tmp_path, monkeypatch):
    source = tmp_path / "Secrets.txt"
    source.write_text(
        "OPENAI_API_KEY=sk-test-redacted-value\n"
        "GROQ_API_KEY=gsk_test_redacted_value\n"
        "bare-unknown-token-value\n",
        encoding="utf-8",
    )
    vault = SecretVault(str(tmp_path / ".beast" / "provider_secrets.env"))

    result = vault.import_file(str(source), overwrite=True, load=True)

    assert result["mode"] == "0o600"
    assert result["providers"]["openai"] == 1
    assert result["providers"]["groq"] == 1
    assert result["providers"]["unknown"] == 1
    assert "value" not in result["entries"][0]
    assert result["entries"][0]["fingerprint"]
    assert vault.vault_path.read_text(encoding="utf-8").count("sk-test-redacted-value") == 1

    status = vault.status()
    assert any(item["env_name"] == "OPENAI_API_KEY" for item in status["entries"])
    assert all("value" not in item for item in status["entries"])


def test_secret_vault_load_respects_existing_environment(tmp_path, monkeypatch):
    vault_path = tmp_path / "provider_secrets.env"
    vault_path.write_text('OPENAI_API_KEY="from_vault"\n', encoding="utf-8")
    vault = SecretVault(str(vault_path))
    monkeypatch.setenv("OPENAI_API_KEY", "already_set")

    result = vault.load(override=False)

    assert result["loaded"] == 0
    assert result["skipped_existing"] == 1
    assert result["entries"][0]["env_name"] == "OPENAI_API_KEY"


def test_secret_vault_splits_ovhcloud_compound_line(tmp_path):
    source = tmp_path / "Secrets.txt"
    source.write_text(
        "OVHCLOUD APP KEY - app_key_value,  APP SECRET - app_secret_value,   CONSUMER KEY - consumer_key_value\n",
        encoding="utf-8",
    )
    vault = SecretVault(str(tmp_path / ".beast" / "provider_secrets.env"))

    result = vault.import_file(str(source), overwrite=True, load=False)
    env_names = {entry["env_name"] for entry in result["entries"]}

    assert env_names == {"OVHCLOUD_APP_KEY", "OVHCLOUD_APP_SECRET", "OVHCLOUD_CONSUMER_KEY"}
