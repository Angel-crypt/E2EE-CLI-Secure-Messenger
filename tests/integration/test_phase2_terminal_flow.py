from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import quote

import pytest
from websockets.asyncio.client import ClientConnection, connect

from app.app_controller import AppController
from infrastructure.crypto import CryptoProvider
from infrastructure.minimal_relay_server import MinimalRelayServer


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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_terminal_to_terminal_wiring_handshake_and_encrypted_message_flow():
    relay = MinimalRelayServer()
    await relay.start()

    alice_controller = AppController(crypto_provider=CryptoProvider())
    bob_controller = AppController(crypto_provider=CryptoProvider())

    alice_ws = await _setup_terminal_runtime(alice_controller, "alice", relay.url)
    bob_ws = await _setup_terminal_runtime(bob_controller, "bob", relay.url)

    now = int(datetime.now(timezone.utc).timestamp())
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

    send_result = alice_controller.send_text_message(
        "alice", "bob", "hola cifrado", now_seconds=now + 3
    )
    assert send_result["ok"] is True
    ciphertext = send_result["data"]["payload"]["ciphertext"]
    assert ciphertext != "hola cifrado"

    await alice_ws.send(
        json.dumps(
            {
                "message_id": "4c0e20a4-4a69-40a3-a3e2-25bf1f2b40f8",
                "timestamp": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                "type": "MESSAGE",
                "from": "alice",
                "to": "bob",
                "payload": send_result["data"]["payload"],
            }
        )
    )

    incoming_message_for_bob = json.loads(await bob_ws.recv())
    decrypted = bob_controller.receive_message(
        incoming_message_for_bob, now_seconds=now + 3
    )
    assert decrypted["ok"] is True
    assert decrypted["data"]["plaintext"] == "hola cifrado"

    await alice_ws.close()
    await bob_ws.close()
    await relay.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redundant_handshake_offer_on_active_channel_is_ignored_without_warning():
    relay = MinimalRelayServer()
    await relay.start()

    alice_controller = AppController(crypto_provider=CryptoProvider())
    bob_controller = AppController(crypto_provider=CryptoProvider())
    alice_ws = await _setup_terminal_runtime(alice_controller, "alice", relay.url)
    bob_ws = await _setup_terminal_runtime(bob_controller, "bob", relay.url)

    now = int(datetime.now(timezone.utc).timestamp())

    first_offer = alice_controller.create_handshake_offer(
        "alice", "bob", now_seconds=now
    )
    await alice_ws.send(json.dumps(first_offer["data"]["frame"]))
    for_bob_1 = json.loads(await bob_ws.recv())
    bob_response_1 = bob_controller.process_handshake_frame(
        for_bob_1, now_seconds=now + 1
    )
    await bob_ws.send(json.dumps(bob_response_1["data"]["frame"]))
    for_alice_1 = json.loads(await alice_ws.recv())
    alice_controller.process_handshake_frame(for_alice_1, now_seconds=now + 2)

    second_offer = alice_controller.create_handshake_offer(
        "alice", "bob", now_seconds=now + 10
    )
    assert second_offer["ok"] is True
    assert second_offer["data"]["event"] == "HANDSHAKE_COMPLETED"
    assert second_offer["data"]["frame"] is None

    notifications = bob_controller.pull_notifications("bob")
    assert notifications["ok"] is True
    items = notifications["data"]["notifications"]
    assert items == []

    await alice_ws.close()
    await bob_ws.close()
    await relay.stop()
