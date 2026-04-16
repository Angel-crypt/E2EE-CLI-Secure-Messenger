from __future__ import annotations

import json
from urllib.parse import quote

import pytest
from websockets.asyncio.client import connect

from infrastructure.minimal_relay_server import MinimalRelayServer


async def _ws_connect(url: str, username: str):
    sep = "&" if "?" in url else "?"
    return await connect(f"{url}{sep}username={quote(username)}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_relay_starts_and_relays_frames_between_clients():
    relay = MinimalRelayServer(host="127.0.0.1", port=0)
    await relay.start()

    alice = await _ws_connect(relay.url, "alice")
    bob = await _ws_connect(relay.url, "bob")
    try:
        await alice.send(
            json.dumps(
                {
                    "type": "REGISTER",
                    "from": "alice",
                    "payload": {"username": "alice", "public_key": "k"},
                }
            )
        )
        await bob.send(
            json.dumps(
                {
                    "type": "REGISTER",
                    "from": "bob",
                    "payload": {"username": "bob", "public_key": "k"},
                }
            )
        )

        frame = {
            "message_id": "relay-runner-test",
            "timestamp": "2026-04-15T22:20:00Z",
            "type": "MESSAGE",
            "from": "alice",
            "to": "bob",
            "payload": {
                "ciphertext": "gAAAAABrunner",
                "encoding": "base64url",
                "algorithm": "FERNET",
                "nonce": "n-runner-1",
                "sent_at": "2026-04-15T22:20:00Z",
            },
        }
        await alice.send(json.dumps(frame))

        received = json.loads(await bob.recv())
        assert received == frame
    finally:
        await alice.close()
        await bob.close()
        await relay.stop()
