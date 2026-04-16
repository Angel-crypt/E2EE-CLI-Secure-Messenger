"""CLI interactiva para el dominio de mensajería."""

from __future__ import annotations

from collections import deque
import os
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
from uuid import uuid4

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from app.app_controller import AppController
from cli.command_catalog import COMMANDS, resolve_command
from cli.formatters import (
    build_users_table,
    format_error,
    format_event,
    format_info,
    format_notification,
    format_success,
    format_warning,
)
from cli.themes import get_theme, list_theme_names
from cli.status_diagnostics import build_status_diagnostics
from infrastructure.runtime_transport_gateway import RuntimeTransportGateway


PROMPT_TOOLKIT_COLOR_MAP: dict[str, str] = {
    "black": "ansiblack",
    "red": "ansired",
    "green": "ansigreen",
    "yellow": "ansiyellow",
    "blue": "ansiblue",
    "magenta": "ansimagenta",
    "cyan": "ansicyan",
    "white": "ansiwhite",
    "bright_black": "ansibrightblack",
    "bright_red": "ansibrightred",
    "bright_green": "ansibrightgreen",
    "bright_yellow": "ansibrightyellow",
    "bright_blue": "ansibrightblue",
    "bright_magenta": "ansibrightmagenta",
    "bright_cyan": "ansibrightcyan",
    "bright_white": "ansibrightwhite",
}


def _should_use_legacy_windows_console(
    environ: dict[str, str] | None = None,
    os_name: str | None = None,
) -> bool:
    """Decide modo legacy para evitar artefactos ANSI en Windows."""
    env = environ if environ is not None else os.environ
    current_os_name = os_name if os_name is not None else os.name

    if current_os_name != "nt":
        return False

    if env.get("CLI_LEGACY_WINDOWS", "0") == "1":
        return True
    if env.get("CLI_FORCE_MODERN_TERMINAL", "0") == "1":
        return False

    modern_terminal_markers = (
        "WT_SESSION",
        "TERM_PROGRAM",
        "VSCODE_GIT_IPC_HANDLE",
        "PYCHARM_HOSTED",
    )
    if any(env.get(marker) for marker in modern_terminal_markers):
        return False

    term_value = env.get("TERM", "").lower()
    if any(token in term_value for token in ("xterm", "ansi", "cygwin", "linux")):
        return False

    return True


