import pytest

from app.services.key_exchange_service import KeyExchangeService


@pytest.fixture
def service() -> KeyExchangeService:
    return KeyExchangeService(timeout_seconds=5)


@pytest.mark.unit
def test_reconnect_invalidates_existing_channel(service: KeyExchangeService):
    service.activate_secure_channel("alice", "bob", key=b"k", fp="fp-1", now=1)

    assert service.channel_state("alice", "bob") == "ACTIVE"

    service.invalidate_user_channels("alice", now_seconds=2)

    assert service.channel_state("alice", "bob") == "INVALID"


@pytest.mark.unit
def test_retry_handshake_after_timeout_is_allowed(service: KeyExchangeService):
    service.start_handshake("alice", "bob", now_seconds=0)
    service.invalidate_user_channels("alice", now_seconds=6)

    assert service.channel_state("alice", "bob") == "INVALID"

    ok, error = service.start_handshake("alice", "bob", now_seconds=7)

    assert ok is True
    assert error is None
    assert service.channel_state("alice", "bob") == "ESTABLISHING"


@pytest.mark.unit
def test_secure_channel_required_after_invalidation(service: KeyExchangeService):
    service.activate_secure_channel("alice", "bob", key=b"k", fp="fp-1", now=1)
    service.invalidate_user_channels("alice", now_seconds=2)

    assert service.channel_state("alice", "bob") == "INVALID"
