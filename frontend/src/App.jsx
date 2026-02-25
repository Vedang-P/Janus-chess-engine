import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import ChessBoard from "./components/ChessBoard";
import { API_BASE, createSearchSocket, fetchLegalMoves, movePosition, resetPosition } from "./lib/api";
import { formatEval, moveToArrow, parseFenBoard, pieceColor, squareToIndex } from "./lib/chess";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const EMPTY_SEARCH = {
  depth: 0,
  eval: null,
  eval_cp: null,
  nodes: 0,
  nps: 0,
  cutoffs: 0,
  elapsed_ms: 0,
  current_move: "",
  pv: [],
  candidate_moves: {},
  piece_values: {},
  piece_breakdown: {},
  heatmap: {}
};

function sideLabel(side) {
  return side === "w" ? "White" : "Black";
}

function clampEvalFill(scoreCp) {
  if (scoreCp === null || scoreCp === undefined) return 50;
  const clamped = Math.max(-1200, Math.min(1200, scoreCp));
  return 50 + clamped / 24;
}

export default function App() {
  const [fen, setFen] = useState(START_FEN);
  const [fenDraft, setFenDraft] = useState(START_FEN);
  const [legalMoves, setLegalMoves] = useState([]);
  const [sideToMove, setSideToMove] = useState("w");
  const [status, setStatus] = useState("ongoing");
  const [selectedSquare, setSelectedSquare] = useState(null);
  const [hoveredSquare, setHoveredSquare] = useState(null);
  const [lastMove, setLastMove] = useState(null);
  const [humanSide, setHumanSide] = useState("white");
  const [maxDepth, setMaxDepth] = useState(5);
  const [timeMs, setTimeMs] = useState(2500);
  const [thinking, setThinking] = useState(false);
  const [search, setSearch] = useState(EMPTY_SEARCH);
  const [searchTimeline, setSearchTimeline] = useState([]);
  const [error, setError] = useState("");
  const [moveLog, setMoveLog] = useState([]);

  const wsRef = useRef(null);
  const searchTokenRef = useRef(0);

  const board = useMemo(() => parseFenBoard(fen), [fen]);
  const humanTurn = (humanSide === "white" ? "w" : "b") === sideToMove;
  const evalFill = useMemo(() => clampEvalFill(search.eval_cp), [search.eval_cp]);

  const candidateList = useMemo(
    () =>
      Object.entries(search.candidate_moves || {})
        .map(([move, evalScore]) => ({ move, eval: Number(evalScore) }))
        .sort((a, b) => b.eval - a.eval),
    [search.candidate_moves]
  );

  const legalTargets = useMemo(() => {
    if (!selectedSquare) return [];
    const targets = new Set();
    for (const move of legalMoves) {
      if (move.slice(0, 2) === selectedSquare) {
        targets.add(move.slice(2, 4));
      }
    }
    return Array.from(targets);
  }, [legalMoves, selectedSquare]);

  const arrows = useMemo(() => {
    const candidateArrows = candidateList.slice(0, 3).map((candidate, idx) =>
      moveToArrow(
        candidate.move,
        idx === 0 ? "#ff8243" : "#7bdaf8",
        idx === 0 ? 10 : 7,
        idx === 0 ? 0.92 : 0.7
      )
    );
    const pvArrows = search.pv.slice(0, 2).map((move) => moveToArrow(move, "#ffdb6e", 6, 0.65));
    return [...candidateArrows, ...pvArrows].filter(Boolean);
  }, [candidateList, search.pv]);

  const hoveredPieceDetail = useMemo(() => {
    if (!hoveredSquare) return null;
    return search.piece_breakdown?.[hoveredSquare] || null;
  }, [hoveredSquare, search.piece_breakdown]);

  const closeSocket = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const applyPosition = useCallback((payload) => {
    setFen(payload.fen);
    setFenDraft(payload.fen);
    setSideToMove(payload.side_to_move);
    setLegalMoves(payload.legal_moves || []);
    setStatus(payload.status || "ongoing");
    setSelectedSquare(null);
  }, []);

  const refreshPosition = useCallback(
    async (targetFen) => {
      const data = await fetchLegalMoves(targetFen);
      applyPosition(data);
      return data;
    },
    [applyPosition]
  );

  const applyMoveToPosition = useCallback(
    async (fromFen, move, actor) => {
      const data = await movePosition(fromFen, move);
      applyPosition(data);
      setLastMove({ from: move.slice(0, 2), to: move.slice(2, 4) });
      setMoveLog((prev) => [...prev, { by: actor, move }]);
      return data;
    },
    [applyPosition]
  );

  const startLiveSearch = useCallback(
    (positionFen, { autoPlayBestMove }) => {
      const token = ++searchTokenRef.current;
      setThinking(true);
      setError("");
      setSearch({ ...EMPTY_SEARCH });
      setSearchTimeline([]);
      closeSocket();

      const socket = createSearchSocket();
      let completed = false;
      wsRef.current = socket;

      socket.onopen = () => {
        socket.send(
          JSON.stringify({
            fen: positionFen,
            max_depth: maxDepth,
            time_limit_ms: timeMs,
            snapshot_interval_ms: 80
          })
        );
      };

      socket.onmessage = async (event) => {
        if (token !== searchTokenRef.current) return;

        const data = JSON.parse(event.data);
        if (data.type === "snapshot") {
          setSearch({
            depth: data.depth,
            eval: data.eval,
            eval_cp: data.eval_cp,
            nodes: data.nodes,
            nps: data.nps,
            cutoffs: data.cutoffs,
            elapsed_ms: data.elapsed_ms,
            current_move: data.current_move || "",
            pv: data.pv || [],
            candidate_moves: data.candidate_moves || {},
            piece_values: data.piece_values || {},
            piece_breakdown: data.piece_breakdown || {},
            heatmap: data.heatmap || {}
          });
          setSearchTimeline((prev) => {
            const next = [
              ...prev,
              {
                eval_cp: data.eval_cp,
                nodes: data.nodes,
                depth: data.depth,
                cutoffs: data.cutoffs
              }
            ];
            return next.slice(-80);
          });
          return;
        }

        if (data.type === "complete") {
          completed = true;
          setSearch({
            depth: data.depth,
            eval: data.eval,
            eval_cp: data.eval_cp,
            nodes: data.nodes,
            nps: data.nps,
            cutoffs: data.cutoffs,
            elapsed_ms: data.elapsed_ms,
            current_move: data.current_move || "",
            pv: data.pv || [],
            candidate_moves: data.candidate_moves || {},
            piece_values: data.piece_values || {},
            piece_breakdown: data.piece_breakdown || {},
            heatmap: data.heatmap || {}
          });

          if (autoPlayBestMove && data.best_move) {
            try {
              await applyMoveToPosition(positionFen, data.best_move, "engine");
            } catch (err) {
              setError(err.message);
            }
          }

          setThinking(false);
          closeSocket();
          return;
        }

        if (data.type === "error") {
          completed = true;
          setError(data.message || "Search failed.");
          setThinking(false);
          closeSocket();
        }
      };

      socket.onerror = () => {
        if (token !== searchTokenRef.current) return;
        setError("WebSocket error while searching.");
        setThinking(false);
        closeSocket();
      };

      socket.onclose = () => {
        if (token !== searchTokenRef.current) return;
        if (wsRef.current === socket) {
          wsRef.current = null;
        }
        if (!completed) {
          setThinking(false);
          setError((prev) => prev || "Search connection closed.");
        }
      };
    },
    [applyMoveToPosition, closeSocket, maxDepth, timeMs]
  );

  useEffect(() => {
    refreshPosition(START_FEN).catch((err) => setError(err.message));
    return () => {
      closeSocket();
      searchTokenRef.current += 1;
    };
  }, [closeSocket, refreshPosition]);

  useEffect(() => {
    if (status !== "ongoing") {
      setThinking(false);
      closeSocket();
      return;
    }

    if (humanTurn || thinking) {
      return;
    }

    startLiveSearch(fen, { autoPlayBestMove: true });
  }, [fen, humanTurn, status, thinking, startLiveSearch, closeSocket]);

  const pickMove = useCallback(
    (fromSquare, toSquare) => {
      const candidates = legalMoves.filter(
        (move) => move.slice(0, 2) === fromSquare && move.slice(2, 4) === toSquare
      );
      if (candidates.length === 0) return null;
      if (candidates.length === 1) return candidates[0];
      return candidates.find((move) => move.endsWith("q")) || candidates[0];
    },
    [legalMoves]
  );

  const handleSquareClick = useCallback(
    async (square) => {
      if (status !== "ongoing") return;
      if (!humanTurn || thinking) return;

      if (selectedSquare) {
        const chosenMove = pickMove(selectedSquare, square);
        if (chosenMove) {
          try {
            setError("");
            await applyMoveToPosition(fen, chosenMove, "human");
          } catch (err) {
            setError(err.message);
          }
          return;
        }
      }

      const piece = board[squareToIndex(square)];
      const ownColor = humanSide === "white" ? "w" : "b";
      if (piece && pieceColor(piece) === ownColor) {
        setSelectedSquare(square);
      } else {
        setSelectedSquare(null);
      }
    },
    [status, humanTurn, thinking, selectedSquare, pickMove, applyMoveToPosition, fen, board, humanSide]
  );

  const loadFen = useCallback(async () => {
    try {
      setError("");
      searchTokenRef.current += 1;
      closeSocket();
      setThinking(false);
      setMoveLog([]);
      setLastMove(null);
      setSearch({ ...EMPTY_SEARCH });
      setSearchTimeline([]);
      await refreshPosition(fenDraft);
    } catch (err) {
      setError(err.message);
    }
  }, [fenDraft, closeSocket, refreshPosition]);

  const resetGame = useCallback(async () => {
    try {
      setError("");
      searchTokenRef.current += 1;
      closeSocket();
      setThinking(false);
      setMoveLog([]);
      setLastMove(null);
      setSearch({ ...EMPTY_SEARCH });
      setSearchTimeline([]);
      const data = await resetPosition();
      applyPosition(data);
    } catch (err) {
      setError(err.message);
    }
  }, [applyPosition, closeSocket]);

  const analyzeCurrentPosition = useCallback(() => {
    if (thinking) return;
    startLiveSearch(fen, { autoPlayBestMove: false });
  }, [fen, startLiveSearch, thinking]);

  return (
    <div className="page">
      <header className="hero">
        <div>
          <h1>Chess Research Visualizer</h1>
          <p>
            Live alpha-beta search snapshots over WebSocket with explainable piece valuations. API: <code>{API_BASE}</code>
          </p>
        </div>
        <div className={`status-pill status-${status}`}>
          {status === "ongoing" ? `${sideLabel(sideToMove)} to move` : status.toUpperCase()}
        </div>
      </header>

      <main className="layout">
        <section className="panel board-panel">
          <ChessBoard
            fen={fen}
            orientation={humanSide}
            selectedSquare={selectedSquare}
            legalTargets={legalTargets}
            lastMove={lastMove}
            currentMove={search.current_move}
            hoveredSquare={hoveredSquare}
            heatmap={search.heatmap}
            arrows={arrows}
            onSquareClick={handleSquareClick}
            onSquareHover={setHoveredSquare}
          />
        </section>

        <section className="panel controls">
          <div className="toolbar">
            <button type="button" onClick={resetGame}>
              New Game
            </button>
            <button type="button" onClick={analyzeCurrentPosition} disabled={thinking}>
              Analyze Position
            </button>
          </div>

          <div className="config-grid">
            <label>
              Play as
              <select value={humanSide} onChange={(event) => setHumanSide(event.target.value)}>
                <option value="white">White</option>
                <option value="black">Black</option>
              </select>
            </label>

            <label>
              Max depth
              <input
                type="range"
                min="1"
                max="8"
                value={maxDepth}
                onChange={(event) => setMaxDepth(Number(event.target.value))}
              />
              <span>{maxDepth}</span>
            </label>

            <label>
              Time (ms)
              <input
                type="number"
                min="100"
                max="15000"
                value={timeMs}
                onChange={(event) => setTimeMs(Number(event.target.value) || 100)}
              />
            </label>
          </div>

          <label>
            FEN
            <textarea rows={3} value={fenDraft} onChange={(event) => setFenDraft(event.target.value)} />
            <button type="button" onClick={loadFen}>
              Load FEN
            </button>
          </label>

          <div className="telemetry-grid">
            <article>
              <span>Eval</span>
              <strong>{formatEval(search.eval)}</strong>
            </article>
            <article>
              <span>Depth</span>
              <strong>{search.depth || 0}</strong>
            </article>
            <article>
              <span>Nodes</span>
              <strong>{search.nodes.toLocaleString()}</strong>
            </article>
            <article>
              <span>NPS</span>
              <strong>{search.nps.toLocaleString()}</strong>
            </article>
          </div>

          <div className="eval-bar-wrap" title="Positive favors side to move; negative favors opponent">
            <div className="eval-bar">
              <div className="eval-black" style={{ height: `${100 - evalFill}%` }} />
              <div className="eval-white" style={{ height: `${evalFill}%` }} />
            </div>
            <div className="eval-side-text">
              <span>White</span>
              <span>Black</span>
            </div>
          </div>

          <div className="panel-subsection">
            <h2>Principal Variation</h2>
            <p className="pv-line">{search.pv.length ? search.pv.join(" ") : "-"}</p>
          </div>

          <div className="panel-subsection">
            <h2>Candidate Move Rankings</h2>
            <div className="candidate-list">
              {candidateList.slice(0, 10).map((candidate, idx) => (
                <div className="candidate-row" key={`${candidate.move}-${idx}`}>
                  <span>#{idx + 1}</span>
                  <span>{candidate.move}</span>
                  <strong>{formatEval(candidate.eval)}</strong>
                </div>
              ))}
              {!candidateList.length && <p className="muted">No candidate data yet.</p>}
            </div>
          </div>

          <div className="panel-subsection">
            <h2>Dynamic Piece Valuation</h2>
            {!hoveredSquare && <p className="muted">Hover a square to inspect piece valuation.</p>}
            {hoveredSquare && !hoveredPieceDetail && <p className="muted">{hoveredSquare}: empty or no piece data yet.</p>}
            {hoveredSquare && hoveredPieceDetail && (
              <div className="piece-inspector">
                <div>
                  <span>Square</span>
                  <strong>{hoveredSquare}</strong>
                </div>
                <div>
                  <span>Piece</span>
                  <strong>{hoveredPieceDetail.piece}</strong>
                </div>
                <div>
                  <span>Base</span>
                  <strong>{hoveredPieceDetail.base}</strong>
                </div>
                <div>
                  <span>PST</span>
                  <strong>{hoveredPieceDetail.pst}</strong>
                </div>
                <div>
                  <span>Mobility</span>
                  <strong>{hoveredPieceDetail.mobility}</strong>
                </div>
                <div>
                  <span>Pawn Struct.</span>
                  <strong>{hoveredPieceDetail.pawn_structure}</strong>
                </div>
                <div>
                  <span>King Safety</span>
                  <strong>{hoveredPieceDetail.king_safety}</strong>
                </div>
                <div>
                  <span>Total</span>
                  <strong>{hoveredPieceDetail.total}</strong>
                </div>
              </div>
            )}
          </div>

          <div className="panel-subsection">
            <h2>Search Visualization</h2>
            <div className="search-counters">
              <span>Current Move: {search.current_move || "-"}</span>
              <span>Cutoffs: {search.cutoffs}</span>
              <span>Elapsed: {Math.round(search.elapsed_ms)}ms</span>
            </div>
            <div className="timeline-bars">
              {searchTimeline.map((frame, idx) => {
                const h = Math.max(8, Math.min(58, 8 + Math.abs(frame.eval_cp || 0) / 18));
                const positive = (frame.eval_cp || 0) >= 0;
                return (
                  <div
                    key={`frame-${idx}`}
                    className="timeline-bar"
                    style={{
                      height: `${h}px`,
                      background: positive
                        ? "linear-gradient(180deg, rgba(255,130,67,0.95), rgba(255,130,67,0.45))"
                        : "linear-gradient(180deg, rgba(104,215,255,0.95), rgba(104,215,255,0.4))"
                    }}
                    title={`depth ${frame.depth} | eval ${frame.eval_cp} | nodes ${frame.nodes}`}
                  />
                );
              })}
            </div>
          </div>

          <div className="panel-subsection">
            <h2>Move Log</h2>
            <div className="move-log">
              {moveLog.map((entry, idx) => (
                <div key={`${entry.move}-${idx}`} className="move-log-row">
                  <span>{idx + 1}.</span>
                  <span>{entry.by}</span>
                  <strong>{entry.move}</strong>
                </div>
              ))}
              {!moveLog.length && <p className="muted">No moves yet.</p>}
            </div>
          </div>

          {thinking && <p className="thinking">Engine thinking...</p>}
          {error && <p className="error">{error}</p>}
        </section>
      </main>
    </div>
  );
}
