import pytest

from app.interfaces import ClockPort
from app.services.key_exchange_service import KeyExchangeService


class MutableClock(ClockPort):
    def __init__(self, value: int) -> None:
        self.value = value

    def now_seconds(self) -> int:
        return self.value


@pytest.mark.unit
def test_key_exchange_uses_clock_when_now_not_provided():
    clock = MutableClock(10)
    service = KeyExchangeService(timeout_seconds=5, clock=clock)

    service.start_handshake("alice", "bob")
    assert service.channel_state("alice", "bob") == "ESTABLISHING"

    clock.value = 16
    timed_out, error = service.check_timeout("alice", "bob")

    assert timed_out is True
    assert error is not None
    assert error["payload"]["code"] == "504_KEY_EXCHANGE_TIMEOUT"
