from engine.board import Board
from engine.evaluation import evaluate, evaluate_detailed


def test_evaluate_returns_centipawns_int() -> None:
    board = Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    score = evaluate(board)
    assert isinstance(score, int)


def test_evaluate_detailed_exposes_breakdown_maps() -> None:
    board = Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
    details = evaluate_detailed(board)

    assert isinstance(details.score_cp, int)
    assert "white" in details.components
    assert "black" in details.components
    assert "net" in details.components
    assert details.piece_breakdown

    # One known piece should include explainability fields.
    piece_info = details.piece_breakdown.get("e4")
    assert piece_info is not None
    assert {"base", "pst", "mobility", "pawn_structure", "king_safety", "total"}.issubset(piece_info.keys())
