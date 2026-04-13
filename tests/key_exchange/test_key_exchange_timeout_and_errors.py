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
def test_handshake_timeout_returns_504_key_exchange_timeout(
    service: KeyExchangeService,
):
    service.start_handshake("alice", "bob", now_seconds=0)

    timed_out, timeout_error = service.check_timeout("alice", "bob", now_seconds=6)

    assert timed_out is True
    assert timeout_error is not None
    assert service.channel_state("alice", "bob") == "INVALID"
    _assert_error_code(timeout_error, "504_KEY_EXCHANGE_TIMEOUT", "alice")


@pytest.mark.unit
def test_key_exchange_errors_follow_error_schema(service: KeyExchangeService):
    service.start_handshake("alice", "bob", now_seconds=0)
    _, timeout_error = service.check_timeout("alice", "bob", now_seconds=6)

    validated = validate_message(timeout_error)
    assert validated["type"] == "ERROR"
    assert validated["payload"]["code"] == "504_KEY_EXCHANGE_TIMEOUT"
