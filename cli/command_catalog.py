"""Catálogo de comandos CLI y utilidades asociadas."""

from __future__ import annotations


COMMANDS: tuple[str, ...] = (
    "/user",
    "/logout",
    "/users",
    "/chat",
    "/msg",
    "/notif",
    "/poll",
    "/theme",
    "/leave",
    "/help",
    "/status",
    "/clear",
    "/exit",
)


def resolve_command(
    raw_command: str, commands: tuple[str, ...] = COMMANDS
) -> str | None:
    """Resuelve comando por coincidencia exacta o prefijo único/primero.

    Mantiene semántica histórica de la CLI:
    - requiere slash inicial
    - prefijos ambiguos resuelven al primer comando del catálogo
    """

    if not raw_command.startswith("/"):
        return None
    if raw_command in commands:
        return raw_command

    matches = [command for command in commands if command.startswith(raw_command)]
    if not matches:
        return None
    return matches[0]
