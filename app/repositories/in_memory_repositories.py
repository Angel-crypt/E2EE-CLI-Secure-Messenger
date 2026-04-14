"""Repositorios en memoria para fase local y pruebas rapidas."""

from __future__ import annotations

from typing import Any


class InMemorySessionRepository:
    """Persistencia en memoria de sesiones y presencia."""

    def __init__(self) -> None:
        self._active_by_user: dict[str, dict[str, Any]] = {}
        self._known_users: set[str] = set()

    def create_active_session(
        self,
        username: str,
        session_id: str,
        connected_at_iso: str,
        connected_at_epoch: int,
    ) -> bool:
        if username in self._active_by_user:
            return False

        self._active_by_user[username] = {
            "session_id": session_id,
            "connected_at": connected_at_iso,
            "connected_at_epoch": connected_at_epoch,
            "status": "ACTIVE",
        }
        self._known_users.add(username)
        return True

    def close_active_session(
        self,
        username: str,
        disconnected_at_iso: str,
        disconnected_at_epoch: int,
    ) -> bool:
        _ = disconnected_at_iso
        _ = disconnected_at_epoch
        if username not in self._active_by_user:
            return False

        del self._active_by_user[username]
        self._known_users.add(username)
        return True

    def is_user_active(self, username: str) -> bool:
        return username in self._active_by_user

    def list_users_state(self) -> list[dict[str, str]]:
        users = []
        for username in sorted(self._known_users):
            users.append(
                {
                    "username": username,
                    "state": "online"
                    if username in self._active_by_user
                    else "offline",
                }
            )
        return users


class InMemoryChannelRepository:
    """Persistencia en memoria de canales seguros."""

    def __init__(self) -> None:
        self._channels: dict[str, dict[str, Any]] = {}

    def upsert_channel(
        self,
        pair_key: str,
        peer_a: str,
        peer_b: str,
        state: str,
        started_at: int | None = None,
        established_at: int | None = None,
        invalidated_at: int | None = None,
    ) -> None:
        self._channels[pair_key] = {
            "pair_key": pair_key,
            "peer_a": peer_a,
            "peer_b": peer_b,
            "state": state,
            "started_at": started_at,
            "established_at": established_at,
            "invalidated_at": invalidated_at,
        }

    def get_channel(self, pair_key: str) -> dict[str, Any] | None:
        return self._channels.get(pair_key)

    def invalidate_user_channels(self, username: str, invalidated_at: int) -> None:
        for channel in self._channels.values():
            if username in {channel["peer_a"], channel["peer_b"]}:
                channel["state"] = "INVALID"
                channel["invalidated_at"] = invalidated_at
