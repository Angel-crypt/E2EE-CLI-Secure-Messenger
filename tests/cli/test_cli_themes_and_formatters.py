import pytest
import time
from prompt_toolkit.document import Document
from prompt_toolkit.completion.base import CompleteEvent

from app.app_controller import AppController
from cli.cli_app import CliApp, _CliCompleter, _should_use_legacy_windows_console
from cli.formatters import build_users_table, format_error
from cli.themes import get_theme, list_theme_names


@pytest.mark.unit
def test_theme_catalog_has_expected_presets():
    names = list_theme_names()
    assert "default" in names
    assert "minimal" in names
    assert "matrix" in names


@pytest.mark.unit
def test_error_formatter_maps_code_to_spanish_message():
    theme = get_theme("default")
    message = {
        "type": "ERROR",
        "from": "server",
        "to": "alice",
        "payload": {
            "code": "404_USER_OFFLINE",
            "message": "x",
            "details": {},
            "retriable": True,
        },
    }
    rendered = format_error(theme, message)
    assert "404_USER_OFFLINE" in rendered
    assert "no está disponible" in rendered


@pytest.mark.unit
def test_cli_can_select_theme_and_activate_chat():
    cli = CliApp(AppController())

    cli._handle_user(["/user", "alice"])
    cli._controller.register(cli._build_register_message("bob"))

    cli._handle_theme(["/theme", "matrix"])
    assert cli._theme_name == "matrix"

    cli._handle_chat(["/chat", "bob"])
    assert cli._chat_target == "bob"


@pytest.mark.unit
def test_cli_logout_disconnects_user_and_clears_chat_target():
    cli = CliApp(AppController())

    cli._handle_user(["/user", "alice"])
    cli._controller.register(cli._build_register_message("bob"))
    cli._handle_chat(["/chat", "bob"])

    assert cli._current_user == "alice"
    assert cli._chat_target == "bob"

    cli._handle_logout(["/logout"])

    assert cli._current_user is None
    assert cli._chat_target is None
    users = cli._controller.list_users()["data"]["users"]
    alice = next(user for user in users if user["username"] == "alice")
    assert alice["state"] == "offline"


@pytest.mark.unit
def test_cli_prevents_chat_with_self():
    cli = CliApp(AppController())
    cli._handle_user(["/user", "alice"])

    cli._handle_chat(["/chat", "alice"])

    assert cli._chat_target is None


@pytest.mark.unit
def test_cli_prevents_direct_message_to_self():
    cli = CliApp(AppController())
    cli._handle_user(["/user", "alice"])

    cli._handle_msg(["/msg", "alice", "hola"])

    pulled = cli._controller.pull_notifications("alice")
    assert pulled["ok"] is True
    assert pulled["data"]["notifications"] == []


@pytest.mark.unit
def test_completer_for_msg_works_with_extra_spaces():
    completer = _CliCompleter(
        get_commands=lambda: ["/msg"],
        get_themes=lambda: ["default"],
        get_usernames=lambda: ["bob", "carol"],
    )

    doc = Document(text="/msg    b", cursor_position=len("/msg    b"))
    labels = [
        c.text
        for c in completer.get_completions(doc, CompleteEvent(text_inserted=True))
    ]

    assert "bob" in labels


@pytest.mark.unit
def test_cli_resolves_unique_prefix_command_with_slash():
    cli = CliApp(AppController())

    resolved = cli._resolve_command("/st")

    assert resolved == "/status"


@pytest.mark.unit
def test_cli_resolves_ambiguous_prefix_to_first_command():
    cli = CliApp(AppController())

    resolved = cli._resolve_command("/u")

    assert resolved == "/user"


@pytest.mark.unit
def test_cli_rejects_command_without_slash():
    cli = CliApp(AppController())

    resolved = cli._resolve_command("status")

    assert resolved is None


