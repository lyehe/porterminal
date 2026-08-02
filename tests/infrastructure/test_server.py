"""Server process launch contract tests."""

from porterminal.infrastructure import server


def test_start_server_uses_environment_aware_asgi_factory(monkeypatch):
    captured: dict = {}
    sentinel = object()

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(server.subprocess, "Popen", fake_popen)

    process = server.start_server("127.0.0.1", 8123)

    assert process is sentinel
    assert captured["command"][:6] == [
        server.sys.executable,
        "-m",
        "uvicorn",
        "porterminal.asgi:create_app_from_env",
        "--factory",
        "--host",
    ]
    assert "porterminal.app:app" not in captured["command"]
    assert "--no-proxy-headers" in captured["command"]
    assert captured["kwargs"]["stdout"] is server.subprocess.PIPE
