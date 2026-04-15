from datetime import datetime, timezone

import pytest

from app.protocol import ProtocolValidationError, validate_message


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _message_payload() -> dict:
    return {
        "ciphertext": "gAAAAABo...",
        "encoding": "base64url",
        "algorithm": "FERNET",
        "nonce": "7f4cd3272ff44d85b0b10ac1d4ccf774",
        "sent_at": _now_iso(),
    }


def _base_message() -> dict:
    return {
        "message_id": "4c0e20a4-4a69-40a3-a3e2-25bf1f2b40f8",
        "timestamp": _now_iso(),
        "type": "MESSAGE",
        "from": "alice",
        "to": "bob",
        "payload": _message_payload(),
    }


@pytest.mark.unit
def test_message_payload_requires_nonce_and_sent_at_for_replay_guard():
    validated = validate_message(_base_message())

    assert validated["payload"]["nonce"] == "7f4cd3272ff44d85b0b10ac1d4ccf774"
    assert validated["payload"]["sent_at"].endswith("Z")


@pytest.mark.unit
def test_message_payload_missing_nonce_is_rejected():
    message = _base_message()
    del message["payload"]["nonce"]

    with pytest.raises(ProtocolValidationError) as exc_info:
        validate_message(message)

    assert exc_info.value.code == "400_MISSING_FIELD"


@pytest.mark.unit
def test_message_payload_missing_sent_at_is_rejected():
    message = _base_message()
    del message["payload"]["sent_at"]

    with pytest.raises(ProtocolValidationError) as exc_info:
        validate_message(message)

    assert exc_info.value.code == "400_MISSING_FIELD"


@pytest.mark.unit
def test_error_payload_accepts_replay_error_codes():
    error_message = {
        "message_id": "8f3967ea-f08f-448f-8fec-9b53bb8e8a43",
        "timestamp": _now_iso(),
        "type": "ERROR",
        "from": "server",
        "to": "alice",
        "payload": {
            "code": "409_REPLAY_DETECTED",
            "message": "Replay detectado",
            "details": {"nonce": "7f4cd3272ff44d85b0b10ac1d4ccf774"},
            "retriable": False,
        },
    }

    validated = validate_message(error_message)

    assert validated["payload"]["code"] == "409_REPLAY_DETECTED"
