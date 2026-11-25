from app.kernel.deployment import deployment as dep


def _manager():
    cls = next(v for v in vars(dep).values()
               if isinstance(v, type) and hasattr(v, "_litellm_executable") and hasattr(v, "start_litellm_sidecar"))
    return cls.__new__(cls)


def test_beast_litellm_bin_override(monkeypatch):
    monkeypatch.setenv("BEAST_LITELLM_BIN", "/opt/x/bin/litellm")
    assert _manager()._litellm_executable() == "/opt/x/bin/litellm"


def test_missing_litellm_reports_unavailable_instead_of_crashing(monkeypatch, tmp_path):
    monkeypatch.setenv("BEAST_LITELLM_BIN", str(tmp_path / "nope" / "litellm"))
    m = _manager()
    monkeypatch.setattr(m, "litellm_sidecar_status", lambda **kw: {"running": False, "pid": None}, raising=False)
    cfg = tmp_path / "litellm.config.yaml"
    cfg.write_text("model_list: []\n")
    out = m.start_litellm_sidecar(config_path=cfg, pid_file=tmp_path / "litellm.pid", port=4999,
                                  dry_run=False, approved=True)
    assert out["status"] == "unavailable" and "BEAST_LITELLM_BIN" in out["reason"]
    assert not (tmp_path / "litellm.pid").exists()
