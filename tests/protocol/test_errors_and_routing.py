import pytest

from app.protocol import ProtocolValidationError, make_error, validate_message


@pytest.mark.unit
def test_message_to_offline_user_returns_404_user_offline():
    err = make_error(
        code="404_USER_OFFLINE",
        message="El usuario bob no esta disponible",
        to="alice",
        details={"target": "bob"},
        retriable=True,
    )

    validated = validate_message(err)
    assert validated["type"] == "ERROR"
    assert validated["payload"]["code"] == "404_USER_OFFLINE"


@pytest.mark.unit
def test_duplicate_username_returns_409_username_taken():
    err = make_error(
        code="409_USERNAME_TAKEN",
        message="El username ya esta en uso",
        to="alice",
        details={"username": "alice"},
        retriable=False,
    )

    validated = validate_message(err)
    assert validated["payload"]["code"] == "409_USERNAME_TAKEN"


@pytest.mark.unit
def test_error_response_is_structured():
    err = make_error(
        code="400_INVALID_PAYLOAD",
        message="Payload invalido",
        details={"field": "payload.reason"},
        retriable=False,
    )

    assert err["type"] == "ERROR"
    assert "payload" in err
    assert set(err["payload"].keys()) == {"code", "message", "details", "retriable"}


@pytest.mark.unit
def test_make_error_with_unknown_code_is_rejected_by_validator():
    err = make_error(
        code="499_UNKNOWN",
        message="Codigo no soportado",
        retriable=False,
    )

    with pytest.raises(ProtocolValidationError) as exc_info:
        validate_message(err)

    assert exc_info.value.code == "400_INVALID_PAYLOAD"
