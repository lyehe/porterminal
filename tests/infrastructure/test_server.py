"""Server process launch contract tests."""

from porterminal.infrastructure import server


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return b'{"status":"healthy","sessions":0}'


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


def test_wait_for_server_checks_the_protected_health_url(monkeypatch):
    requested: list[str] = []

    def urlopen(url, **_kwargs):
        requested.append(url)
        return _Response()

    monkeypatch.setattr(server.urllib.request, "urlopen", urlopen)

    assert server.wait_for_server(
        "127.0.0.1",
        8123,
        timeout=1,
        access_path="/AccessCode_1234567890",
    )
    assert requested == ["http://127.0.0.1:8123/AccessCode_1234567890/health"]
