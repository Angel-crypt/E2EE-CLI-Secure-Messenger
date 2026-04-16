import pytest
from datetime import datetime, timezone

from app.app_controller import AppController
from app.interfaces import SystemClock


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


@pytest.mark.unit
def test_controller_uses_internal_notification_bus():
    controller = AppController()

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


class _CountingCryptoProvider:
    def __init__(self) -> None:
        self.generate_calls = 0
        self.derive_calls = 0
        self.fingerprint_calls = 0

    def generate_ecdh_keypair(self) -> tuple[str, object]:
        self.generate_calls += 1
        return ("pub-local", object())

    def derive_fernet_key(self, private_key: object, remote_public_pem: str) -> bytes:
        _ = private_key, remote_public_pem
        self.derive_calls += 1
        return b"session"

    def fingerprint_public_key(self, public_pem: str) -> str:
        _ = public_pem
        self.fingerprint_calls += 1
        return "fp-remote"

    def encrypt(self, fernet_key: bytes, plaintext: str) -> str:
        _ = fernet_key
        return plaintext

    def decrypt(self, fernet_key: bytes, ciphertext: str) -> str:
        _ = fernet_key
        return ciphertext


@pytest.mark.unit
def test_process_handshake_frame_skips_crypto_rotation_when_channel_already_active():
    crypto = _CountingCryptoProvider()
    controller = AppController(crypto_provider=crypto)
    controller.register(_register_msg("alice"))
    controller.register(_register_msg("bob"))
    controller._key_exchange.activate_secure_channel(  # type: ignore[attr-defined]
        "alice", "bob", key=b"stable", fp="fp-stable", now=100
    )

    response = controller.process_handshake_frame(
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
                "public_key": "pub-remote-new",
                "nonce": "abc123",
                "reason": "ON_DEMAND",
            },
        },
        now_seconds=101,
    )

    assert response["ok"] is True
    assert response["data"]["event"] == "HANDSHAKE_COMPLETED"
    assert response["data"]["frame"] is None
    assert crypto.generate_calls == 0
    assert crypto.derive_calls == 0
    assert crypto.fingerprint_calls == 0

    notifications = controller.pull_notifications("bob")
    assert notifications["ok"] is True
    assert notifications["data"]["notifications"] == []


@pytest.mark.unit
def test_create_handshake_offer_returns_no_frame_when_channel_already_active():
    crypto = _CountingCryptoProvider()
    controller = AppController(crypto_provider=crypto)
    controller.register(_register_msg("alice"))
    controller.register(_register_msg("bob"))
    controller._key_exchange.activate_secure_channel(  # type: ignore[attr-defined]
        "alice", "bob", key=b"stable", fp="fp-stable", now=100
    )

    response = controller.create_handshake_offer("alice", "bob", now_seconds=101)

    assert response["ok"] is True
    assert response["data"]["event"] == "HANDSHAKE_COMPLETED"
    assert response["data"]["state"] == "ACTIVE"
    assert response["data"]["frame"] is None
    assert crypto.generate_calls == 0


@pytest.mark.unit
def test_create_handshake_offer_returns_no_frame_when_channel_establishing_and_pending_key():
    crypto = _CountingCryptoProvider()
    controller = AppController(crypto_provider=crypto)
    controller.register(_register_msg("alice"))
    controller.register(_register_msg("bob"))
    started = controller.handshake_init(_handshake_msg("alice", "bob"), now_seconds=100)
    assert started["ok"] is True
    controller._key_exchange.set_pending_private_key(  # type: ignore[attr-defined]
        "alice", "bob", object()
    )

    response = controller.create_handshake_offer("alice", "bob", now_seconds=101)

    assert response["ok"] is True
    assert response["data"]["event"] == "HANDSHAKE_STARTED"
    assert response["data"]["state"] == "ESTABLISHING"
    assert response["data"]["frame"] is None
    assert crypto.generate_calls == 0