@pytest.mark.unit
def test_users_table_uses_theme_styles_for_consistency():
    theme = get_theme("matrix")

    table = build_users_table(
        theme,
        [
            {"username": "alice", "state": "online"},
            {"username": "bob", "state": "offline"},
        ],
    )

    assert str(table.border_style) == theme.meta_style
    assert str(table.header_style) == theme.table_header_style


@pytest.mark.unit
def test_prompt_style_mapping_is_portable_across_themes():
    cli = CliApp(AppController())

    assert cli._rich_style_to_prompt_style("dim") == "fg:ansibrightblack"
    assert (
        cli._rich_style_to_prompt_style("white on black") == "fg:ansiwhite bg:ansiblack"
    )
    assert cli._rich_style_to_prompt_style("bright_cyan") == "fg:ansibrightcyan"


@pytest.mark.unit
def test_status_diagnostics_has_runtime_specific_fields_without_duplication():
    cli = CliApp(AppController())

    diagnostics = cli._status_diagnostics()

    assert diagnostics["session"] == "sin registrar"
    assert diagnostics["runtime_users"] == "0"
    assert diagnostics["online_users"] == "0"
    assert diagnostics["chat_active"] == "no"
    assert diagnostics["target"] == "(sin chat activo)"
    assert diagnostics["target_status"] == "N/A"
    assert diagnostics["channel"] == "N/A"


@pytest.mark.unit
def test_status_diagnostics_with_active_chat_uses_target_and_channel_status():
    cli = CliApp(AppController())

    cli._handle_user(["/user", "alice"])
    cli._controller.register(cli._build_register_message("bob"))
    cli._handle_chat(["/chat", "bob"])

    diagnostics = cli._status_diagnostics()

    assert diagnostics["session"] == "registrado"
    assert diagnostics["runtime_users"] == "2"
    assert diagnostics["online_users"] == "2"
    assert diagnostics["chat_active"] == "sí"
    assert diagnostics["target"] == "bob"
    assert diagnostics["target_status"] == "online"
    assert diagnostics["channel"] in {"ESTABLISHING", "ACTIVE", "INVALID", "NONE"}


@pytest.mark.unit
def test_legacy_windows_enabled_on_plain_windows_shell():
    env = {}

    legacy = _should_use_legacy_windows_console(env, os_name="nt")

    assert legacy is True


@pytest.mark.unit
def test_legacy_windows_disabled_on_modern_windows_terminal():
    env = {"WT_SESSION": "1"}

    legacy = _should_use_legacy_windows_console(env, os_name="nt")

    assert legacy is False


@pytest.mark.unit
def test_legacy_windows_env_override_is_respected():
    env = {"CLI_LEGACY_WINDOWS": "1", "WT_SESSION": "1"}

    legacy = _should_use_legacy_windows_console(env, os_name="nt")

    assert legacy is True


@pytest.mark.unit
def test_cli_register_connects_transport_when_gateway_is_configured(monkeypatch):
    connected: list[str] = []

    class _FakeGateway:
        def connect(self, username: str) -> None:
            connected.append(username)

        def close(self) -> None:
            return None

        def send_frame(self, frame: dict) -> None:
            return None

        def poll_incoming(self) -> list[dict]:
            return []

    cli = CliApp(
        AppController(),
        relay_url="ws://127.0.0.1:8765",
        transport_gateway_factory=lambda _url: _FakeGateway(),
    )

    cli._handle_user(["/user", "alice"])

    assert connected == ["alice"]


@pytest.mark.unit
def test_cli_register_without_gateway_keeps_legacy_local_flow():
    cli = CliApp(AppController())

    cli._handle_user(["/user", "alice"])

    assert cli._current_user == "alice"


@pytest.mark.unit
def test_background_polling_loop_triggers_notifications_without_manual_notif():
    cli = CliApp(AppController())
    cli._current_user = "alice"

    calls = {"count": 0}

    def _fake_print_notifications() -> None:
        calls["count"] += 1

    cli._print_notifications = _fake_print_notifications  # type: ignore[method-assign]

    cli._start_background_polling(interval_seconds=0.05)
    try:
        time.sleep(0.16)
    finally:
        cli._stop_background_polling()

    assert calls["count"] >= 2


