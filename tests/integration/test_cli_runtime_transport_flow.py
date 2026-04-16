from __future__ import annotations

import asyncio

import pytest

from app.app_controller import AppController
from cli.cli_app import CliApp
from app.protocol import make_error
from infrastructure.crypto import CryptoProvider
from infrastructure.minimal_relay_server import MinimalRelayServer


async def _wait_until(predicate, on_tick=None, timeout: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        if on_tick is not None:
            await on_tick()
        await asyncio.sleep(0.05)
    raise AssertionError("Condition not reached before timeout")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cli_runtime_flow_register_handshake_and_exchange_message_with_relay():
    relay = MinimalRelayServer()
    await relay.start()

    alice_logs: list[str] = []

    alice = CliApp(
        AppController(crypto_provider=CryptoProvider()),
        relay_url=relay.url,
    )
    bob = CliApp(
        AppController(crypto_provider=CryptoProvider()),
        relay_url=relay.url,
    )

    alice._print_line = lambda text: alice_logs.append(text)
    bob._print_line = lambda text: None

    await asyncio.to_thread(alice._handle_user, ["/user", "alice"])
    await asyncio.to_thread(bob._handle_user, ["/user", "bob"])

    async def _pump() -> None:
        alice._drain_transport_frames()
        bob._drain_transport_frames()
        await asyncio.sleep(0.05)

    async def _pump_alice_only() -> None:
        alice._drain_transport_frames()
        await asyncio.sleep(0.05)

    for _ in range(4):
        await _pump()

    await asyncio.to_thread(alice._handle_chat, ["/chat", "bob"])

    await _wait_until(
        lambda: (
            alice._channel_state("alice", "bob") == "ACTIVE"
            and bob._channel_state("alice", "bob") == "ACTIVE"
        ),
        on_tick=_pump,
    )

    await asyncio.to_thread(alice._handle_free_text, "hola runtime real")

    await _wait_until(
        lambda: any(frame.get("type") == "MESSAGE" for frame in relay.relayed_frames),
        on_tick=_pump_alice_only,
    )

    message_frames = [
        frame for frame in relay.relayed_frames if frame.get("type") == "MESSAGE"
    ]
    assert message_frames
    latest = message_frames[-1]
    assert latest["payload"]["ciphertext"] != "hola runtime real"

    incoming_for_bob: dict | None = None
    for _ in range(40):
        assert bob._transport_gateway is not None
        frames = bob._transport_gateway.poll_incoming()
        for frame in frames:
            if frame.get("type") == "MESSAGE":
                incoming_for_bob = frame
                break
        if incoming_for_bob is not None:
            break
        await asyncio.sleep(0.05)

    assert incoming_for_bob is not None
    assert incoming_for_bob["from"] == "alice"
    assert incoming_for_bob["to"] == "bob"
    assert incoming_for_bob["payload"]["ciphertext"] != "hola runtime real"

    await asyncio.to_thread(alice._handle_logout, ["/logout"])
    await asyncio.to_thread(bob._handle_logout, ["/logout"])
    await relay.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cli_runtime_auto_receives_messages_with_background_polling():
    cli = CliApp(AppController())
    logs: list[str] = []
    cli._print_line = lambda text: logs.append(text)

    await asyncio.to_thread(cli._handle_user, ["/user", "alice"])

    cli._controller._notifications_bus.publish_to_user(  # type: ignore[attr-defined]
        "alice",
        make_error(
            code="409_REMOTE_KEY_CHANGED",
            message="No se pudo completar la operación solicitada.",
            to="alice",
            details={"operation": "HANDSHAKE_INIT"},
            retriable=True,
        ),
    )

    cli._start_background_polling(interval_seconds=0.05)
    try:
        await _wait_until(
            lambda: any("409_REMOTE_KEY_CHANGED" in line for line in logs),
            timeout=2.0,
        )
    finally:
        cli._stop_background_polling()
