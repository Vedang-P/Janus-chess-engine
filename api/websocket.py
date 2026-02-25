"""WebSocket routes for live search telemetry."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from engine.board import Board
from engine.constants import START_FEN
from engine.instrumentation import SearchSnapshot
from engine.search import SearchEngine, SearchResult

router = APIRouter()


def _serialize_snapshot(snapshot: SearchSnapshot) -> dict:
    payload = snapshot.to_dict()
    payload["type"] = "snapshot"
    return payload


def _serialize_complete(result: SearchResult) -> dict:
    return {
        "type": "complete",
        "depth": result.depth,
        "nodes": result.nodes,
        "nps": result.nps,
        "current_move": result.current_move,
        "pv": [move.uci() for move in result.pv],
        "eval": result.eval,
        "eval_cp": result.score,
        "candidate_moves": result.candidate_moves,
        "piece_values": result.piece_values,
        "piece_breakdown": result.piece_breakdown,
        "heatmap": result.heatmap,
        "cutoffs": result.cutoffs,
        "elapsed_ms": round(result.elapsed_ms, 2),
        "best_move": result.best_move.uci() if result.best_move else None,
    }


@router.websocket("/ws/search")
async def search_websocket(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        while True:
            payload = await websocket.receive_json()
            fen = payload.get("fen", START_FEN)
            max_depth = int(payload.get("max_depth", 5))
            time_limit_ms = int(payload.get("time_limit_ms", 3000))
            snapshot_interval_ms = int(payload.get("snapshot_interval_ms", 75))

            board = Board(fen)
            engine = SearchEngine()
            event_queue: asyncio.Queue[dict | None] = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def on_snapshot(snapshot: SearchSnapshot) -> None:
                loop.call_soon_threadsafe(event_queue.put_nowait, _serialize_snapshot(snapshot))

            async def run_search() -> None:
                try:
                    result = await asyncio.to_thread(
                        engine.search,
                        board,
                        max_depth,
                        time_limit_ms,
                        None,
                        on_snapshot,
                        snapshot_interval_ms,
                    )
                    await event_queue.put(_serialize_complete(result))
                except Exception as exc:  # noqa: BLE001
                    await event_queue.put({"type": "error", "message": str(exc)})
                finally:
                    await event_queue.put(None)

            worker = asyncio.create_task(run_search())

            while True:
                item = await event_queue.get()
                if item is None:
                    break
                await websocket.send_json(item)

            await worker
    except WebSocketDisconnect:
        return
