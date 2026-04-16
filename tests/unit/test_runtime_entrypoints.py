from __future__ import annotations

import pytest

import main as main_module


@pytest.mark.unit
def test_main_client_uses_relay_url_from_env(monkeypatch):
    monkeypatch.setenv("E2EE_RELAY_URL", "ws://env-relay:9999")
    captured: dict[str, object] = {}

    class FakeCliApp:
        def __init__(self, controller, relay_url=None, **kw):
            captured["relay_url"] = relay_url

        def run(self) -> None:
            pass

    monkeypatch.setattr("main.CliApp", FakeCliApp)
    main_module.main(["--client"])

    assert captured["relay_url"] == "ws://env-relay:9999"


@pytest.mark.unit
def test_main_client_is_default_when_no_flag(monkeypatch):
    monkeypatch.delenv("E2EE_RELAY_URL", raising=False)
    monkeypatch.setattr("main._load_dotenv", lambda *_: None)
    captured: dict[str, object] = {}

    class FakeCliApp:
        def __init__(self, controller, relay_url=None, **kw):
            captured["relay_url"] = relay_url

        def run(self) -> None:
            pass

    monkeypatch.setattr("main.CliApp", FakeCliApp)
    main_module.main([])

    assert captured["relay_url"] is None


@pytest.mark.unit
def test_main_server_reads_host_and_port_from_env(monkeypatch):
    monkeypatch.setenv("E2EE_RELAY_HOST", "0.0.0.0")
    monkeypatch.setenv("E2EE_RELAY_PORT", "9000")
    captured: dict[str, object] = {}

    async def fake_relay_main(host: str, port: int) -> None:
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("main._relay_main", fake_relay_main)
    main_module.main(["--server"])

    assert captured == {"host": "0.0.0.0", "port": 9000}


@pytest.mark.unit
def test_main_server_uses_defaults_when_env_absent(monkeypatch):
    monkeypatch.delenv("E2EE_RELAY_HOST", raising=False)
    monkeypatch.delenv("E2EE_RELAY_PORT", raising=False)
    captured: dict[str, object] = {}

    async def fake_relay_main(host: str, port: int) -> None:
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("main._relay_main", fake_relay_main)
    main_module.main(["--server"])

    assert captured == {"host": "127.0.0.1", "port": 8765}
