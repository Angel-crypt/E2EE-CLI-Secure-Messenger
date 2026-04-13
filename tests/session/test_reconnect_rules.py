import pytest

from app.protocol import validate_message
from app.services.user_service import SessionUserService


@pytest.fixture
def service() -> SessionUserService:
    return SessionUserService()


def _assert_structured_error(
    error_message: dict, expected_code: str, expected_to: str
) -> None:
    validated = validate_message(error_message)
    assert validated["type"] == "ERROR"
    assert validated.get("to") == expected_to
    assert validated["payload"]["code"] == expected_code


@pytest.mark.unit
def test_reconnect_requires_previous_session_closed(service: SessionUserService):
    service.register("alice")

    ok_while_active, err_active = service.register("alice")
    assert ok_while_active is False
    _assert_structured_error(err_active, "409_USERNAME_TAKEN", "alice")

    service.disconnect("alice")

    ok_after_close, err_after_close = service.register("alice")
    assert ok_after_close is True
    assert err_after_close is None


@pytest.mark.unit
def test_reconnect_invalidates_previous_channels(service: SessionUserService):
    service.register("alice")
    service.register("bob")
    service.mark_secure_channel("alice", "bob")

    can_send_before, _ = service.can_send_message("alice", "bob")
    assert can_send_before is True

    service.disconnect("alice")
    service.register("alice")

    can_send_after, err_after = service.can_send_message("alice", "bob")
    assert can_send_after is False
    _assert_structured_error(err_after, "403_SECURE_CHANNEL_REQUIRED", "alice")


@pytest.mark.unit
def test_message_after_reconnect_requires_new_handshake_init(
    service: SessionUserService,
):
    service.register("alice")
    service.register("bob")
    service.mark_secure_channel("alice", "bob")

    service.disconnect("alice")
    service.register("alice")

    can_send, err = service.can_send_message("alice", "bob")
    assert can_send is False
    _assert_structured_error(err, "403_SECURE_CHANNEL_REQUIRED", "alice")
