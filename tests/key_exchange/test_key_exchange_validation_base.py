import pytest

from app.services.key_exchange_service import KeyExchangeService


@pytest.fixture
def service() -> KeyExchangeService:
    return KeyExchangeService(timeout_seconds=5)


@pytest.mark.unit
def test_start_handshake_when_channel_missing(service: KeyExchangeService):
    assert service.channel_state("alice", "bob") == "NONE"

    ok, error = service.start_handshake("alice", "bob", now_seconds=0)

    assert ok is True
    assert error is None
    assert service.channel_state("alice", "bob") == "ESTABLISHING"
