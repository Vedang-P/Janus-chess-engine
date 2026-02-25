"""Command-line utilities for the chess engine."""

from __future__ import annotations

import argparse

from engine.board import Board
from engine.constants import BLACK, START_FEN, WHITE
from engine.evaluation import evaluate
from engine.perft import perft, perft_divide
from engine.search import SearchEngine
from engine.movegen import generate_legal_moves, in_check


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Chess engine utilities")
    parser.add_argument("--fen", default=START_FEN, help="FEN position")

    subparsers = parser.add_subparsers(dest="command", required=False)

    perft_parser = subparsers.add_parser("perft", help="Run perft")
    perft_parser.add_argument("depth", type=int, help="Perft depth")
    perft_parser.add_argument("--divide", action="store_true", help="Show per-move split")

    search_parser = subparsers.add_parser("search", help="Run iterative deepening search")
    search_parser.add_argument("--depth", type=int, default=5, help="Max search depth")
    search_parser.add_argument("--time", type=int, default=3000, help="Time limit in ms")

    eval_parser = subparsers.add_parser("eval", help="Evaluate position")
    eval_parser.add_argument("--depth", type=int, default=4, help="Search depth")
    eval_parser.add_argument("--time", type=int, default=2000, help="Time limit in ms")

    play_parser = subparsers.add_parser("play", help="Play against the engine in terminal")
    play_parser.add_argument("--side", choices=("white", "black"), default="white", help="Your side")
    play_parser.add_argument("--depth", type=int, default=4, help="Engine max depth")
    play_parser.add_argument("--time", type=int, default=2000, help="Engine time limit in ms")

    return parser


def _find_legal_move(board: Board, move_uci: str):
    for move in generate_legal_moves(board):
        if move.uci() == move_uci:
            return move
    return None


def _print_eval(board: Board, depth: int, time_ms: int) -> None:
    static_cp = evaluate(board)
    engine = SearchEngine()
    result = engine.search(board, max_depth=depth, time_limit_ms=time_ms)
    best = result.best_move.uci() if result.best_move else "0000"
    pv = " ".join(m.uci() for m in result.pv) or "-"
    print(f"static_eval_cp={static_cp}")
    print(
        f"search_eval_cp={result.score} depth={result.depth} "
        f"bestmove={best} nodes={result.nodes} nps={result.nps}"
    )
    print(f"pv {pv}")


def _run_play_mode(board: Board, human_side: int, depth: int, time_ms: int) -> None:
    print("Commands: move in UCI (e2e4), eval, fen, moves, quit")
    while True:
        legal = generate_legal_moves(board)
        if not legal:
            if in_check(board, board.side_to_move):
                winner = "black" if board.side_to_move == WHITE else "white"
                print(f"Checkmate. {winner} wins.")
            else:
                print("Stalemate.")
            return

        print()
        print(board)
        print(f"FEN: {board.to_fen()}")
        stm = "white" if board.side_to_move == WHITE else "black"
        print(f"Side to move: {stm}")

        if board.side_to_move == human_side:
            raw = input("your> ").strip().lower()
            if not raw:
                continue
            if raw in {"quit", "exit"}:
                return
            if raw == "fen":
                print(board.to_fen())
                continue
            if raw == "moves":
                print(" ".join(m.uci() for m in legal))
                continue
            if raw == "eval":
                _print_eval(board, depth, time_ms)
                continue

            move = _find_legal_move(board, raw)
            if move is None:
                print("Illegal move. Use `moves` to list legal options.")
                continue
            board.make_move(move)
            continue

        engine = SearchEngine()
        result = engine.search(board, max_depth=depth, time_limit_ms=time_ms)
        if result.best_move is None:
            print("No move found.")
            return
        board.make_move(result.best_move)
        pv = " ".join(m.uci() for m in result.pv) or "-"
        print(
            f"engine> {result.best_move.uci()} "
            f"(eval={result.score} depth={result.depth} nodes={result.nodes})"
        )
        print(f"pv {pv}")


def run() -> None:
    parser = build_parser()
    args = parser.parse_args()

    board = Board(args.fen)

    if args.command == "perft":
        if args.divide:
            for move, count in perft_divide(board, args.depth).items():
                print(f"{move}: {count}")
        else:
            print(perft(board, args.depth))
        return

    if args.command == "search":
        engine = SearchEngine()
        result = engine.search(board, max_depth=args.depth, time_limit_ms=args.time)
        print(f"bestmove {result.best_move.uci() if result.best_move else '0000'}")
        print(f"depth {result.depth} score {result.score} nodes {result.nodes} nps {result.nps}")
        print("pv", " ".join(m.uci() for m in result.pv))
        return

    if args.command == "eval":
        _print_eval(board, args.depth, args.time)
        return

    if args.command == "play":
        human_side = WHITE if args.side == "white" else BLACK
        _run_play_mode(board, human_side, args.depth, args.time)
        return

    print(board)


if __name__ == "__main__":
    run()