class CliApp:
    """Aplicación CLI síncrona con comando y chat persistente."""

    def __init__(
        self,
        controller: AppController,
        relay_url: str | None = None,
        transport_gateway_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._controller = controller
        self._console = Console(
            legacy_windows=_should_use_legacy_windows_console(),
            highlight=False,
        )
        self._session: PromptSession | None = None
        self._running = True
        self._current_user: str | None = None
        self._chat_target: str | None = None
        self._poll_enabled = True
        self._theme_name = "default"
        self._theme = get_theme(self._theme_name)
        self._prompt_style = self._build_prompt_toolkit_style()
        self._last_notification_fingerprint: str | None = None
        self._seen_transport_message_ids: deque[str] = deque(maxlen=256)
        self._exit_confirmation_pending = False
        self._last_status_snapshot: tuple[str, str, str, str, str] | None = None
        self._relay_url = relay_url
        self._transport_gateway = None
        self._background_poll_interval_seconds = 0.25
        self._background_poll_stop = threading.Event()
        self._background_poll_thread: threading.Thread | None = None
        if relay_url is not None:
            factory = transport_gateway_factory or RuntimeTransportGateway
            self._transport_gateway = factory(relay_url)

    def run(self) -> None:
        """Ejecuta loop principal interactivo."""
        if self._session is None:
            completer = _CliCompleter(
                get_commands=lambda: list(COMMANDS),
                get_themes=list_theme_names,
                get_usernames=self._list_known_usernames,
            )
            self._session = PromptSession(
                completer=completer,
                complete_while_typing=True,
            )

        self._render_welcome()
        self._start_background_polling()
        try:
            with patch_stdout(raw=True):
                while self._running:
                    self._poll_notifications()
                    self._render_status_bar_if_changed()
                    prompt = self._build_prompt()
                    try:
                        assert self._session is not None
                        line = self._session.prompt(
                            prompt,
                            style=self._prompt_style,
                        ).strip()
                    except (EOFError, KeyboardInterrupt):
                        self._running = False
                        continue

                    if not line:
                        continue

                    if line.startswith("/"):
                        self._handle_command(line)
                    else:
                        self._exit_confirmation_pending = False
                        self._handle_free_text(line)
        finally:
            self._stop_background_polling()

    def _build_prompt(self) -> FormattedText:
        if self._current_user is None:
            return FormattedText(
                [
                    ("class:prompt.user", "guest"),
                    ("class:prompt.meta", " > "),
                ]
            )
        if self._chat_target is not None:
            state = self._channel_state(self._current_user, self._chat_target)
            lock = self._theme.icon_lock
            state_colored = self._colored_state(state)
            return FormattedText(
                [
                    ("class:prompt.user", self._current_user),
                    ("class:prompt.meta", " @"),
                    ("class:prompt.target", self._chat_target),
                    ("class:prompt.meta", f" {lock}:"),
                    ("class:prompt.channel", state_colored),
                    ("class:prompt.meta", " > "),
                ]
            )
        return FormattedText(
            [
                ("class:prompt.user", self._current_user),
                ("class:prompt.meta", " > "),
            ]
        )

    def _build_status_bar(self) -> tuple[str, str, str, str, str]:
        user = self._current_user or "guest"
        chat = self._chat_target or "-"
        channel = (
            self._channel_state(self._current_user, self._chat_target)
            if self._current_user and self._chat_target
            else "N/A"
        )
        poll = "on" if self._poll_enabled else "off"
        return user, chat, channel, self._theme_name, poll

    def _render_status_bar_if_changed(self) -> None:
        snapshot = self._build_status_bar()
        if snapshot == self._last_status_snapshot:
            return

        self._last_status_snapshot = snapshot
        user, chat, channel, theme_name, poll = snapshot

        channel_style = self._theme.meta_style
        if channel == "ACTIVE":
            channel_style = self._theme.success_style
        elif channel == "ESTABLISHING":
            channel_style = self._theme.warning_style
        elif channel == "INVALID":
            channel_style = self._theme.error_style

        line = Text()
        line.append(f"{self._theme.icon_info} user=", style=self._theme.meta_style)
        line.append(user, style=self._theme.message_style)
        line.append(" | ", style=self._theme.meta_style)
        line.append("chat=", style=self._theme.meta_style)
        line.append(chat, style=self._theme.message_style)
        line.append(" | ", style=self._theme.meta_style)
        line.append("channel=", style=self._theme.meta_style)
        line.append(channel, style=channel_style)
        line.append(" | ", style=self._theme.meta_style)
        line.append("theme=", style=self._theme.meta_style)
        line.append(theme_name, style=self._theme.info_style)
        line.append(" | ", style=self._theme.meta_style)
        line.append("poll=", style=self._theme.meta_style)
        line.append(poll, style=self._theme.info_style)

        self._console.print(
            Panel(
                line,
                title="Estado",
                style=self._theme.panel_style,
                border_style=self._theme.meta_style,
                title_align="center",
            )
        )

    def _render_welcome(self) -> None:
        self._console.print(
            Panel(
                "CLI Secure Messenger\nUsa /help para ver comandos.",
                title="Bienvenido",
                style=self._theme.panel_style,
                border_style=self._theme.meta_style,
                title_align="center",
            )
        )
        self._print_hints()

    def _handle_command(self, line: str) -> None:
        parts = line.split()
        raw_cmd = parts[0].lower()
        cmd = self._resolve_command(raw_cmd)
        if cmd is None:
            self._print_line(format_warning(self._theme, "Comando no reconocido."))
            return

        if cmd != "/exit":
            self._exit_confirmation_pending = False

        if cmd == "/help":
            self._render_help()
            return
        if cmd == "/status":
            self._render_status()
            return
        if cmd == "/clear":
            self._console.clear()
            self._render_welcome()
            return
        if cmd == "/exit":
            if self._chat_target is not None and not self._exit_confirmation_pending:
                self._exit_confirmation_pending = True
                self._print_line(
                    format_warning(
                        self._theme,
                        f"Hay un chat activo con {self._chat_target}. Repite /exit para salir o usa /leave.",
                    )
                )
                return
            if self._transport_gateway is not None:
                self._transport_gateway.close()
            self._stop_background_polling()
            self._running = False
            self._print_line(
                format_info(self._theme, f"{self._theme.icon_exit} Saliendo...")
            )
            return
        if cmd == "/leave":
            self._chat_target = None
            self._print_line(format_info(self._theme, "Modo chat desactivado."))
            return
        if cmd == "/poll":
            self._handle_poll(parts)
            return
        if cmd == "/theme":
            self._handle_theme(parts)
            return
        if cmd == "/notif":
            self._print_notifications()
            return
        if cmd == "/user":
            self._handle_user(parts)
            return
        if cmd == "/logout":
            self._handle_logout(parts)
            return
        if cmd == "/users":
            self._handle_users()
            return
        if cmd == "/chat":
            self._handle_chat(parts)
            return
        if cmd == "/msg":
            self._handle_msg(parts)
            return

    def _handle_user(self, parts: list[str]) -> None:
        if len(parts) != 2:
            self._print_line(format_warning(self._theme, "Uso: /user <name>"))
            return

        username = parts[1]
        response = self._controller.register(self._build_register_message(username))
        if response["ok"]:
            self._current_user = username
            try:
                if self._transport_gateway is not None:
                    self._transport_gateway.connect(username)
                    self._transport_gateway.send_frame(
                        self._build_register_message(username)
                    )
            except RuntimeError:
                self._print_line(
                    format_warning(
                        self._theme,
                        "No se pudo conectar al relay configurado. Se mantiene modo local.",
                    )
                )
                self._transport_gateway = None
            self._print_line(format_event(self._theme, "REGISTERED", response["data"]))
        else:
            self._print_line(format_error(self._theme, response["error"]))

    def _handle_users(self) -> None:
        response = self._controller.list_users()
        if response["ok"]:
            self._print_line(
                format_info(self._theme, f"{self._theme.icon_users} Estado de usuarios")
            )
            table = build_users_table(self._theme, response["data"].get("users", []))
            self._console.print(table)
        else:
            self._print_line(format_error(self._theme, response["error"]))

    def _handle_logout(self, parts: list[str]) -> None:
        if len(parts) != 1:
            self._print_line(format_warning(self._theme, "Uso: /logout"))
            return
        if self._current_user is None:
            self._print_line(format_warning(self._theme, "No hay sesión activa."))
            return

        username = self._current_user
        response = self._controller.disconnect(username)
        self._chat_target = None
        self._current_user = None
        if response["ok"]:
            self._print_line(
                format_event(self._theme, "DISCONNECTED", response["data"])
            )
        else:
            self._print_line(format_error(self._theme, response["error"]))
        if self._transport_gateway is not None:
            self._transport_gateway.close()

    def _handle_chat(self, parts: list[str]) -> None:
        if self._current_user is None:
            self._print_line(
                format_warning(
                    self._theme, "Debes registrarte con /user <name> primero."
                )
            )
            return
        if len(parts) != 2:
            self._print_line(format_warning(self._theme, "Uso: /chat <user>"))
            return

        target = parts[1]
        if target == self._current_user:
            self._print_line(
                format_warning(
                    self._theme,
                    "No puedes iniciar chat contigo mismo. Usa otro usuario.",
                )
            )
            return

        self._ensure_known_transport_user(target)

        status = self._user_status(target)
        if status == "missing":
            self._print_line(
                format_warning(
                    self._theme,
                    f"No es posible iniciar chat: '{target}' no existe en el runtime actual.",
                )
            )
            return
        if status != "online":
            self._print_line(
                format_warning(
                    self._theme,
                    f"No es posible iniciar chat: '{target}' está desconectado.",
                )
            )
            return

        self._chat_target = target
        self._print_line(format_info(self._theme, f"Chat activo con {target}"))

        channel_state = self._channel_state(self._current_user, target)
        if channel_state == "ACTIVE":
            self._print_line(
                format_info(self._theme, f"Canal seguro ya activo con {target}.")
            )
            return
        if channel_state == "ESTABLISHING":
            self._print_line(
                format_info(
                    self._theme,
                    f"Canal seguro en establecimiento con {target}. Esperando confirmación...",
                )
            )
            return

        hs_response = self._controller.handshake_init(
            self._build_handshake_message(self._current_user, target),
            now_seconds=self._now_seconds(),
        )
        if hs_response["ok"]:
            self._print_line(
                format_event(self._theme, "HANDSHAKE_STARTED", hs_response["data"])
            )
            self._start_remote_handshake(target)
        else:
            self._print_line(format_error(self._theme, hs_response["error"]))

    def _handle_msg(self, parts: list[str]) -> None:
        if self._current_user is None:
            self._print_line(
                format_warning(
                    self._theme, "Debes registrarte con /user <name> primero."
                )
            )
            return
        if len(parts) < 3:
            self._print_line(format_warning(self._theme, "Uso: /msg <user> <texto>"))
            return

        target = parts[1]
        text = " ".join(parts[2:])

        if target == self._current_user:
            self._print_line(
                format_warning(
                    self._theme,
                    "No puedes enviarte mensajes a ti mismo.",
                )
            )
            return

        self._ensure_known_transport_user(target)

        status = self._user_status(target)
        if status == "missing":
            self._print_line(
                format_warning(
                    self._theme,
                    f"No es posible enviar mensaje: '{target}' no existe en el runtime actual.",
                )
            )
            return
        if status != "online":
            self._print_line(
                format_warning(
                    self._theme,
                    f"No es posible enviar mensaje: '{target}' está desconectado.",
                )
            )
            return

        response = self._controller.send_text_message(
            self._current_user,
            target,
            text,
            now_seconds=self._now_seconds(),
        )
        self._print_send_response(response)

    def _handle_free_text(self, line: str) -> None:
        if self._current_user is None:
            self._print_line(
                format_warning(
                    self._theme, "Debes registrarte con /user <name> primero."
                )
            )
            return
        if self._chat_target is None:
            self._print_line(
                format_warning(
                    self._theme,
                    "No hay chat activo. Usa /chat <user> o /msg <user> <texto>.",
                )
            )
            return

        response = self._controller.send_text_message(
            self._current_user,
            self._chat_target,
            line,
            now_seconds=self._now_seconds(),
        )
        self._print_send_response(response)

    def _print_send_response(self, response: dict) -> None:
        if response["ok"]:
            self._send_message_frame(response["data"])
            return

        self._print_line(format_error(self._theme, response["error"]))
        data = response.get("data")
        if isinstance(data, dict) and data.get("event") == "HANDSHAKE_STARTED":
            self._print_line(format_event(self._theme, "HANDSHAKE_STARTED", data))
            target = data.get("to")
            if isinstance(target, str):
                self._start_remote_handshake(target)

    def _handle_poll(self, parts: list[str]) -> None:
        if len(parts) != 2 or parts[1] not in {"on", "off"}:
            self._print_line(format_warning(self._theme, "Uso: /poll on|off"))
            return
        self._poll_enabled = parts[1] == "on"
        text = (
            "Polling de notificaciones activado."
            if self._poll_enabled
            else "Polling de notificaciones desactivado."
        )
        self._print_line(format_info(self._theme, text))

    def _handle_theme(self, parts: list[str]) -> None:
        if len(parts) != 2:
            self._print_line(
                format_warning(
                    self._theme,
                    f"Uso: /theme <nombre>. Disponibles: {', '.join(list_theme_names())}",
                )
            )
            return

        name = parts[1]
        if name not in list_theme_names():
            self._print_line(
                format_warning(
                    self._theme,
                    f"Tema inválido. Disponibles: {', '.join(list_theme_names())}",
                )
            )
            return

        self._theme_name = name
        self._theme = get_theme(name)
        self._prompt_style = self._build_prompt_toolkit_style()
        self._print_line(format_success(self._theme, f"Tema activo: {name}"))

    def _render_help(self) -> None:
        from rich.table import Table

        table = Table(
            title=f"{self._theme.icon_help} Comandos",
            header_style=self._theme.table_header_style,
            border_style=self._theme.meta_style,
            title_style=self._theme.table_header_style,
        )
        table.add_column("Comando", style=self._theme.message_style)
        table.add_column("Descripción", style=self._theme.meta_style)

        table.add_row("/user <name>", "Registra usuario local")
        table.add_row("/logout", "Cierra sesión local")
        table.add_row("/users", "Lista usuarios con estado")
        table.add_row("/chat <user>", "Entra a chat persistente e inicia handshake")
        table.add_row("/msg <user> <texto>", "Envía mensaje directo")
        table.add_row("/notif", "Lee notificaciones pendientes")
        table.add_row("/poll on|off", "Activa/desactiva polling")
        table.add_row(
            "/theme <nombre>",
            f"Selecciona tema ({', '.join(list_theme_names())})",
        )
        table.add_row("/leave", "Sale del chat actual")
        table.add_row("/help", "Muestra ayuda")
        table.add_row("/status", "Muestra diagnóstico detallado del runtime")
        table.add_row("/clear", "Limpia la pantalla")
        table.add_row("/exit", "Salir")
        self._console.print(table)

    def _render_status(self) -> None:
        from rich.table import Table

        table = Table(
            title="Diagnóstico actual",
            header_style=self._theme.table_header_style,
            border_style=self._theme.meta_style,
            title_style=self._theme.table_header_style,
        )
        table.add_column("Campo", style=self._theme.message_style)
        table.add_column("Valor", style=self._theme.meta_style)

        diagnostics = self._status_diagnostics()
        table.add_row("Sesión", diagnostics["session"])
        table.add_row("Usuarios runtime", diagnostics["runtime_users"])
        table.add_row("Usuarios online", diagnostics["online_users"])
        table.add_row("Chat activo", diagnostics["chat_active"])
        table.add_row("Destino actual", diagnostics["target"])
        table.add_row("Estado del destino", diagnostics["target_status"])
        table.add_row("Canal con destino", diagnostics["channel"])
        table.add_row("Tema", diagnostics["theme"])
        table.add_row("Polling", diagnostics["polling"])
        self._console.print(table)

    def _print_notifications(self) -> None:
        self._drain_transport_frames()
        if self._current_user is None:
            return
        response = self._controller.pull_notifications(self._current_user)
        if not response["ok"]:
            self._print_line(format_error(self._theme, response["error"]))
            return

        for message in response["data"].get("notifications", []):
            fingerprint = self._notification_fingerprint(message)
            if fingerprint == self._last_notification_fingerprint:
                continue
            self._last_notification_fingerprint = fingerprint
            self._print_line(format_notification(self._theme, message))

    def _poll_notifications(self) -> None:
        if not self._poll_enabled or self._current_user is None:
            return
        self._print_notifications()

    def _start_background_polling(self, interval_seconds: float | None = None) -> None:
        if self._background_poll_thread is not None:
            return
        if interval_seconds is not None:
            self._background_poll_interval_seconds = interval_seconds

        self._background_poll_stop.clear()
        self._background_poll_thread = threading.Thread(
            target=self._background_poll_loop,
            name="cli-background-poll",
            daemon=True,
        )
        self._background_poll_thread.start()

    def _stop_background_polling(self) -> None:
        thread = self._background_poll_thread
        if thread is None:
            return

        self._background_poll_stop.set()
        thread.join(timeout=1.0)
        self._background_poll_thread = None

    def _background_poll_loop(self) -> None:
        while not self._background_poll_stop.wait(
            self._background_poll_interval_seconds
        ):
            try:
                self._poll_notifications()
            except Exception:  # pragma: no cover - defensivo para no matar thread
                continue

    def _send_message_frame(self, payload: dict[str, Any]) -> None:
        if self._transport_gateway is None or self._current_user is None:
            return
        target = payload.get("to")
        if not isinstance(target, str):
            return
        frame = {
            "message_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "type": "MESSAGE",
            "from": self._current_user,
            "to": target,
            "payload": payload.get("payload", {}),
        }
        self._transport_gateway.send_frame(frame)

    def _start_remote_handshake(self, target: str) -> None:
        if self._transport_gateway is None or self._current_user is None:
            return
        offer = self._controller.create_handshake_offer(
            self._current_user,
            target,
            now_seconds=self._now_seconds(),
        )
        if offer.get("ok"):
            self._transport_gateway.send_frame(offer["data"]["frame"])

    def _drain_transport_frames(self) -> None:
        if self._transport_gateway is None:
            return

        for frame in self._transport_gateway.poll_incoming():
            frame_type = frame.get("type")
            if frame_type == "REGISTER":
                remote = frame.get("from")
                if isinstance(remote, str) and remote != self._current_user:
                    self._ensure_known_transport_user(remote)
                continue

            if frame_type == "HANDSHAKE_INIT":
                remote = frame.get("from")
                if (
                    isinstance(remote, str)
                    and remote != self._current_user
                    and self._chat_target is None
                ):
                    self._chat_target = remote
                result = self._controller.process_handshake_frame(
                    frame,
                    now_seconds=self._now_seconds(),
                )
                if result.get("ok"):
                    reply = result.get("data", {}).get("frame")
                    if isinstance(reply, dict):
                        self._transport_gateway.send_frame(reply)
                else:
                    self._print_line(format_error(self._theme, result["error"]))
                continue

            if frame_type == "MESSAGE":
                message_id = frame.get("message_id")
                if isinstance(message_id, str) and self._is_duplicate_transport_message(
                    message_id
                ):
                    continue
                sender = frame.get("from")
                if isinstance(sender, str):
                    self._ensure_known_transport_user(sender)
                    if sender != self._current_user and self._chat_target is None:
                        self._chat_target = sender
                result = self._controller.receive_message(
                    frame,
                    now_seconds=self._now_seconds(),
                )
                if result.get("ok"):
                    sender = result["data"].get("from", "?")
                    plaintext = result["data"].get("plaintext", "")
                    self._print_line(
                        f"[{self._theme.info_style}]{sender}:[/{self._theme.info_style}] {plaintext}"
                    )
                else:
                    self._print_line(format_error(self._theme, result["error"]))

    def _is_duplicate_transport_message(self, message_id: str) -> bool:
        if message_id in self._seen_transport_message_ids:
            return True

        self._seen_transport_message_ids.append(message_id)
        return False

    def _ensure_known_transport_user(self, username: str) -> None:
        if self._transport_gateway is None:
            return
        if self._user_status(username) != "missing":
            return
        self._controller.register(self._build_register_message(username))

    def _user_status(self, username: str) -> str:
        response = self._controller.list_users()
        if not response["ok"]:
            return "missing"
        users = response["data"].get("users", [])
        for user in users:
            if user.get("username") == username:
                return str(user.get("state", "offline"))
        return "missing"

    def _list_known_usernames(self) -> list[str]:
        response = self._controller.list_users()
        if not response.get("ok"):
            return []
        users = response["data"].get("users", [])
        known: list[str] = []
        for user in users:
            username = str(user.get("username", ""))
            if not username:
                continue
            if self._current_user is not None and username == self._current_user:
                continue
            if str(user.get("state", "offline")) != "online":
                continue
            known.append(username)
        return sorted(known)

    def _status_diagnostics(self) -> dict[str, str]:
        return build_status_diagnostics(
            list_users=self._controller.list_users,
            current_user=self._current_user,
            chat_target=self._chat_target,
            user_status=self._user_status,
            channel_state=self._channel_state,
            theme_name=self._theme_name,
            poll_enabled=self._poll_enabled,
        )

    def _resolve_command(self, raw_command: str) -> str | None:
        return resolve_command(raw_command, COMMANDS)

    def _build_prompt_toolkit_style(self) -> Style:
        return Style.from_dict(
            {
                "prompt.user": self._rich_style_to_prompt_style(
                    self._theme.message_style
                ),
                "prompt.target": self._rich_style_to_prompt_style(
                    self._theme.info_style
                ),
                "prompt.meta": self._rich_style_to_prompt_style(self._theme.meta_style),
                "prompt.channel": self._rich_style_to_prompt_style(
                    self._theme.warning_style
                ),
            }
        )

    def _rich_style_to_prompt_style(self, rich_style: str) -> str:
        style_text = rich_style.strip()
        if not style_text:
            return ""

        if style_text == "dim":
            return "fg:ansibrightblack"

        if " on " in style_text:
            fg_raw, bg_raw = style_text.split(" on ", 1)
            fg = fg_raw.strip().split()[-1]
            bg = bg_raw.strip().split()[-1]
            fg_style = PROMPT_TOOLKIT_COLOR_MAP.get(fg, "ansiwhite")
            bg_style = PROMPT_TOOLKIT_COLOR_MAP.get(bg, "ansiblack")
            return f"fg:{fg_style} bg:{bg_style}"

        tokens = style_text.split()
        color_token = tokens[-1]
        color_style = PROMPT_TOOLKIT_COLOR_MAP.get(color_token)
        if color_style is None:
            return "fg:ansiwhite"
        return f"fg:{color_style}"

    def _build_register_message(self, username: str) -> dict:
        return {
            "message_id": "f8215ae4-a9d5-4434-ae54-3cc676db7ce0",
            "timestamp": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "type": "REGISTER",
            "from": username,
            "payload": {
                "username": username,
                "public_key": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...",
            },
        }

    def _build_handshake_message(self, sender: str, target: str) -> dict:
        return {
            "message_id": "15ceec6f-6f45-45f2-a2b8-17f40f53c295",
            "timestamp": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "type": "HANDSHAKE_INIT",
            "from": sender,
            "to": target,
            "payload": {
                "username": sender,
                "public_key": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...",
                "nonce": "YjRjNDY2ZjQwYw",
                "reason": "ON_DEMAND",
            },
        }

    def _now_seconds(self) -> int:
        return int(datetime.now(timezone.utc).timestamp())

    def _channel_state(self, sender: str, target: str) -> str:
        response = self._controller.get_channel_state(sender, target)
        if response.get("ok"):
            return str(response["data"].get("state", "NONE"))
        return "NONE"

    def _notification_fingerprint(self, message: dict) -> str:
        payload = message.get("payload", {})
        code = payload.get("code", "UNKNOWN")
        details = payload.get("details", {})
        return f"{code}|{details}"

    def _print_line(self, text: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        prefix = (
            f"[{self._theme.timestamp_style}][{ts}][/{self._theme.timestamp_style}]"
        )
        self._console.print(f"{prefix} {text}")

    def _print_hints(self) -> None:
        if self._current_user is None:
            self._print_line(
                format_info(
                    self._theme,
                    "Tip: inicia con /user <name>. Luego usa /users y /chat <user>.",
                )
            )
            return
        if self._chat_target is None:
            self._print_line(
                format_info(
                    self._theme,
                    "Tip: usa /chat <user> para modo chat o /msg <user> <texto>.",
                )
            )

    def _colored_state(self, state: str) -> str:
        if state == "ACTIVE":
            return "[ACTIVE]"
        if state == "ESTABLISHING":
            return "[ESTABLISHING]"
        if state == "INVALID":
            return "[INVALID]"
        return "[NONE]"


class _CliCompleter(Completer):
    """Autocompletado contextual de comandos y argumentos."""

    def __init__(self, get_commands, get_themes, get_usernames) -> None:
        self._get_commands = get_commands
        self._get_themes = get_themes
        self._get_usernames = get_usernames

    def get_completions(self, document: Document, complete_event):
        _ = complete_event
        text = document.text_before_cursor

        if text.startswith("/theme "):
            prefix = text.split(" ", 1)[1]
            yield from self._complete(prefix, self._get_themes())
            return

        if text.startswith("/poll "):
            prefix = text.split(" ", 1)[1]
            yield from self._complete(prefix, ["on", "off"])
            return

        if text.startswith("/chat "):
            prefix = text.split(" ", 1)[1]
            yield from self._complete(prefix, self._get_usernames())
            return

        if text.startswith("/msg "):
            parts = text.strip().split()
            if len(parts) == 2:
                prefix = parts[1]
                yield from self._complete(prefix, self._get_usernames())
            return

        if text.startswith("/") and " " not in text:
            yield from self._complete(text, self._get_commands())

    def _complete(self, prefix: str, values: Iterable[str]):
        prefix_lower = prefix.lower()
        for value in values:
            if value.lower().startswith(prefix_lower):
                yield Completion(value, start_position=-len(prefix))
