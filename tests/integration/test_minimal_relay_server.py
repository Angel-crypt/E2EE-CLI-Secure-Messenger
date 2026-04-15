from __future__ import annotations

import pytest

from infrastructure.minimal_relay_server import MinimalRelayServer
from infrastructure.websocket_client import WebSocketClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_minimal_relay_forwards_frames_between_registered_users():
    relay = MinimalRelayServer()
    await relay.start()

    alice = WebSocketClient()
    bob = WebSocketClient()

    await alice.connect(relay.url, "alice")
    await bob.connect(relay.url, "bob")

    await alice.send(
        {
            "type": "REGISTER",
            "from": "alice",
            "payload": {"username": "alice", "public_key": "k"},
        }
    )
    await bob.send(
        {
            "type": "REGISTER",
            "from": "bob",
            "payload": {"username": "bob", "public_key": "k"},
        }
    )

    frame = {
        "message_id": "4c0e20a4-4a69-40a3-a3e2-25bf1f2b40f8",
        "timestamp": "2026-04-15T21:10:00Z",
        "type": "MESSAGE",
        "from": "alice",
        "to": "bob",
        "payload": {
            "ciphertext": "gAAAAABo...",
            "encoding": "base64url",
            "algorithm": "FERNET",
            "nonce": "nonce-2",
            "sent_at": "2026-04-15T21:10:00Z",
        },
    }
    await alice.send(frame)
    received = await bob.receive()

    assert received == frame

    await alice.close()
    await bob.close()
    await relay.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_minimal_relay_is_honest_but_curious_never_decrypts_payload():
    relay = MinimalRelayServer()
    await relay.start()

    alice = WebSocketClient()
    bob = WebSocketClient()

    await alice.connect(relay.url, "alice")
    await bob.connect(relay.url, "bob")

    await alice.send(
        {
            "type": "REGISTER",
            "from": "alice",
            "payload": {"username": "alice", "public_key": "k"},
        }
    )
    await bob.send(
        {
            "type": "REGISTER",
            "from": "bob",
            "payload": {"username": "bob", "public_key": "k"},
        }
    )

    frame = {
        "message_id": "4c0e20a4-4a69-40a3-a3e2-25bf1f2b40f9",
        "timestamp": "2026-04-15T21:11:00Z",
        "type": "MESSAGE",
        "from": "alice",
        "to": "bob",
        "payload": {
            "ciphertext": "gAAAAABhonn6...",
            "encoding": "base64url",
            "algorithm": "FERNET",
            "nonce": "nonce-3",
            "sent_at": "2026-04-15T21:11:00Z",
        },
    }

    await alice.send(frame)
    _ = await bob.receive()

    assert (
        relay.relayed_frames[-1]["payload"]["ciphertext"]
        == frame["payload"]["ciphertext"]
    )
    assert "plaintext" not in relay.relayed_frames[-1]["payload"]

    await alice.close()
    await bob.close()
    await relay.stop()
