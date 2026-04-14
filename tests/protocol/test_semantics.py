import pytest
from datetime import datetime, timezone

from app.protocol import ProtocolValidationError, validate_message


@pytest.mark.unit
def test_register_payload_username_must_match_from():
    now_iso = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    msg = {
        "message_id": "f8215ae4-a9d5-4434-ae54-3cc676db7ce0",
        "timestamp": now_iso,
        "type": "REGISTER",
        "from": "alice",
        "payload": {
            "username": "charlie",
            "public_key": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...",
        },
    }

    with pytest.raises(ProtocolValidationError) as exc_info:
        validate_message(msg)

    assert exc_info.value.code == "400_INVALID_PAYLOAD"


@pytest.mark.unit
def test_handshake_init_payload_username_must_match_from():
    now_iso = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    msg = {
        "message_id": "15ceec6f-6f45-45f2-a2b8-17f40f53c295",
        "timestamp": now_iso,
        "type": "HANDSHAKE_INIT",
        "from": "alice",
        "to": "bob",
        "payload": {
            "username": "charlie",
            "public_key": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...",
            "nonce": "YjRjNDY2ZjQwYw",
            "reason": "ON_DEMAND",
        },
    }

    with pytest.raises(ProtocolValidationError) as exc_info:
        validate_message(msg)

    assert exc_info.value.code == "400_INVALID_PAYLOAD"


@pytest.mark.unit
def test_message_from_must_not_equal_to():
    now_iso = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    msg = {
        "message_id": "4c0e20a4-4a69-40a3-a3e2-25bf1f2b40f8",
        "timestamp": now_iso,
        "type": "MESSAGE",
        "from": "alice",
        "to": "alice",
        "payload": {
            "ciphertext": "gAAAAABo...",
            "encoding": "base64url",
            "algorithm": "FERNET",
        },
    }

    with pytest.raises(ProtocolValidationError) as exc_info:
        validate_message(msg)

    assert exc_info.value.code == "400_INVALID_TO"


@pytest.mark.unit
def test_error_to_if_present_must_be_valid_username():
    now_iso = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    msg = {
        "message_id": "8f3967ea-f08f-448f-8fec-9b53bb8e8a43",
        "timestamp": now_iso,
        "type": "ERROR",
        "from": "server",
        "to": "bad user",
        "payload": {
            "code": "404_USER_OFFLINE",
            "message": "El usuario destino no esta disponible",
            "details": {},
            "retriable": True,
        },
    }

    with pytest.raises(ProtocolValidationError) as exc_info:
        validate_message(msg)

    assert exc_info.value.code == "400_INVALID_TO"
