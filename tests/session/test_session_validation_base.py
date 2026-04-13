import pytest

from app.protocol import validate_message
from app.services.user_service import SessionUserService


@pytest.fixture
def service() -> SessionUserService:
    return SessionUserService()


def _assert_structured_error(
    error_message: dict, expected_code: str, expected_to: str
) -> None:
    validated = validate_message(error_message)
    assert validated["type"] == "ERROR"
    assert validated["from"] == "server"
    assert validated.get("to") == expected_to
    assert validated["payload"]["code"] == expected_code


@pytest.mark.unit
def test_single_session_per_user_rejects_second_register(service: SessionUserService):
    ok_first, err_first = service.register("alice")
    ok_second, err_second = service.register("alice")

    assert ok_first is True
    assert err_first is None
    assert ok_second is False
    assert err_second is not None
    _assert_structured_error(err_second, "409_USERNAME_TAKEN", "alice")


@pytest.mark.unit
def test_user_disconnect_sets_offline_state(service: SessionUserService):
    service.register("alice")
    service.disconnect("alice")

    users = service.list_users()
    by_name = {item["username"]: item["state"] for item in users}

    assert by_name["alice"] == "offline"


@pytest.mark.unit
def test_users_returns_username_and_state(service: SessionUserService):
    service.register("alice")
    service.register("bob")
    service.disconnect("bob")

    users = service.list_users()

    assert isinstance(users, list)
    assert all(set(item.keys()) == {"username", "state"} for item in users)

    by_name = {item["username"]: item["state"] for item in users}
    assert by_name["alice"] == "online"
    assert by_name["bob"] == "offline"


@pytest.mark.unit
def test_no_ttl_presence_depends_on_real_connection(service: SessionUserService):
    service.register("alice")

    users = service.list_users()
    by_name = {item["username"]: item["state"] for item in users}

    assert by_name["alice"] == "online"
