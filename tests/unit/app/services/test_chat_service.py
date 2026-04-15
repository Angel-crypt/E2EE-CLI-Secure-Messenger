from __future__ import annotations

from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet

from app.services.chat_service import ChatService
from app.services.key_exchange_service import KeyExchangeService
from app.services.user_service import SessionUserService
from infrastructure.crypto import CryptoProvider


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _message(sender: str, target: str, ciphertext: str) -> dict:
    sent_at = _now_iso()
    return {
        "message_id": "4c0e20a4-4a69-40a3-a3e2-25bf1f2b40f8",
        "timestamp": sent_at,
        "type": "MESSAGE",
        "from": sender,
        "to": target,
        "payload": {
            "ciphertext": ciphertext,
            "encoding": "base64url",
            "algorithm": "FERNET",
            "nonce": "abcd1234nonce",
            "sent_at": sent_at,
        },
    }


@pytest.fixture
def services() -> tuple[ChatService, KeyExchangeService, CryptoProvider]:
    key_exchange = KeyExchangeService(timeout_seconds=5)
    user_service = SessionUserService(key_exchange_service=key_exchange)
    user_service.register("alice")
    user_service.register("bob")
    crypto = CryptoProvider()
    chat = ChatService(
        user_service=user_service,
        key_exchange_service=key_exchange,
        crypto_provider=crypto,
    )
    return chat, key_exchange, crypto


@pytest.mark.unit
def test_send_requires_secure_channel_and_starts_handshake(
    services: tuple[ChatService, KeyExchangeService, CryptoProvider],
):
    chat, _, _ = services
    message = _message("alice", "bob", "plaintext")

    ok, error, handshake_started = chat.validate_outgoing_message_with_handshake(
        message, now_seconds=int(datetime.now(timezone.utc).timestamp())
    )

    assert ok is False
    assert error is not None
    assert error["payload"]["code"] == "403_SECURE_CHANNEL_REQUIRED"
    assert handshake_started is True


@pytest.mark.unit
def test_build_message_encrypts_payload_with_active_channel(
    services: tuple[ChatService, KeyExchangeService, CryptoProvider],
):
    chat, key_exchange, crypto = services
    session_key = Fernet.generate_key()
    now = int(datetime.now(timezone.utc).timestamp())
    key_exchange.activate_secure_channel(
        "alice", "bob", key=session_key, fp="fp", now=now
    )

    ok, message, error = chat.build_message_from_text("alice", "bob", "hola bob")

    assert ok is True
    assert error is None
    assert message is not None
    assert message["payload"]["ciphertext"] != "hola bob"
    assert crypto.decrypt(session_key, message["payload"]["ciphertext"]) == "hola bob"


@pytest.mark.unit
def test_decrypt_incoming_message_applies_replay_guard(
    services: tuple[ChatService, KeyExchangeService, CryptoProvider],
):
    chat, key_exchange, crypto = services
    session_key = Fernet.generate_key()
    now = int(datetime.now(timezone.utc).timestamp())
    key_exchange.activate_secure_channel(
        "alice", "bob", key=session_key, fp="fp", now=now
    )
    cipher = crypto.encrypt(session_key, "secreto")
    message = _message("alice", "bob", cipher)

    first_ok, plaintext, first_error = chat.decrypt_incoming_message(
        message, now_seconds=now
    )
    second_ok, second_plaintext, second_error = chat.decrypt_incoming_message(
        message, now_seconds=now
    )

    assert first_ok is True
    assert plaintext == "secreto"
    assert first_error is None

    assert second_ok is False
    assert second_plaintext is None
    assert second_error is not None
    assert second_error["payload"]["code"] == "409_REPLAY_DETECTED"
