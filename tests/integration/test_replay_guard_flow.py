from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import quote

import pytest
from websockets.asyncio.client import ClientConnection, connect

from app.app_controller import AppController
from app.protocol import TIMESTAMP_TOLERANCE_SECONDS
from infrastructure.crypto import CryptoProvider
from infrastructure.minimal_relay_server import MinimalRelayServer


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _register_msg(username: str) -> dict:
    return {
        "message_id": "f8215ae4-a9d5-4434-ae54-3cc676db7ce0",
        "timestamp": _now_iso(),
        "type": "REGISTER",
        "from": username,
        "payload": {
            "username": username,
            "public_key": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...",
        },
    }


async def _ws_connect(url: str, username: str) -> ClientConnection:
    sep = "&" if "?" in url else "?"
    return await connect(f"{url}{sep}username={quote(username)}")


async def _setup_terminal_runtime(
    controller: AppController, username: str, relay_url: str
) -> ClientConnection:
    ws = await _ws_connect(relay_url, username)
    await ws.send(json.dumps(_register_msg(username)))
    controller.register(_register_msg("alice"))
    controller.register(_register_msg("bob"))
    return ws


async def _establish_secure_channel(
    alice_controller: AppController,
    bob_controller: AppController,
    alice_ws: ClientConnection,
    bob_ws: ClientConnection,
    now: int,
) -> None:
    offer = alice_controller.create_handshake_offer("alice", "bob", now_seconds=now)
    assert offer["ok"] is True

    await alice_ws.send(json.dumps(offer["data"]["frame"]))
    incoming_for_bob = json.loads(await bob_ws.recv())
    bob_result = bob_controller.process_handshake_frame(
        incoming_for_bob, now_seconds=now + 1
    )
    assert bob_result["ok"] is True
    assert bob_result["data"]["frame"] is not None

    await bob_ws.send(json.dumps(bob_result["data"]["frame"]))
    incoming_for_alice = json.loads(await alice_ws.recv())
    alice_result = alice_controller.process_handshake_frame(
        incoming_for_alice, now_seconds=now + 2
    )
    assert alice_result["ok"] is True

    assert (
        alice_controller.get_channel_state("alice", "bob")["data"]["state"] == "ACTIVE"
    )
    assert bob_controller.get_channel_state("alice", "bob")["data"]["state"] == "ACTIVE"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rejects_message_with_stale_timestamp_before_payload_acceptance():
    relay = MinimalRelayServer()
    await relay.start()

    alice_controller = AppController(crypto_provider=CryptoProvider())
    bob_controller = AppController(crypto_provider=CryptoProvider())

    alice_ws = await _setup_terminal_runtime(alice_controller, "alice", relay.url)
    bob_ws = await _setup_terminal_runtime(bob_controller, "bob", relay.url)

    try:
        now = int(datetime.now(timezone.utc).timestamp())
        await _establish_secure_channel(
            alice_controller, bob_controller, alice_ws, bob_ws, now
        )

        send_result = alice_controller.send_text_message(
            "alice", "bob", "mensaje viejo", now_seconds=now + 3
        )
        assert send_result["ok"] is True
        replay_payload = send_result["data"]["payload"]

        replay_payload["sent_at"] = _now_iso()

        stale_frame = {
            "message_id": "4c0e20a4-4a69-40a3-a3e2-25bf1f2b40f8",
            "timestamp": _now_iso(),
            "type": "MESSAGE",
            "from": "alice",
            "to": "bob",
            "payload": replay_payload,
        }

        await alice_ws.send(json.dumps(stale_frame))
        stale_incoming = json.loads(await bob_ws.recv())
        stale_result = bob_controller.receive_message(
            stale_incoming,
            now_seconds=now + TIMESTAMP_TOLERANCE_SECONDS + 10,
        )

        assert stale_result["ok"] is False
        assert (
            stale_result["error"]["payload"]["code"] == "400_REPLAY_TIMESTAMP_INVALID"
        )

        replay_payload["sent_at"] = _now_iso()
        fresh_frame = {
            "message_id": "2cb74f8e-6353-45e2-a6f6-d2f768f0ca44",
            "timestamp": _now_iso(),
            "type": "MESSAGE",
            "from": "alice",
            "to": "bob",
            "payload": replay_payload,
        }
        await alice_ws.send(json.dumps(fresh_frame))
        fresh_incoming = json.loads(await bob_ws.recv())
        fresh_result = bob_controller.receive_message(
            fresh_incoming,
            now_seconds=int(datetime.now(timezone.utc).timestamp()),
        )

        assert fresh_result["ok"] is True
        assert fresh_result["data"]["plaintext"] == "mensaje viejo"
    finally:
        await alice_ws.close()
        await bob_ws.close()
        await relay.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rejects_replayed_nonce_after_first_valid_delivery():
    relay = MinimalRelayServer()
    await relay.start()

    alice_controller = AppController(crypto_provider=CryptoProvider())
    bob_controller = AppController(crypto_provider=CryptoProvider())

    alice_ws = await _setup_terminal_runtime(alice_controller, "alice", relay.url)
    bob_ws = await _setup_terminal_runtime(bob_controller, "bob", relay.url)

    try:
        now = int(datetime.now(timezone.utc).timestamp())
        await _establish_secure_channel(
            alice_controller, bob_controller, alice_ws, bob_ws, now
        )

        send_result = alice_controller.send_text_message(
            "alice", "bob", "nonce unico", now_seconds=now + 3
        )
        assert send_result["ok"] is True

        frame = {
            "message_id": "4c0e20a4-4a69-40a3-a3e2-25bf1f2b40f8",
            "timestamp": _now_iso(),
            "type": "MESSAGE",
            "from": "alice",
            "to": "bob",
            "payload": send_result["data"]["payload"],
        }

        await alice_ws.send(json.dumps(frame))
        first_incoming = json.loads(await bob_ws.recv())
        first_result = bob_controller.receive_message(
            first_incoming, now_seconds=now + 3
        )
        assert first_result["ok"] is True
        assert first_result["data"]["plaintext"] == "nonce unico"

        await alice_ws.send(json.dumps(frame))
        replay_incoming = json.loads(await bob_ws.recv())
        replay_result = bob_controller.receive_message(
            replay_incoming, now_seconds=now + 3
        )
        assert replay_result["ok"] is False
        assert replay_result["error"]["payload"]["code"] == "409_REPLAY_DETECTED"
    finally:
        await alice_ws.close()
        await bob_ws.close()
        await relay.stop()
