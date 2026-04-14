import pytest
from datetime import datetime, timezone

from app.app_controller import AppController


def _register_msg(username: str) -> dict:
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
        "from": username,
        "payload": {
            "username": username,
            "public_key": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...",
        },
    }


def _message_msg(sender: str, target: str, text: str = "hola") -> dict:
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
        "from": sender,
        "to": target,
        "payload": {
            "ciphertext": text,
            "encoding": "base64url",
            "algorithm": "FERNET",
        },
    }


def _handshake_msg(sender: str, target: str) -> dict:
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
        "from": sender,
        "to": target,
        "payload": {
            "username": sender,
            "public_key": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...",
            "nonce": "YjRjNDY2ZjQwYw",
            "reason": "ON_DEMAND",
        },
    }


@pytest.fixture
def controller() -> AppController:
    c = AppController()
    c.register(_register_msg("alice"))
    c.register(_register_msg("bob"))
    return c


@pytest.mark.unit
def test_message_without_active_channel_returns_403(controller: AppController):
    result = controller.send_message(_message_msg("alice", "bob"), now_seconds=1)
    assert result["ok"] is False
    assert result["error"]["payload"]["code"] == "403_SECURE_CHANNEL_REQUIRED"


@pytest.mark.unit
def test_handshake_then_message_is_accepted(controller: AppController):
    controller.handshake_init(_handshake_msg("alice", "bob"), now_seconds=1)
    controller.complete_handshake("alice", "bob", now_seconds=2)

    result = controller.send_message(
        _message_msg("alice", "bob", "payload"), now_seconds=2
    )

    assert result["ok"] is True
    assert result["data"]["event"] == "MESSAGE_ACCEPTED"


@pytest.mark.unit
def test_send_text_message_empty_is_rejected(controller: AppController):
    result = controller.send_text_message("alice", "bob", "   ", now_seconds=1)
    assert result["ok"] is False
    assert result["error"]["payload"]["code"] == "400_INVALID_PAYLOAD"
