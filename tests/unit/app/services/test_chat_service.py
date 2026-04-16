"""Tests for ChatService behaviors now absorbed into AppController."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet

from app.app_controller import AppController
from app.services.key_exchange_service import KeyExchangeService
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


@pytest.fixture
def controller() -> tuple[AppController, KeyExchangeService, CryptoProvider]:
    key_exchange = KeyExchangeService(timeout_seconds=5)
    crypto = CryptoProvider()
    ctrl = AppController(key_exchange_service=key_exchange, crypto_provider=crypto)
    ctrl.register(_register_msg("alice"))
    ctrl.register(_register_msg("bob"))
    return ctrl, key_exchange, crypto


@pytest.mark.unit
def test_send_requires_secure_channel_and_starts_handshake(
    controller: tuple[AppController, KeyExchangeService, CryptoProvider],
):
    ctrl, _, _ = controller
    message = _message("alice", "bob", "plaintext")
    now = int(datetime.now(timezone.utc).timestamp())

    response = ctrl.send_message(message, now_seconds=now)

    assert response["ok"] is False
    error = response["error"]
    assert error["payload"]["code"] == "403_SECURE_CHANNEL_REQUIRED"
    assert error["payload"]["details"]["handshake_started"] is True


@pytest.mark.unit
def test_build_message_encrypts_payload_with_active_channel(
    controller: tuple[AppController, KeyExchangeService, CryptoProvider],
):
    ctrl, key_exchange, crypto = controller
    session_key = Fernet.generate_key()
    now = int(datetime.now(timezone.utc).timestamp())
    key_exchange.activate_secure_channel(
        "alice", "bob", key=session_key, fp="fp", now=now
    )

    response = ctrl.send_text_message("alice", "bob", "hola bob", now_seconds=now)

    assert response["ok"] is True
    payload = response["data"]["payload"]
    assert payload["ciphertext"] != "hola bob"
    assert crypto.decrypt(session_key, payload["ciphertext"]) == "hola bob"


@pytest.mark.unit
def test_decrypt_incoming_message_applies_replay_guard(
    controller: tuple[AppController, KeyExchangeService, CryptoProvider],
):
    ctrl, key_exchange, crypto = controller
    session_key = Fernet.generate_key()
    now = int(datetime.now(timezone.utc).timestamp())
    key_exchange.activate_secure_channel(
        "alice", "bob", key=session_key, fp="fp", now=now
    )
    cipher = crypto.encrypt(session_key, "secreto")
    message = _message("alice", "bob", cipher)

    first_response = ctrl.receive_message(message, now_seconds=now)
    second_response = ctrl.receive_message(message, now_seconds=now)

    assert first_response["ok"] is True
    assert first_response["data"]["plaintext"] == "secreto"

    assert second_response["ok"] is False
    assert second_response["error"]["payload"]["code"] == "409_REPLAY_DETECTED"
