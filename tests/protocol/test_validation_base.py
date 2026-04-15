import copy
from datetime import datetime, timezone

import pytest

from app.protocol import ProtocolValidationError, validate_message


def _base_message(message_type: str) -> dict:
    now_iso = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    msg = {
        "message_id": "f8215ae4-a9d5-4434-ae54-3cc676db7ce0",
        "timestamp": now_iso,
        "type": message_type,
        "from": "alice",
        "payload": {},
    }
    if message_type == "REGISTER":
        msg["payload"] = {
            "username": "alice",
            "public_key": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...",
        }
    elif message_type == "HANDSHAKE_INIT":
        msg["to"] = "bob"
        msg["payload"] = {
            "username": "alice",
            "public_key": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...",
            "nonce": "YjRjNDY2ZjQwYw",
            "reason": "ON_DEMAND",
        }
    elif message_type == "MESSAGE":
        msg["to"] = "bob"
        msg["payload"] = {
            "ciphertext": "gAAAAABo...",
            "encoding": "base64url",
            "algorithm": "FERNET",
            "nonce": "YjRjNDY2ZjQwYw",
            "sent_at": now_iso,
        }
    elif message_type == "ERROR":
        msg["from"] = "server"
        msg["payload"] = {
            "code": "404_USER_OFFLINE",
            "message": "El usuario bob no esta disponible",
            "details": {"target": "bob"},
            "retriable": True,
        }
    return msg


@pytest.mark.unit
def test_register_message_schema_valid():
    message = _base_message("REGISTER")
    validated = validate_message(message)
    assert validated["type"] == "REGISTER"


@pytest.mark.unit
def test_handshake_init_schema_valid():
    message = _base_message("HANDSHAKE_INIT")
    validated = validate_message(message)
    assert validated["type"] == "HANDSHAKE_INIT"


@pytest.mark.unit
def test_message_schema_valid():
    message = _base_message("MESSAGE")
    validated = validate_message(message)
    assert validated["type"] == "MESSAGE"


@pytest.mark.unit
def test_error_schema_valid():
    message = _base_message("ERROR")
    validated = validate_message(message)
    assert validated["type"] == "ERROR"


@pytest.mark.unit
def test_invalid_type_rejected_with_400_invalid_type():
    message = _base_message("MESSAGE")
    message["type"] = "PUBLIC_KEY"

    with pytest.raises(ProtocolValidationError) as exc_info:
        validate_message(message)

    assert exc_info.value.code == "400_INVALID_TYPE"


@pytest.mark.unit
def test_missing_required_field_rejected_with_400_missing_field():
    message = _base_message("MESSAGE")
    del message["message_id"]

    with pytest.raises(ProtocolValidationError) as exc_info:
        validate_message(message)

    assert exc_info.value.code == "400_MISSING_FIELD"


@pytest.mark.unit
def test_additional_property_rejected_with_400_bad_format():
    message = _base_message("MESSAGE")
    message["extra"] = "not-allowed"

    with pytest.raises(ProtocolValidationError) as exc_info:
        validate_message(message)

    assert exc_info.value.code == "400_BAD_FORMAT"


@pytest.mark.unit
def test_payload_not_modified_during_routing():
    message = _base_message("MESSAGE")
    original_payload = copy.deepcopy(message["payload"])

    validated = validate_message(message)

    assert validated["payload"] == original_payload
