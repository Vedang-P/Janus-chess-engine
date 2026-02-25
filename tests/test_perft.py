from engine.board import Board
from engine.perft import perft


def test_perft_start_position_depth_1_2_3() -> None:
    board = Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    assert perft(board, 1) == 20
    assert perft(board, 2) == 400
    assert perft(board, 3) == 8902


def test_perft_start_position_depth_4() -> None:
    board = Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    assert perft(board, 4) == 197281


def test_perft_kiwipete_depth_2() -> None:
    board = Board("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
    assert perft(board, 2) == 2039


def test_perft_kiwipete_depth_3() -> None:
    board = Board("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
    assert perft(board, 3) == 97862
