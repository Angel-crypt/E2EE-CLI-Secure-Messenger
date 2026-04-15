import pytest
from datetime import datetime, timezone

from app.protocol import ProtocolValidationError, validate_message


def _register_message() -> dict:
    now_iso = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return {
        "message_id": "f8215ae4-a9d5-4434-ae54-3cc676db7ce0",
        "timestamp": now_iso,
        "type": "REGISTER",
        "from": "alice",
        "payload": {
            "username": "alice",
            "public_key": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...",
        },
    }


def _handshake_message() -> dict:
    now_iso = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return {
        "message_id": "15ceec6f-6f45-45f2-a2b8-17f40f53c295",
        "timestamp": now_iso,
        "type": "HANDSHAKE_INIT",
        "from": "alice",
        "to": "bob",
        "payload": {
            "username": "alice",
            "public_key": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...",
            "nonce": "YjRjNDY2ZjQwYw",
            "reason": "ON_DEMAND",
        },
    }


def _message_message() -> dict:
    now_iso = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return {
        "message_id": "4c0e20a4-4a69-40a3-a3e2-25bf1f2b40f8",
        "timestamp": now_iso,
        "type": "MESSAGE",
        "from": "alice",
        "to": "bob",
        "payload": {
            "ciphertext": "gAAAAABo...",
            "encoding": "base64url",
            "algorithm": "FERNET",
            "nonce": "YjRjNDY2ZjQwYw",
            "sent_at": now_iso,
        },
    }


def _error_message() -> dict:
    now_iso = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return {
        "message_id": "8f3967ea-f08f-448f-8fec-9b53bb8e8a43",
        "timestamp": now_iso,
        "type": "ERROR",
        "from": "server",
        "payload": {
            "code": "404_USER_OFFLINE",
            "message": "El usuario bob no esta disponible",
            "details": {"target": "bob"},
            "retriable": True,
        },
    }


@pytest.mark.unit
def test_register_without_to_is_valid():
    msg = _register_message()
    validated = validate_message(msg)
    assert "to" not in validated


@pytest.mark.unit
def test_handshake_init_without_to_is_invalid():
    msg = _handshake_message()
    del msg["to"]

    with pytest.raises(ProtocolValidationError) as exc_info:
        validate_message(msg)

    assert exc_info.value.code == "400_MISSING_FIELD"


@pytest.mark.unit
def test_message_without_to_is_invalid():
    msg = _message_message()
    del msg["to"]

    with pytest.raises(ProtocolValidationError) as exc_info:
        validate_message(msg)

    assert exc_info.value.code == "400_MISSING_FIELD"


@pytest.mark.unit
def test_error_without_to_is_valid():
    msg = _error_message()
    validated = validate_message(msg)
    assert validated["type"] == "ERROR"
