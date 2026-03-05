# app/routing/circuit_breaker.py
from __future__ import annotations
from dataclasses import dataclass
import time
from typing import Dict, Tuple

Key = Tuple[str, str]  # (provider, model)

@dataclass
class BreakerState:
    failures: int = 0
    open_until: float = 0.0  # epoch seconds

class CircuitBreaker:
    """
    Simple circuit breaker:
    - after N failures, open for cooldown seconds
    - success resets failures
    """
    def __init__(self, failure_threshold: int = 3, cooldown_s: int = 20):
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self._state: Dict[Key, BreakerState] = {}

    def allow(self, provider: str, model: str) -> bool:
        st = self._state.get((provider, model))
        if not st:
            return True
        if st.open_until <= 0:
            return True
        return time.time() >= st.open_until

    def record_success(self, provider: str, model: str) -> None:
        self._state[(provider, model)] = BreakerState(failures=0, open_until=0.0)

    def record_failure(self, provider: str, model: str) -> None:
        st = self._state.get((provider, model)) or BreakerState()
        st.failures += 1
        if st.failures >= self.failure_threshold:
            st.open_until = time.time() + self.cooldown_s
        self._state[(provider, model)] = st

breaker = CircuitBreaker()