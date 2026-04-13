import pytest

from app.protocol import validate_message
from app.services.key_exchange_service import KeyExchangeService


@pytest.fixture
def service() -> KeyExchangeService:
    return KeyExchangeService(timeout_seconds=5)


def _assert_error_code(
    error_message: dict, expected_code: str, expected_to: str
) -> None:
    validated = validate_message(error_message)
    assert validated["type"] == "ERROR"
    assert validated.get("to") == expected_to
    assert validated["payload"]["code"] == expected_code


@pytest.mark.unit
def test_reconnect_invalidates_existing_channel(service: KeyExchangeService):
    service.start_handshake("alice", "bob", now_seconds=0)
    service.complete_handshake("alice", "bob", now_seconds=1)

    assert service.channel_state("alice", "bob") == "ACTIVE"

    service.invalidate_user_channels("alice", now_seconds=2)

    assert service.channel_state("alice", "bob") == "INVALID"


@pytest.mark.unit
def test_retry_handshake_after_timeout_is_allowed(service: KeyExchangeService):
    service.start_handshake("alice", "bob", now_seconds=0)
    service.check_timeout("alice", "bob", now_seconds=6)

    assert service.channel_state("alice", "bob") == "INVALID"

    ok, error = service.start_handshake("alice", "bob", now_seconds=7)

    assert ok is True
    assert error is None
    assert service.channel_state("alice", "bob") == "ESTABLISHING"


@pytest.mark.unit
def test_secure_channel_required_after_invalidation(service: KeyExchangeService):
    service.start_handshake("alice", "bob", now_seconds=0)
    service.complete_handshake("alice", "bob", now_seconds=1)
    service.invalidate_user_channels("alice", now_seconds=2)

    ok, error = service.can_send_message("alice", "bob", now_seconds=2)

    assert ok is False
    _assert_error_code(error, "403_SECURE_CHANNEL_REQUIRED", "alice")
