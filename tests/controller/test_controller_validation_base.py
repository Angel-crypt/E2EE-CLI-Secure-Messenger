import pytest
from datetime import datetime, timezone

from app.app_controller import AppController


def _register_msg(username: str) -> dict:
    now_iso = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return {
        "message_id": "f8215ae4-a9d5-4434-ae54-3cc676db7ce0",
        "timestamp": now_iso,
        "type": "REGISTER",
        "from": username,
        "payload": {
            "username": username,
            "public_key": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...",
        },
    }


@pytest.fixture
def controller() -> AppController:
    return AppController()


@pytest.mark.unit
def test_register_valid_message_creates_user(controller: AppController):
    result = controller.register(_register_msg("alice"))
    assert result["ok"] is True
    assert result["data"]["event"] == "REGISTERED"


@pytest.mark.unit
def test_register_duplicate_returns_409(controller: AppController):
    controller.register(_register_msg("alice"))
    result = controller.register(_register_msg("alice"))

    assert result["ok"] is False
    assert result["error"]["payload"]["code"] == "409_USERNAME_TAKEN"


@pytest.mark.unit
def test_list_users_returns_username_and_state(controller: AppController):
    controller.register(_register_msg("alice"))
    response = controller.list_users()

    assert response["ok"] is True
    users = response["data"]["users"]
    assert users == [{"username": "alice", "state": "online"}]
