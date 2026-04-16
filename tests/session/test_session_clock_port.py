import pytest

from app.interfaces import ClockPort
from app.services.key_exchange_service import KeyExchangeService
from app.services.user_service import SessionUserService


class FixedClock(ClockPort):
    def __init__(self, value: int) -> None:
        self._value = value

    def now_seconds(self) -> int:
        return self._value


class SpyKeyExchange(KeyExchangeService):
    def __init__(self) -> None:
        super().__init__(timeout_seconds=5)
        self.last_invalidated: tuple[str, int | None] | None = None

    def invalidate_user_channels(
        self, username: str, now_seconds: int | None = None
    ) -> None:
        self.last_invalidated = (username, now_seconds)
        super().invalidate_user_channels(username, now_seconds)


@pytest.mark.unit
def test_session_service_uses_clock_port_on_disconnect():
    clock = FixedClock(123)
    key_exchange = SpyKeyExchange()
    service = SessionUserService(key_exchange_service=key_exchange, clock=clock)

    service.register("alice")
    assert (
        key_exchange.last_invalidated is None
    )  # register no longer invalidates channels

    service.disconnect("alice")
    assert key_exchange.last_invalidated == ("alice", 123)