@pytest.mark.unit
def test_background_polling_respects_poll_off_and_does_not_spam():
    cli = CliApp(AppController())
    cli._current_user = "alice"
    cli._poll_enabled = False

    calls = {"count": 0}

    def _fake_print_notifications() -> None:
        calls["count"] += 1

    cli._print_notifications = _fake_print_notifications  # type: ignore[method-assign]

    cli._start_background_polling(interval_seconds=0.05)
    try:
        time.sleep(0.16)
    finally:
        cli._stop_background_polling()

    assert calls["count"] == 0


@pytest.mark.unit
def test_drain_transport_frames_skips_duplicate_message_ids():
    class _FakeGateway:
        def __init__(self) -> None:
            self._first = True

        def poll_incoming(self) -> list[dict]:
            if not self._first:
                return []
            self._first = False
            frame = {
                "message_id": "dup-1",
                "type": "MESSAGE",
                "from": "bob",
                "to": "alice",
                "payload": {"ciphertext": "x", "algorithm": "FERNET"},
                "timestamp": "2026-01-01T00:00:00Z",
            }
            return [frame, frame]

    cli = CliApp(AppController())
    cli._current_user = "alice"
    cli._transport_gateway = _FakeGateway()

    printed: list[str] = []
    cli._print_line = lambda text: printed.append(text)  # type: ignore[method-assign]
    cli._ensure_known_transport_user = (  # type: ignore[method-assign]
        lambda _username: None
    )
    cli._controller.receive_message = lambda _frame, now_seconds=None: {  # type: ignore[method-assign]
        "ok": True,
        "data": {"from": "bob", "plaintext": "hola"},
    }

    cli._drain_transport_frames()

    rendered_messages = [line for line in printed if "bob:" in line and "hola" in line]
    assert len(rendered_messages) == 1


@pytest.mark.unit
def test_drain_handshake_auto_assigns_chat_target_when_missing():
    class _FakeGateway:
        def poll_incoming(self) -> list[dict]:
            return [
                {
                    "message_id": "hs-1",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "type": "HANDSHAKE_INIT",
                    "from": "bob",
                    "to": "alice",
                    "payload": {
                        "username": "bob",
                        "public_key": "pub",
                        "nonce": "n1",
                        "reason": "ON_DEMAND",
                    },
                }
            ]

        def send_frame(self, frame: dict) -> None:
            _ = frame

    cli = CliApp(AppController())
    cli._current_user = "alice"
    cli._chat_target = None
    cli._transport_gateway = _FakeGateway()
    cli._controller.register(cli._build_register_message("bob"))
    cli._controller.process_handshake_frame = lambda frame, now_seconds=None: {  # type: ignore[method-assign]
        "ok": True,
        "data": {"event": "HANDSHAKE_COMPLETED", "frame": None},
    }

    cli._drain_transport_frames()

    assert cli._chat_target == "bob"


@pytest.mark.unit
def test_drain_message_auto_assigns_chat_target_when_missing():
    class _FakeGateway:
        def poll_incoming(self) -> list[dict]:
            return [
                {
                    "message_id": "msg-1",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "type": "MESSAGE",
                    "from": "bob",
                    "to": "alice",
                    "payload": {
                        "ciphertext": "x",
                        "algorithm": "FERNET",
                        "encoding": "base64url",
                        "nonce": "n1",
                        "sent_at": "2026-01-01T00:00:00Z",
                    },
                }
            ]

    cli = CliApp(AppController())
    cli._current_user = "alice"
    cli._chat_target = None
    cli._transport_gateway = _FakeGateway()
    cli._controller.register(cli._build_register_message("bob"))
    cli._controller.receive_message = lambda _frame, now_seconds=None: {  # type: ignore[method-assign]
        "ok": True,
        "data": {"from": "bob", "plaintext": "hola"},
    }
    cli._print_line = lambda _text: None  # type: ignore[method-assign]

    cli._drain_transport_frames()

    assert cli._chat_target == "bob"
