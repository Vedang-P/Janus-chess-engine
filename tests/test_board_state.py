from engine.board import Board
from engine.constants import (
    CASTLE_WHITE_KING,
    PIECE_NONE,
    WK,
    WP,
    WR,
    square_index,
)
from engine.move import Move


def snapshot(board: Board):
    return board.debug_state()


def test_make_unmake_simple_pawn_push_roundtrip() -> None:
    board = Board("8/8/8/8/8/8/4P3/4K3 w - - 0 1")
    initial = snapshot(board)

    move = Move(from_square=square_index("e2"), to_square=square_index("e4"), piece=WP, is_double_push=True)
    assert board.make_move(move)

    assert board.en_passant == square_index("e3")
    assert board.unmake_move()
    assert snapshot(board) == initial


def test_make_unmake_en_passant_roundtrip() -> None:
    board = Board("8/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    initial = snapshot(board)

    move = Move(
        from_square=square_index("e5"),
        to_square=square_index("d6"),
        piece=WP,
        is_en_passant=True,
    )
    assert board.make_move(move)
    assert board.piece_on(square_index("d5")) == PIECE_NONE

    assert board.unmake_move()
    assert snapshot(board) == initial


def test_make_unmake_promotion_roundtrip() -> None:
    board = Board("4k3/4P3/8/8/8/8/8/4K3 w - - 0 1")
    initial = snapshot(board)

    move = Move(
        from_square=square_index("e7"),
        to_square=square_index("e8"),
        piece=WP,
        promotion=WR,
        captured=PIECE_NONE,
    )
    assert board.make_move(move)

    assert board.piece_on(square_index("e8")) == WR

    assert board.unmake_move()
    assert snapshot(board) == initial


def test_castling_rights_update_and_restore() -> None:
    board = Board("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1")
    initial = snapshot(board)

    rook_move = Move(from_square=square_index("h1"), to_square=square_index("h2"), piece=WR)
    assert board.make_move(rook_move)
    assert board.castling_rights & CASTLE_WHITE_KING == 0
    assert board.unmake_move()
    assert snapshot(board) == initial


def test_make_unmake_castle_roundtrip() -> None:
    board = Board("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1")
    initial = snapshot(board)

    castle = Move(from_square=square_index("e1"), to_square=square_index("g1"), piece=WK, is_castle=True)
    assert board.make_move(castle)
    assert board.piece_on(square_index("f1")) == WR
    assert board.piece_on(square_index("h1")) == PIECE_NONE

    assert board.unmake_move()
    assert snapshot(board) == initial


def test_to_fen_round_trip() -> None:
    fen = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
    board = Board(fen)
    assert board.to_fen() == fen


def test_reject_move_for_wrong_side_to_move() -> None:
    board = Board("8/8/8/8/8/8/4P3/4K3 b - - 0 1")
    initial = snapshot(board)

    move = Move(from_square=square_index("e2"), to_square=square_index("e4"), piece=WP, is_double_push=True)
    assert not board.make_move(move)
    assert snapshot(board) == initial


def test_reject_invalid_en_passant_target() -> None:
    board = Board("8/8/8/3pP3/8/8/8/4K3 w - - 0 1")
    initial = snapshot(board)

    move = Move(
        from_square=square_index("e5"),
        to_square=square_index("d6"),
        piece=WP,
        is_en_passant=True,
    )
    assert not board.make_move(move)
    assert snapshot(board) == initial
