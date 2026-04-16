"""Temas predefinidos para el CLI.

Solo se permite seleccionar temas existentes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CliTheme:
    name: str
    info_style: str
    success_style: str
    warning_style: str
    error_style: str
    message_style: str
    meta_style: str
    icon_info: str
    icon_success: str
    icon_warning: str
    icon_error: str
    icon_message: str
    icon_lock: str
    icon_help: str
    icon_users: str
    icon_notif: str
    icon_exit: str
    panel_style: str
    timestamp_style: str
    table_header_style: str


THEMES: dict[str, CliTheme] = {
    "default": CliTheme(
        name="default",
        info_style="cyan",
        success_style="green",
        warning_style="yellow",
        error_style="red",
        message_style="magenta",
        meta_style="dim",
        icon_info="[i]",
        icon_success="[ok]",
        icon_warning="[!]",
        icon_error="[x]",
        icon_message="[msg]",
        icon_lock="[lock]",
        icon_help="[help]",
        icon_users="[users]",
        icon_notif="[notif]",
        icon_exit="[exit]",
        panel_style="white on black",
        timestamp_style="dim",
        table_header_style="bold cyan",
    ),
    "minimal": CliTheme(
        name="minimal",
        info_style="white",
        success_style="white",
        warning_style="white",
        error_style="white",
        message_style="white",
        meta_style="dim",
        icon_info="-",
        icon_success="+",
        icon_warning="!",
        icon_error="x",
        icon_message=">",
        icon_lock="#",
        icon_help="?",
        icon_users="u",
        icon_notif="n",
        icon_exit="q",
        panel_style="white on black",
        timestamp_style="dim",
        table_header_style="bold white",
    ),
    "matrix": CliTheme(
        name="matrix",
        info_style="green",
        success_style="bright_green",
        warning_style="yellow",
        error_style="red",
        message_style="green",
        meta_style="dim green",
        icon_info="[i]",
        icon_success="[+]",
        icon_warning="[!]",
        icon_error="[x]",
        icon_message=">>",
        icon_lock="[k]",
        icon_help="[?]",
        icon_users="[u]",
        icon_notif="[n]",
        icon_exit="[q]",
        panel_style="green on black",
        timestamp_style="dim green",
        table_header_style="bold green",
    ),
}


def get_theme(theme_name: str) -> CliTheme:
    """Retorna tema por nombre o `default` si no existe."""
    return THEMES.get(theme_name, THEMES["default"])


def list_theme_names() -> list[str]:
    """Retorna nombres de temas disponibles."""
    return sorted(THEMES.keys())
