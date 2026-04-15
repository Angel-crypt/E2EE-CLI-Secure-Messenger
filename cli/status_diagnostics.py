"""Diagnóstico de estado para la CLI."""

from __future__ import annotations

from typing import Callable


def build_status_diagnostics(
    *,
    list_users: Callable[[], dict],
    current_user: str | None,
    chat_target: str | None,
    user_status: Callable[[str], str],
    channel_state: Callable[[str, str], str],
    theme_name: str,
    poll_enabled: bool,
) -> dict[str, str]:
    """Construye snapshot de diagnóstico visible en `/status`."""

    response = list_users()
    users = response.get("data", {}).get("users", []) if response.get("ok") else []
    runtime_users = len(users)
    online_users = sum(1 for user in users if user.get("state") == "online")

    target = chat_target or "(sin chat activo)"
    if chat_target is None:
        target_status = "N/A"
        channel = "N/A"
    else:
        target_status = user_status(chat_target)
        if current_user is None:
            channel = "N/A"
        else:
            channel = channel_state(current_user, chat_target)

    return {
        "session": "registrado" if current_user else "sin registrar",
        "runtime_users": str(runtime_users),
        "online_users": str(online_users),
        "chat_active": "sí" if chat_target else "no",
        "target": target,
        "target_status": target_status,
        "channel": channel,
        "theme": theme_name,
        "polling": "on" if poll_enabled else "off",
    }
