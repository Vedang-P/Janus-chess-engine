from engine.board import Board
from engine.instrumentation import SearchSnapshot
from engine.search import SearchEngine


def test_search_returns_a_legal_move() -> None:
    board = Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
    engine = SearchEngine()

    result = engine.search(board, max_depth=2, time_limit_ms=2000)

    assert result.best_move is not None
    assert result.depth >= 1
    assert result.nodes > 0


def test_search_emits_live_snapshots() -> None:
    board = Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
    engine = SearchEngine()
    snapshots: list[SearchSnapshot] = []

    def on_snapshot(snapshot: SearchSnapshot) -> None:
        snapshots.append(snapshot)

    engine.search(board, max_depth=2, time_limit_ms=2000, on_snapshot=on_snapshot, snapshot_interval_ms=20)

    assert snapshots
    latest = snapshots[-1]
    assert latest.depth >= 1
    assert isinstance(latest.candidate_moves, dict)
    assert isinstance(latest.piece_values, dict)
