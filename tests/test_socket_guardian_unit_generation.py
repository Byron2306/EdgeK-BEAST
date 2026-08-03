from pathlib import Path

from scripts.generate_socket_guardian_units import generate


def test_guardian_units_are_generated_only_for_explicitly_managed_services(tmp_path: Path):
    registry = tmp_path / "services.yaml"
    registry.write_text(
        "services:\n"
        "  reverse_proxy: {port: 80}\n"
        "  beast: {hostname: beast.test, upstream: 127.0.0.1:8101, port: 8101, socket_guardian: true}\n"
        "  arda: {hostname: arda.test, upstream: 127.0.0.1:18401, port: 18401, socket_guardian: false}\n",
        encoding="utf-8",
    )
    config = tmp_path / "guardian.yaml"
    config.write_text("guardian: {}\n", encoding="utf-8")
    repository = tmp_path / "repo"
    (repository / "venv" / "bin").mkdir(parents=True)
    (repository / "venv" / "bin" / "python").touch()

    outputs = generate(registry, config, tmp_path / "units", repository)

    names = {path.name for path in outputs}
    service = (tmp_path / "units" / "beast-socket-guardian.service").read_text(encoding="utf-8")
    assert "beast-socket-guardian-beast.socket" in names
    assert "beast-socket-guardian-arda.socket" not in names
    assert "beast-socket-guardian-beast.socket" in service
    assert "beast-socket-guardian-arda.socket" not in service
