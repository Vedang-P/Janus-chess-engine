"""Iterative deepening negamax alpha-beta with live instrumentation."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from .board import Board
from .evaluation import evaluate, evaluate_detailed, terminal_score
from .instrumentation import SearchSnapshot, SnapshotThrottle
from .move import Move
from .movegen import generate_legal_moves, in_check


@dataclass(slots=True)
class CandidateScore:
    move: str
    score: int
    eval: float


@dataclass(slots=True)
class SearchResult:
    best_move: Move | None
    score: int
    eval: float
    depth: int
    pv: list[Move]
    nodes: int
    elapsed_ms: float
    nps: int
    cutoffs: int
    current_move: str
    candidates: list[CandidateScore]
    candidate_moves: dict[str, float]
    piece_values: dict[str, int]
    piece_breakdown: dict[str, dict[str, int | str]]
    heatmap: dict[str, int]


class _SearchTimeout(Exception):
    pass


class SearchEngine:
    def __init__(self) -> None:
        self.nodes = 0
        self.cutoffs = 0
        self._deadline = 0.0
        self._start = 0.0

    def search(
        self,
        board: Board,
        max_depth: int = 5,
        time_limit_ms: int = 3_000,
        on_iteration: Callable[[SearchResult], None] | None = None,
        on_snapshot: Callable[[SearchSnapshot], None] | None = None,
        snapshot_interval_ms: int = 75,
    ) -> SearchResult:
        if max_depth < 1:
            raise ValueError("max_depth must be >= 1")

        self.nodes = 0
        self.cutoffs = 0
        self._start = perf_counter()
        self._deadline = self._start + (time_limit_ms / 1000.0)

        root_eval = evaluate_detailed(board)
        throttler = SnapshotThrottle(snapshot_interval_ms, on_snapshot)

        best_result = SearchResult(
            best_move=None,
            score=0,
            eval=0.0,
            depth=0,
            pv=[],
            nodes=0,
            elapsed_ms=0.0,
            nps=0,
            cutoffs=0,
            current_move="",
            candidates=[],
            candidate_moves={},
            piece_values=root_eval.piece_values,
            piece_breakdown=root_eval.piece_breakdown,
            heatmap=root_eval.heatmap,
        )

        for depth in range(1, max_depth + 1):
            try:
                score, best_move, pv, candidates, current_move = self._search_root(
                    board,
                    depth,
                    root_eval,
                    throttler,
                )
            except _SearchTimeout:
                break

            elapsed_ms = (perf_counter() - self._start) * 1000.0
            nps = int(self.nodes / max((elapsed_ms / 1000.0), 1e-9))
            pv_uci = [move.uci() for move in pv]
            candidate_moves = {item.move: item.eval for item in candidates}

            best_result = SearchResult(
                best_move=best_move,
                score=score,
                eval=round(score / 100.0, 2),
                depth=depth,
                pv=pv,
                nodes=self.nodes,
                elapsed_ms=elapsed_ms,
                nps=nps,
                cutoffs=self.cutoffs,
                current_move=current_move,
                candidates=candidates,
                candidate_moves=candidate_moves,
                piece_values=root_eval.piece_values,
                piece_breakdown=root_eval.piece_breakdown,
                heatmap=_compose_heatmap(root_eval.heatmap, candidate_moves, pv_uci),
            )
            if on_iteration is not None:
                on_iteration(best_result)

            throttler.emit(
                _to_snapshot(best_result),
                force=True,
            )

        return best_result

    def _search_root(
        self,
        board: Board,
        depth: int,
        root_eval,
        throttler: SnapshotThrottle,
    ) -> tuple[int, Move | None, list[Move], list[CandidateScore], str]:
        self._check_timeout()

        alpha = -100_000
        beta = 100_000

        moves = generate_legal_moves(board)
        if not moves:
            score = terminal_score(board, in_check(board, board.side_to_move), 0)
            return score, None, [], [], ""

        ordered = sorted(moves, key=_move_order_key, reverse=True)

        best_score = -100_000
        best_move: Move | None = None
        best_pv: list[Move] = []
        candidates: list[CandidateScore] = []
        current_move = ""

        for move in ordered:
            self._check_timeout()
            current_move = move.uci()

            board.make_move(move)
            child_score, child_pv = self._negamax(board, depth - 1, -beta, -alpha, 1)
            score = -child_score
            board.unmake_move()

            candidates.append(CandidateScore(move=current_move, score=score, eval=round(score / 100.0, 2)))

            if score > best_score:
                best_score = score
                best_move = move
                best_pv = [move] + child_pv

            if score > alpha:
                alpha = score

            elapsed_ms = (perf_counter() - self._start) * 1000.0
            nps = int(self.nodes / max((elapsed_ms / 1000.0), 1e-9))
            pv_uci = [item.uci() for item in best_pv]
            candidate_moves = {item.move: item.eval for item in sorted(candidates, key=lambda c: c.score, reverse=True)}

            throttler.emit(
                SearchSnapshot(
                    depth=depth,
                    nodes=self.nodes,
                    nps=nps,
                    current_move=current_move,
                    pv=pv_uci,
                    eval=round(best_score / 100.0, 2),
                    eval_cp=best_score,
                    candidate_moves=candidate_moves,
                    piece_values=root_eval.piece_values,
                    piece_breakdown=root_eval.piece_breakdown,
                    heatmap=_compose_heatmap(root_eval.heatmap, candidate_moves, pv_uci),
                    cutoffs=self.cutoffs,
                    elapsed_ms=round(elapsed_ms, 2),
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return best_score, best_move, best_pv, candidates, current_move

    def _negamax(self, board: Board, depth: int, alpha: int, beta: int, ply: int) -> tuple[int, list[Move]]:
        self._check_timeout()
        self.nodes += 1

        if depth == 0:
            return evaluate(board), []

        moves = generate_legal_moves(board)
        if not moves:
            return terminal_score(board, in_check(board, board.side_to_move), ply), []

        best_score = -100_000
        best_line: list[Move] = []

        for move in sorted(moves, key=_move_order_key, reverse=True):
            board.make_move(move)
            child_score, child_line = self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
            score = -child_score
            board.unmake_move()

            if score > best_score:
                best_score = score
                best_line = [move] + child_line

            if score > alpha:
                alpha = score

            if alpha >= beta:
                self.cutoffs += 1
                break

        return best_score, best_line

    def _check_timeout(self) -> None:
        if perf_counter() >= self._deadline:
            raise _SearchTimeout


def _to_snapshot(result: SearchResult) -> SearchSnapshot:
    return SearchSnapshot(
        depth=result.depth,
        nodes=result.nodes,
        nps=result.nps,
        current_move=result.current_move,
        pv=[move.uci() for move in result.pv],
        eval=result.eval,
        eval_cp=result.score,
        candidate_moves=result.candidate_moves,
        piece_values=result.piece_values,
        piece_breakdown=result.piece_breakdown,
        heatmap=result.heatmap,
        cutoffs=result.cutoffs,
        elapsed_ms=round(result.elapsed_ms, 2),
    )


def _build_heatmap(candidate_moves: dict[str, float], pv: list[str]) -> dict[str, int]:
    heatmap: dict[str, int] = {}

    for idx, move in enumerate(pv[:8]):
        if len(move) < 4:
            continue
        to_sq = move[2:4]
        heatmap[to_sq] = heatmap.get(to_sq, 0) + max(1, 5 - idx)

    ranked = sorted(candidate_moves.items(), key=lambda item: item[1], reverse=True)
    for idx, (move, _) in enumerate(ranked[:10]):
        if len(move) < 4:
            continue
        from_sq = move[:2]
        to_sq = move[2:4]
        heatmap[from_sq] = heatmap.get(from_sq, 0) + max(1, 3 - idx)
        heatmap[to_sq] = heatmap.get(to_sq, 0) + max(1, 4 - idx)

    return heatmap


def _compose_heatmap(
    static_heatmap: dict[str, int],
    candidate_moves: dict[str, float],
    pv: list[str],
) -> dict[str, int]:
    merged = dict(static_heatmap)
    search_heatmap = _build_heatmap(candidate_moves, pv)
    for square, value in search_heatmap.items():
        merged[square] = merged.get(square, 0) + value
    return merged


def _move_order_key(move: Move) -> int:
    score = 0
    if move.captured != -1:
        score += 10_000
    if move.promotion != -1:
        score += 8_000
    if move.is_castle:
        score += 100
    return score
