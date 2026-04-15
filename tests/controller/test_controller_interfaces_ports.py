import pytest
from datetime import datetime, timezone

from app.app_controller import AppController
from app.interfaces import InMemoryNotificationBus, SystemClock


class FixedClock(SystemClock):
    def __init__(self, fixed: int) -> None:
        self._fixed = fixed

    def now_seconds(self) -> int:
        return self._fixed


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
            "nonce": "YjRjNDY2ZjQwYw",
            "sent_at": now_iso,
        },
    }


@pytest.mark.unit
def test_controller_uses_injected_notification_port():
    bus = InMemoryNotificationBus()
    controller = AppController(notifications=bus)

    controller.register(_register_msg("alice"))
    controller.register(_register_msg("bob"))
    result = controller.send_message(_message_msg("alice", "bob"), now_seconds=1)

    assert result["ok"] is False
    assert controller.pull_notifications("alice")["data"]["notifications"]


@pytest.mark.unit
def test_controller_uses_clock_when_now_seconds_not_provided():
    clock = FixedClock(10)
    controller = AppController(clock=clock)

    controller.register(_register_msg("alice"))
    controller.register(_register_msg("bob"))
    controller.send_message(_message_msg("alice", "bob"))

    state = controller.handshake_init(
        {
            "message_id": "15ceec6f-6f45-45f2-a2b8-17f40f53c295",
            "timestamp": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
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
    )

    assert state["ok"] is True
