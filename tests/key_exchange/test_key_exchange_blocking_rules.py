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
def test_message_blocked_while_handshake_establishing(service: KeyExchangeService):
    service.start_handshake("alice", "bob", now_seconds=0)

    ok, error = service.can_send_message("alice", "bob", now_seconds=1)

    assert ok is False
    assert error is not None
    _assert_error_code(error, "403_SECURE_CHANNEL_REQUIRED", "alice")


@pytest.mark.unit
def test_secure_channel_required_without_active_channel(service: KeyExchangeService):
    ok, error = service.can_send_message("alice", "bob", now_seconds=0)

    assert ok is False
    assert error is not None
    _assert_error_code(error, "403_SECURE_CHANNEL_REQUIRED", "alice")
