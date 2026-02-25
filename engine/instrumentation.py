"""Search instrumentation models and throttled emission."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Callable


@dataclass(slots=True)
class SearchSnapshot:
    depth: int
    nodes: int
    nps: int
    current_move: str
    pv: list[str]
    eval: float
    eval_cp: int
    candidate_moves: dict[str, float]
    piece_values: dict[str, int]
    piece_breakdown: dict[str, dict[str, int | str]]
    heatmap: dict[str, int]
    cutoffs: int
    elapsed_ms: float

    def to_dict(self) -> dict:
        return asdict(self)


class SnapshotThrottle:
    """Emit snapshots at a bounded rate to avoid overloading websocket clients."""

    def __init__(self, interval_ms: int, callback: Callable[[SearchSnapshot], None] | None) -> None:
        self.interval = max(1, interval_ms) / 1000.0
        self.callback = callback
        self._next_emit_at = 0.0

    def emit(self, snapshot: SearchSnapshot, force: bool = False) -> None:
        if self.callback is None:
            return

        now = perf_counter()
        if force or now >= self._next_emit_at:
            self.callback(snapshot)
            self._next_emit_at = now + self.interval
