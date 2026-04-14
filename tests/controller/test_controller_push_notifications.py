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


def _message_msg(sender: str, target: str) -> dict:
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
            "ciphertext": "hola",
            "encoding": "base64url",
            "algorithm": "FERNET",
        },
    }


@pytest.mark.unit
def test_send_message_without_channel_publishes_directed_notification():
    controller = AppController()
    controller.register(_register_msg("alice"))
    controller.register(_register_msg("bob"))

    result = controller.send_message(_message_msg("alice", "bob"), now_seconds=1)
    assert result["ok"] is False
    assert result["error"]["payload"]["code"] == "403_SECURE_CHANNEL_REQUIRED"

    notifications = controller.pull_notifications("alice")
    assert notifications["ok"] is True
    items = notifications["data"]["notifications"]
    assert len(items) == 1
    assert items[0]["payload"]["code"] == "403_SECURE_CHANNEL_REQUIRED"
