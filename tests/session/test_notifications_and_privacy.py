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
def test_register_rejection_is_privacy_preserving(service: SessionUserService):
    service.register("alice")
    _, err = service.register("alice")

    assert err is not None
    _assert_structured_error(err, "409_USERNAME_TAKEN", "alice")
    assert err["payload"]["message"] == "No se pudo completar la operación solicitada."
    assert set(err["payload"]["details"].keys()) <= {"operation"}
