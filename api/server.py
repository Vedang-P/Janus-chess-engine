"""FastAPI server exposing engine analysis and gameplay endpoints."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engine.board import Board
from engine.constants import START_FEN
from engine.movegen import generate_legal_moves, in_check
from engine.perft import perft, perft_divide
from engine.search import SearchEngine, SearchResult

from .websocket import router as websocket_router


class AnalyzeRequest(BaseModel):
    fen: str = Field(default=START_FEN)
    max_depth: int = Field(default=5, ge=1, le=10)
    time_limit_ms: int = Field(default=3000, ge=50, le=120_000)


class PerftRequest(BaseModel):
    fen: str = Field(default=START_FEN)
    depth: int = Field(default=3, ge=1, le=6)
    divide: bool = Field(default=False)


class PositionRequest(BaseModel):
    fen: str = Field(default=START_FEN)


class MoveRequest(BaseModel):
    fen: str = Field(default=START_FEN)
    move: str = Field(min_length=4, max_length=5)


class ResetRequest(BaseModel):
    fen: str = Field(default=START_FEN)


app = FastAPI(title="Chess Engine API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(websocket_router)


def _board_from_fen(fen: str) -> Board:
    try:
        return Board(fen)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _side_name(board: Board) -> str:
    return "w" if board.side_to_move == 0 else "b"


def _status_from_moves(board: Board, legal_moves: list) -> str:
    if legal_moves:
        return "ongoing"
    return "checkmate" if in_check(board, board.side_to_move) else "stalemate"


def _position_payload(board: Board, legal_moves: list) -> dict:
    return {
        "fen": board.to_fen(),
        "side_to_move": _side_name(board),
        "legal_moves": [move.uci() for move in legal_moves],
        "status": _status_from_moves(board, legal_moves),
    }


def _search_payload(result: SearchResult) -> dict:
    return {
        "best_move": result.best_move.uci() if result.best_move else None,
        "score": result.score,
        "eval": result.eval,
        "depth": result.depth,
        "nodes": result.nodes,
        "nps": result.nps,
        "cutoffs": result.cutoffs,
        "elapsed_ms": round(result.elapsed_ms, 2),
        "current_move": result.current_move,
        "pv": [move.uci() for move in result.pv],
        "candidate_moves": result.candidate_moves,
        "piece_values": result.piece_values,
        "piece_breakdown": result.piece_breakdown,
        "heatmap": result.heatmap,
    }


def _apply_uci_move(board: Board, wanted: str) -> str:
    target = wanted.lower().strip()
    legal = generate_legal_moves(board)
    for move in legal:
        if move.uci() == target:
            board.make_move(move)
            return move.uci()
    raise HTTPException(status_code=400, detail=f"Illegal move: {target}")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze")
def analyze(payload: AnalyzeRequest) -> dict:
    board = _board_from_fen(payload.fen)
    engine = SearchEngine()
    result = engine.search(board, max_depth=payload.max_depth, time_limit_ms=payload.time_limit_ms)
    response = _position_payload(board, generate_legal_moves(board))
    response.update(_search_payload(result))
    return response


@app.post("/legal-moves")
def legal_moves(payload: PositionRequest) -> dict:
    board = _board_from_fen(payload.fen)
    legal = generate_legal_moves(board)
    return _position_payload(board, legal)


@app.post("/move")
def move(payload: MoveRequest) -> dict:
    board = _board_from_fen(payload.fen)
    played = _apply_uci_move(board, payload.move)
    legal = generate_legal_moves(board)
    response = _position_payload(board, legal)
    response["last_move"] = played
    return response


@app.post("/apply-move")
def apply_move(payload: MoveRequest) -> dict:
    # Backward-compatible alias.
    return move(payload)


@app.post("/engine-move")
def engine_move(payload: AnalyzeRequest) -> dict:
    board = _board_from_fen(payload.fen)
    engine = SearchEngine()
    result = engine.search(board, max_depth=payload.max_depth, time_limit_ms=payload.time_limit_ms)

    if result.best_move is not None:
        board.make_move(result.best_move)

    legal = generate_legal_moves(board)
    response = _position_payload(board, legal)
    response.update(_search_payload(result))
    return response


@app.post("/reset")
def reset(payload: ResetRequest | None = None) -> dict:
    fen = START_FEN if payload is None else payload.fen
    board = _board_from_fen(fen)
    legal = generate_legal_moves(board)
    return _position_payload(board, legal)


@app.post("/perft")
def run_perft(payload: PerftRequest) -> dict:
    board = _board_from_fen(payload.fen)
    if payload.divide:
        return {"divide": perft_divide(board, payload.depth)}
    return {"nodes": perft(board, payload.depth)}
