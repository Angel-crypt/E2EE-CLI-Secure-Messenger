from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.key_exchange_service import KeyExchangeService


def _iso_from_epoch(epoch_seconds: int) -> str:
    return (
        datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


@pytest.fixture
def service() -> KeyExchangeService:
    return KeyExchangeService(timeout_seconds=5)


@pytest.mark.unit
def test_validate_replay_rejects_timestamp_outside_window(service: KeyExchangeService):
    service.activate_secure_channel(
        "alice", "bob", key=b"k", fp="fp-1", now=1_700_000_000
    )

    stale_sent_at = _iso_from_epoch(1_700_000_000 - 121)
    ok, error = service.validate_replay(
        "alice",
        "bob",
        nonce="nonce-1",
        sent_at_iso=stale_sent_at,
        now=1_700_000_000,
    )

    assert ok is False
    assert error is not None
    assert error["payload"]["code"] == "400_REPLAY_TIMESTAMP_INVALID"


@pytest.mark.unit
def test_validate_replay_rejects_nonce_reuse(service: KeyExchangeService):
    service.activate_secure_channel(
        "alice", "bob", key=b"k", fp="fp-1", now=1_700_000_000
    )
    sent_at = _iso_from_epoch(1_700_000_000)

    first_ok, first_error = service.validate_replay(
        "alice", "bob", nonce="same-nonce", sent_at_iso=sent_at, now=1_700_000_000
    )
    second_ok, second_error = service.validate_replay(
        "alice", "bob", nonce="same-nonce", sent_at_iso=sent_at, now=1_700_000_000
    )

    assert first_ok is True
    assert first_error is None
    assert second_ok is False
    assert second_error is not None
    assert second_error["payload"]["code"] == "409_REPLAY_DETECTED"


@pytest.mark.unit
def test_activate_secure_channel_stores_key_and_state(service: KeyExchangeService):
    service.start_handshake("alice", "bob", now_seconds=10)
    service.activate_secure_channel(
        "alice", "bob", key=b"session-key", fp="fp-a", now=11
    )

    assert service.channel_state("alice", "bob") == "ACTIVE"
    assert service.get_session_key("alice", "bob") == b"session-key"
    assert service.get_remote_fingerprint("alice", "bob") == "fp-a"


@pytest.mark.unit
def test_activate_secure_channel_emits_warning_on_fingerprint_change(
    service: KeyExchangeService,
):
    now = int(datetime.now(tz=timezone.utc).timestamp())
    service.activate_secure_channel("alice", "bob", key=b"k1", fp="fp-old", now=now)
    service.activate_secure_channel("alice", "bob", key=b"k2", fp="fp-new", now=now + 1)

    warning = service.consume_fingerprint_warning("alice", "bob")

    assert warning is not None
    assert warning["event"] == "REMOTE_KEY_CHANGED"
    assert warning["previous_fingerprint"] == "fp-old"
    assert warning["current_fingerprint"] == "fp-new"

    assert service.consume_fingerprint_warning("alice", "bob") is None


@pytest.mark.unit
def test_activate_secure_channel_with_same_fingerprint_emits_no_warning(
    service: KeyExchangeService,
):
    now = int(datetime.now(tz=timezone.utc).timestamp())
    service.activate_secure_channel("alice", "bob", key=b"k1", fp="fp-stable", now=now)
    service.activate_secure_channel(
        "alice", "bob", key=b"k2", fp="fp-stable", now=now + 1
    )

    assert service.consume_fingerprint_warning("alice", "bob") is None


@pytest.mark.unit
def test_validate_replay_accepts_timestamp_inside_window(service: KeyExchangeService):
    now = int(datetime.now(tz=timezone.utc).timestamp())
    service.activate_secure_channel("alice", "bob", key=b"k", fp="fp-1", now=now)
    recent = datetime.now(tz=timezone.utc) - timedelta(seconds=60)
    sent_at = recent.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    ok, error = service.validate_replay(
        "alice", "bob", nonce="nonce-recent", sent_at_iso=sent_at, now=now
    )

    assert ok is True
    assert error is None
