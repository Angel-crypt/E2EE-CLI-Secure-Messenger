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

    pair = service._pair_key("alice", "bob")
    assert service._channels[pair]["started_at"] == 10
