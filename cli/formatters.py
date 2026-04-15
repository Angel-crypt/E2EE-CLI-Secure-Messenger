"""Formateadores centralizados para salida de CLI."""

from __future__ import annotations

from typing import Any

from rich.table import Table

from cli.themes import CliTheme


ERROR_UX_MESSAGES = {
    "401_NOT_REGISTERED": "Debes registrarte primero con /user <nombre>.",
    "403_SECURE_CHANNEL_REQUIRED": "Canal seguro requerido. Reintenta en unos segundos.",
    "404_USER_OFFLINE": "El usuario destino no está disponible.",
    "409_USERNAME_TAKEN": "No se pudo iniciar sesión con esa identidad.",
    "400_BAD_FORMAT": "Comando o mensaje inválido.",
    "400_MISSING_FIELD": "Comando o mensaje incompleto.",
    "400_INVALID_FIELD_TYPE": "Formato de datos inválido.",
    "400_INVALID_TYPE": "Tipo de mensaje no permitido.",
    "400_INVALID_TO": "Destino inválido para esta operación.",
    "400_INVALID_PAYLOAD": "Contenido de mensaje inválido.",
    "400_TIMESTAMP_OUT_OF_WINDOW": "Mensaje fuera de ventana temporal válida.",
    "500_INTERNAL_ERROR": "Error interno temporal. Intenta nuevamente.",
    "503_ROUTING_UNAVAILABLE": "Servicio temporalmente no disponible.",
    "504_KEY_EXCHANGE_TIMEOUT": "Tiempo de intercambio de clave agotado. Reintenta.",
    "409_REMOTE_KEY_CHANGED": "Advertencia: cambió la fingerprint remota; posible MITM.",
}


def format_info(theme: CliTheme, text: str) -> str:
    return f"[{theme.info_style}]{theme.icon_info} {text}[/{theme.info_style}]"


def format_success(theme: CliTheme, text: str) -> str:
    return f"[{theme.success_style}]{theme.icon_success} {text}[/{theme.success_style}]"


def format_warning(theme: CliTheme, text: str) -> str:
    return f"[{theme.warning_style}]{theme.icon_warning} {text}[/{theme.warning_style}]"


def format_error(theme: CliTheme, error_message: dict[str, Any]) -> str:
    payload = error_message.get("payload", {})
    code = payload.get("code", "500_INTERNAL_ERROR")
    ux_text = ERROR_UX_MESSAGES.get(
        code, "No se pudo completar la operación solicitada."
    )
    return f"[{theme.error_style}]{theme.icon_error} {code}: {ux_text}[/{theme.error_style}]"


def format_event(theme: CliTheme, event: str, data: dict[str, Any]) -> str:
    if event == "REGISTERED":
        return format_success(theme, f"Usuario registrado: {data.get('username')}")
    if event == "DISCONNECTED":
        return format_info(theme, f"Sesión cerrada: {data.get('username')}")
    if event == "HANDSHAKE_STARTED":
        return format_warning(
            theme,
            f"{theme.icon_lock} Estableciendo canal seguro con {data.get('to')}",
        )
    if event == "HANDSHAKE_COMPLETED":
        return format_success(theme, f"Canal seguro activo con {data.get('to')}")
    if event == "MESSAGE_ACCEPTED":
        return format_success(theme, f"Mensaje enviado a {data.get('to')}")
    return format_info(theme, f"Evento: {event}")


def format_notification(theme: CliTheme, message: dict[str, Any]) -> str:
    payload = message.get("payload", {})
    code = payload.get("code", "UNKNOWN")
    if code.startswith("4"):
        return format_warning(theme, f"{theme.icon_notif} Notificación: {code}")
    if code.startswith("5"):
        return format_error(theme, message)
    return format_info(theme, f"{theme.icon_notif} Notificación: {code}")


def build_users_table(theme: CliTheme, users: list[dict[str, str]]) -> Table:
    table = Table(
        title="Usuarios",
        show_header=True,
        header_style=theme.table_header_style,
        border_style=theme.meta_style,
        title_style=theme.table_header_style,
    )
    table.add_column(
        "Username", style=theme.message_style, header_style=theme.table_header_style
    )
    table.add_column(
        "Estado", style=theme.meta_style, header_style=theme.table_header_style
    )

    for user in users:
        state = user.get("state", "offline")
        state_style = theme.success_style if state == "online" else theme.warning_style
        table.add_row(
            user.get("username", "?"), f"[{state_style}]{state}[/{state_style}]"
        )
    return table
