import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import ChessBoard from "./components/ChessBoard";
import {
  analyzePosition,
  createSearchSocket,
  engineMovePosition,
  fetchLegalMoves,
  movePosition,
  resetPosition
} from "./lib/api";
import { formatEval, moveToArrow, parseFenBoard, pieceColor, squareToIndex } from "./lib/chess";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const TIME_PRESETS_MS = [250, 500, 1000, 2000, 3000, 5000, 10000];
const PIECE_NAME = {
  p: "Pawn",
  n: "Knight",
  b: "Bishop",
  r: "Rook",
  q: "Queen",
  k: "King"
};
const BASE_VALUE_CP = {
  p: 100,
  n: 320,
  b: 330,
  r: 500,
  q: 900,
  k: 0
};
const LEGEND_ITEMS = [
  { term: "Eval", meaning: "Who is better right now. Positive means White is better." },
  { term: "Centipawn (cp)", meaning: "Engine unit. 100 cp is roughly equal to one pawn." },
  { term: "Depth", meaning: "How many half-moves ahead the engine searched." },
  { term: "Nodes", meaning: "Total positions the engine examined in this search." },
  { term: "NPS", meaning: "Nodes per second. Higher means faster search speed." },
  { term: "Cutoffs", meaning: "Branches skipped by alpha-beta pruning to save time." },
  { term: "PV", meaning: "Principal Variation: the engine's best line right now." },
  { term: "Candidates", meaning: "Top move choices and their current evaluations." },
  { term: "Search Flow", meaning: "Live snapshot bars of eval trend while the search runs." },
  { term: "Dynamic Value", meaning: "Value details for the piece you clicked on the board." },
  { term: "Square", meaning: "Board coordinate of the currently selected piece." },
  { term: "Piece", meaning: "The piece type on that selected square (pawn, knight, bishop, etc.)." },
  { term: "Dynamic (cp)", meaning: "Current live value of that selected piece in this position." },
  { term: "Base (cp)", meaning: "Starting piece value before position-based adjustments." },
  { term: "PST (cp)", meaning: "Piece-square table bonus/penalty based on where the piece stands." },
  { term: "Heatmap", meaning: "Squares currently receiving more tactical pressure." }
];

const EMPTY_SEARCH = {
  depth: 0,
  eval: null,
  eval_cp: null,
  search_side: "w",
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

function formatPvLine(pv) {
  if (!pv || pv.length === 0) return "-";

  const tokens = [];
  for (let idx = 0; idx < pv.length; idx += 1) {
    if (idx % 2 === 0) {
      tokens.push(`${Math.floor(idx / 2) + 1}.`);
    }
    tokens.push(pv[idx]);
  }
  return tokens.join(" ");
}

function formatCp(value) {
  if (value === null || value === undefined) return "-";
  return `${value > 0 ? "+" : ""}${value} cp`;
}

function normalizeScore(value) {
  if (value === null || value === undefined) return null;
  return Number(Number(value).toFixed(2));
}

function buildMoveRows(moves) {
  const rows = [];
  for (let idx = 0; idx < moves.length; idx += 2) {
    rows.push({
      number: Math.floor(idx / 2) + 1,
      white: moves[idx]?.move || "",
      black: moves[idx + 1]?.move || ""
    });
  }
  return rows;
}

function normalizeFenInput(rawFen) {
  const normalized = String(rawFen || "")
    .trim()
    .replace(/\s+/g, " ");
  if (!normalized) return "";
  if (normalized.toLowerCase() === "startpos") return START_FEN;
  return normalized;
}

export default function App() {
  const [fen, setFen] = useState(START_FEN);
  const [fenDraft, setFenDraft] = useState(START_FEN);
  const [legalMoves, setLegalMoves] = useState([]);
  const [sideToMove, setSideToMove] = useState("w");
  const [status, setStatus] = useState("ongoing");
  const [selectedSquare, setSelectedSquare] = useState(null);
  const [hoveredSquare, setHoveredSquare] = useState(null);
  const [trackedSquare, setTrackedSquare] = useState(null);
  const [dragFromSquare, setDragFromSquare] = useState(null);
  const [dragToSquare, setDragToSquare] = useState(null);
  const [lastMove, setLastMove] = useState(null);
  const [humanSide, setHumanSide] = useState("white");
  const [maxDepth, setMaxDepth] = useState(5);
  const [timeMs, setTimeMs] = useState(2500);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [thinking, setThinking] = useState(false);
  const [coldStartHintOpen, setColdStartHintOpen] = useState(false);
  const [showResultOverlay, setShowResultOverlay] = useState(false);
  const [positionEval, setPositionEval] = useState(null);
  const [positionEvalCp, setPositionEvalCp] = useState(null);
  const [search, setSearch] = useState(EMPTY_SEARCH);
  const [searchTimeline, setSearchTimeline] = useState([]);
  const [error, setError] = useState("");
  const [moveLog, setMoveLog] = useState([]);

  const wsRef = useRef(null);
  const searchTokenRef = useRef(0);
  const lastSnapshotUiUpdateRef = useRef(0);

  const board = useMemo(() => parseFenBoard(fen), [fen]);
  const humanTurn = (humanSide === "white" ? "w" : "b") === sideToMove;
  const evalFill = useMemo(
    () => clampEvalFill(positionEvalCp ?? search.eval_cp),
    [positionEvalCp, search.eval_cp]
  );
  const gameResult = useMemo(() => {
    if (status === "checkmate") {
      return sideToMove === "w"
        ? { score: "0-1", caption: "Black wins by checkmate" }
        : { score: "1-0", caption: "White wins by checkmate" };
    }
    if (status === "stalemate") {
      return { score: "1/2-1/2", caption: "Draw by stalemate" };
    }
    return null;
  }, [sideToMove, status]);

  const moveRows = useMemo(() => buildMoveRows(moveLog), [moveLog]);

  const candidateList = useMemo(() => {
    const entries = Object.entries(search.candidate_moves || {}).map(([move, evalScore]) => ({
      move,
      eval: Number(evalScore)
    }));
    if (search.search_side === "w") {
      return entries.sort((a, b) => b.eval - a.eval);
    }
    return entries.sort((a, b) => a.eval - b.eval);
  }, [search.candidate_moves, search.search_side]);

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
    const result = [];
    const seen = new Set();

    const bestCandidate = candidateList[0];
    if (bestCandidate) {
      const arrow = moveToArrow(bestCandidate.move, "#7fa650", 8, 0.8);
      if (arrow) {
        const key = `${arrow.from}-${arrow.to}`;
        seen.add(key);
        result.push(arrow);
      }
    }

    const pvPrimary = search.pv[0];
    if (pvPrimary) {
      const arrow = moveToArrow(pvPrimary, "#7fa650", 8, 0.8);
      if (arrow) {
        const key = `${arrow.from}-${arrow.to}`;
        if (!seen.has(key)) {
          result.push(arrow);
        }
      }
    }

    return result;
  }, [candidateList, search.pv]);

  const trackedPieceDetail = useMemo(() => {
    if (!trackedSquare) return null;
    return search.piece_breakdown?.[trackedSquare] || null;
  }, [trackedSquare, search.piece_breakdown]);

  const trackedPieceSymbol = useMemo(() => {
    if (!trackedSquare) return null;
    return board[squareToIndex(trackedSquare)] || null;
  }, [board, trackedSquare]);

  const trackedPieceName = useMemo(() => {
    if (!trackedPieceSymbol) return "";
    return PIECE_NAME[trackedPieceSymbol.toLowerCase()] || "";
  }, [trackedPieceSymbol]);

  const trackedPieceDynamicValue = useMemo(() => {
    if (!trackedSquare || !trackedPieceSymbol) return null;

    if (typeof search.piece_values?.[trackedSquare] === "number") {
      return search.piece_values[trackedSquare];
    }

    if (typeof trackedPieceDetail?.signed_total === "number") {
      return trackedPieceDetail.signed_total;
    }

    const base = BASE_VALUE_CP[trackedPieceSymbol.toLowerCase()] || 0;
    return pieceColor(trackedPieceSymbol) === "w" ? base : -base;
  }, [trackedPieceDetail, trackedPieceSymbol, trackedSquare, search.piece_values]);

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
    setPositionEval(typeof payload.position_eval === "number" ? payload.position_eval : null);
    setPositionEvalCp(typeof payload.position_eval_cp === "number" ? payload.position_eval_cp : null);
    setSelectedSquare(null);
    setDragFromSquare(null);
    setDragToSquare(null);
  }, []);

  const refreshPosition = useCallback(
    async (targetFen) => {
      const data = await fetchLegalMoves(targetFen);
      applyPosition(data);
      return data;
    },
    [applyPosition]
  );

  const recordMoveLocally = useCallback((move, actor) => {
    setLastMove({ from: move.slice(0, 2), to: move.slice(2, 4) });
    setMoveLog((prev) => [...prev, { by: actor, move }]);
    setTrackedSquare((prev) => {
      if (!prev) return prev;
      if (prev === move.slice(0, 2)) return move.slice(2, 4);
      return prev;
    });
  }, []);

  const clearSessionUiState = useCallback(() => {
    setThinking(false);
    setMoveLog([]);
    setLastMove(null);
    setTrackedSquare(null);
    setSearch({ ...EMPTY_SEARCH });
    setSearchTimeline([]);
  }, []);

  const appendSearchTimelineFrame = useCallback((view) => {
    setSearchTimeline((prev) => {
      const next = [
        ...prev,
        {
          eval_cp: view.eval_cp ?? 0,
          nodes: view.nodes,
          depth: view.depth,
          cutoffs: view.cutoffs
        }
      ];
      return next.slice(-64);
    });
  }, []);

  const applyMoveToPosition = useCallback(
    async (fromFen, move, actor) => {
      const data = await movePosition(fromFen, move);
      applyPosition(data);
      recordMoveLocally(move, actor);
      return data;
    },
    [applyPosition, recordMoveLocally]
  );

  const buildSearchView = useCallback((payload, whiteSign, rootSide) => {
    const evalCpWhite = (payload.eval_cp ?? 0) * whiteSign;
    const evalWhite = normalizeScore((payload.eval ?? 0) * whiteSign);
    const candidateMovesWhite = Object.fromEntries(
      Object.entries(payload.candidate_moves || {}).map(([move, evalScore]) => [
        move,
        normalizeScore(Number(evalScore) * whiteSign)
      ])
    );

    return {
      depth: payload.depth || 0,
      eval: evalWhite,
      eval_cp: evalCpWhite,
      search_side: rootSide,
      nodes: payload.nodes || 0,
      nps: payload.nps || 0,
      cutoffs: payload.cutoffs || 0,
      elapsed_ms: payload.elapsed_ms || 0,
      current_move: payload.current_move || "",
      pv: payload.pv || [],
      candidate_moves: candidateMovesWhite,
      piece_values: payload.piece_values || {},
      piece_breakdown: payload.piece_breakdown || {},
      heatmap: payload.heatmap || {}
    };
  }, []);

  const runHttpFallbackSearch = useCallback(
    async (positionFen, whiteSign, rootSide, autoPlayBestMove, token) => {
      try {
        const payload = autoPlayBestMove
          ? await engineMovePosition(positionFen, maxDepth, timeMs)
          : await analyzePosition(positionFen, maxDepth, timeMs);
        if (token !== searchTokenRef.current) return;

        const view = buildSearchView(payload, whiteSign, rootSide);
        setSearch(view);
        appendSearchTimelineFrame(view);

        if (autoPlayBestMove && payload.best_move) {
          applyPosition(payload);
          recordMoveLocally(payload.best_move, "engine");
        }
      } catch (err) {
        if (token !== searchTokenRef.current) return;
        setError(err.message || "Fallback search failed.");
      } finally {
        if (token === searchTokenRef.current) {
          setThinking(false);
        }
      }
    },
    [
      analyzePosition,
      appendSearchTimelineFrame,
      applyPosition,
      buildSearchView,
      engineMovePosition,
      maxDepth,
      recordMoveLocally,
      timeMs
    ]
  );

  const startLiveSearch = useCallback(
    (positionFen, { autoPlayBestMove }) => {
      const token = ++searchTokenRef.current;
      const rootSide = positionFen.split(" ")[1] === "b" ? "b" : "w";
      const whiteSign = rootSide === "w" ? 1 : -1;
      const watchdogMs = Math.max(4000, timeMs + 3500);
      setThinking(true);
      setError("");
      setSearch({ ...EMPTY_SEARCH });
      setSearchTimeline([]);
      lastSnapshotUiUpdateRef.current = 0;
      closeSocket();

      const socket = createSearchSocket();
      let completed = false;
      let fallbackStarted = false;
      let watchdogId = null;

      const clearWatchdog = () => {
        if (watchdogId !== null) {
          window.clearTimeout(watchdogId);
          watchdogId = null;
        }
      };

      const startHttpFallback = () => {
        if (fallbackStarted || completed || token !== searchTokenRef.current) return;
        fallbackStarted = true;
        completed = true;
        clearWatchdog();
          closeSocket();
          runHttpFallbackSearch(positionFen, whiteSign, rootSide, autoPlayBestMove, token);
        };

      const armWatchdog = () => {
        clearWatchdog();
        watchdogId = window.setTimeout(() => {
          startHttpFallback();
        }, watchdogMs);
      };

      wsRef.current = socket;
      armWatchdog();

      socket.onopen = () => {
        armWatchdog();
        socket.send(
          JSON.stringify({
            fen: positionFen,
            max_depth: maxDepth,
            time_limit_ms: timeMs,
            snapshot_interval_ms: 140
          })
        );
      };

      socket.onmessage = async (event) => {
        if (token !== searchTokenRef.current) return;

        const data = JSON.parse(event.data);
        armWatchdog();
        if (data.type === "snapshot") {
          const now = Date.now();
          if (now - lastSnapshotUiUpdateRef.current < 120) {
            return;
          }
          lastSnapshotUiUpdateRef.current = now;
          const view = buildSearchView(data, whiteSign, rootSide);
          setSearch(view);
          appendSearchTimelineFrame(view);
          return;
        }

        if (data.type === "complete") {
          completed = true;
          clearWatchdog();
          const view = buildSearchView(data, whiteSign, rootSide);
          setSearch(view);
          appendSearchTimelineFrame(view);

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
          clearWatchdog();
          if (autoPlayBestMove) {
            startHttpFallback();
          } else {
            completed = true;
            setError(data.message || "Search failed.");
            setThinking(false);
            closeSocket();
          }
        }
      };

      socket.onerror = () => {
        if (token !== searchTokenRef.current) return;
        if (!fallbackStarted) {
          startHttpFallback();
          return;
        }
        clearWatchdog();
        setError("WebSocket error while searching.");
        setThinking(false);
        closeSocket();
      };

      socket.onclose = () => {
        if (token !== searchTokenRef.current) return;
        clearWatchdog();
        if (wsRef.current === socket) {
          wsRef.current = null;
        }
        if (!completed) {
          if (!fallbackStarted) {
            startHttpFallback();
          } else {
            setThinking(false);
            setError((prev) => prev || "Search connection closed.");
          }
        }
      };
    },
    [
      appendSearchTimelineFrame,
      applyMoveToPosition,
      buildSearchView,
      closeSocket,
      maxDepth,
      runHttpFallbackSearch,
      timeMs
    ]
  );

  useEffect(() => {
    if (!trackedSquare) return;
    if (!board[squareToIndex(trackedSquare)]) {
      setTrackedSquare(null);
    }
  }, [board, trackedSquare]);

  useEffect(() => {
    if (!gameResult) {
      setShowResultOverlay(false);
      return;
    }
    setShowResultOverlay(true);
    const timer = window.setTimeout(() => setShowResultOverlay(false), 1800);
    return () => window.clearTimeout(timer);
  }, [gameResult]);

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

  const tryPlayMove = useCallback(
    async (fromSquare, toSquare) => {
      const chosenMove = pickMove(fromSquare, toSquare);
      if (!chosenMove) return false;
      try {
        setError("");
        await applyMoveToPosition(fen, chosenMove, "human");
      } catch (err) {
        setError(err.message);
      }
      return true;
    },
    [applyMoveToPosition, fen, pickMove]
  );

  const handleSquareDown = useCallback(
    (square, event) => {
      if (status !== "ongoing" || !humanTurn || thinking) return;
      event?.preventDefault();
      const piece = board[squareToIndex(square)];
      const ownColor = humanSide === "white" ? "w" : "b";
      if (piece && pieceColor(piece) === ownColor) {
        setSelectedSquare(square);
        setDragFromSquare(square);
        setDragToSquare(square);
        return;
      }

      if (selectedSquare) {
        // Support click-to-move: clicking a target square after selecting a piece.
        setDragFromSquare(selectedSquare);
        setDragToSquare(square);
        return;
      }

      setSelectedSquare(null);
      setDragFromSquare(null);
      setDragToSquare(null);
    },
    [status, humanTurn, thinking, board, humanSide, selectedSquare]
  );

  const handleSquareEnter = useCallback(
    (square) => {
      if (dragFromSquare) {
        setDragToSquare(square);
      }
    },
    [dragFromSquare]
  );

  const handleSquareTap = useCallback(
    (square) => {
      const piece = board[squareToIndex(square)];
      if (!piece) return;
      setTrackedSquare((prev) => (prev === square ? null : square));
    },
    [board]
  );

  const handleSquareUp = useCallback(
    async (square) => {
      const fromSquare = dragFromSquare || selectedSquare;
      if (!fromSquare) return;

      setDragFromSquare(null);
      setDragToSquare(null);

      if (fromSquare === square) {
        const piece = board[squareToIndex(square)];
        const ownColor = humanSide === "white" ? "w" : "b";
        if (piece && pieceColor(piece) === ownColor) {
          setSelectedSquare(square);
        } else {
          setSelectedSquare(null);
        }
        return;
      }

      const moved = await tryPlayMove(fromSquare, square);
      if (!moved) {
        const piece = board[squareToIndex(square)];
        const ownColor = humanSide === "white" ? "w" : "b";
        if (piece && pieceColor(piece) === ownColor) {
          setSelectedSquare(square);
        } else {
          setSelectedSquare(fromSquare);
        }
        return;
      }
      setSelectedSquare(null);
    },
    [board, dragFromSquare, humanSide, selectedSquare, tryPlayMove]
  );

  const loadFen = useCallback(async () => {
    try {
      setError("");
      const normalizedFen = normalizeFenInput(fenDraft);
      if (!normalizedFen) {
        setError("Please enter a valid FEN.");
        return;
      }
      searchTokenRef.current += 1;
      closeSocket();
      clearSessionUiState();
      setFenDraft(normalizedFen);
      await refreshPosition(normalizedFen);
    } catch (err) {
      setError(err.message);
    }
  }, [clearSessionUiState, fenDraft, closeSocket, refreshPosition]);

  const resetGame = useCallback(async () => {
    try {
      setError("");
      searchTokenRef.current += 1;
      closeSocket();
      clearSessionUiState();
      const data = await resetPosition();
      applyPosition(data);
    } catch (err) {
      setError(err.message);
    }
  }, [applyPosition, clearSessionUiState, closeSocket]);

  const analyzeCurrentPosition = useCallback(() => {
    if (thinking) return;
    startLiveSearch(fen, { autoPlayBestMove: false });
  }, [fen, startLiveSearch, thinking]);

  const handleTimeInputChange = useCallback((value) => {
    const digits = String(value).replace(/[^\d]/g, "");
    if (!digits) {
      setTimeMs(100);
      return;
    }
    const parsed = Number(digits);
    const clamped = Math.max(100, Math.min(15000, parsed));
    setTimeMs(clamped);
  }, []);

  return (
    <div className="page">
      <header className="hero">
        <h1 className="janus-wordmark">J A N U S</h1>
      </header>

      <main className="layout">
        <section className="panel board-panel">
          <div className="board-stage">
            <div className="board-shell">
              <ChessBoard
                fen={fen}
                orientation={humanSide}
                selectedSquare={selectedSquare}
                trackedSquare={trackedSquare}
                legalTargets={legalTargets}
                lastMove={lastMove}
                currentMove={search.current_move}
                hoveredSquare={hoveredSquare}
                dragFromSquare={dragFromSquare}
                dragToSquare={dragToSquare}
                heatmap={showHeatmap ? search.heatmap : {}}
                arrows={arrows}
                onSquareHover={setHoveredSquare}
                onSquareDown={handleSquareDown}
                onSquareUp={handleSquareUp}
                onSquareEnter={handleSquareEnter}
                onSquareTap={handleSquareTap}
              />
              {showResultOverlay && gameResult && (
                <div className="result-overlay">
                  <p className="result-score">{gameResult.score}</p>
                  <p className="result-caption">{gameResult.caption}</p>
                </div>
              )}
            </div>
          </div>

          <div className="board-info-row">
            <span>{status === "ongoing" ? `${sideLabel(sideToMove)} to move` : status.toUpperCase()}</span>
            <span>Eval {formatEval(positionEval ?? search.eval)}</span>
            <span>Depth {search.depth || 0}</span>
            <span>Nodes {search.nodes.toLocaleString()}</span>
            <span>NPS {search.nps.toLocaleString()}</span>
            <span>Cutoffs {search.cutoffs}</span>
          </div>

          <div className="eval-capsule" title="Evaluation">
            <div className="eval-capsule-white" style={{ width: `${evalFill}%` }} />
          </div>

          <div className={`thinking-dots ${thinking ? "active" : ""}`} aria-hidden={!thinking}>
            <span />
            <span />
            <span />
            <span />
          </div>

        </section>

        <div className="controls-side">
          <section className="panel controls">
            <div className="toolbar">
              <button type="button" onClick={resetGame}>
                New Game
              </button>
              <button type="button" onClick={analyzeCurrentPosition} disabled={thinking}>
                Analyze
              </button>
            </div>

            <button type="button" onClick={() => setShowHeatmap((prev) => !prev)}>
              Heatmap {showHeatmap ? "On" : "Off"}
            </button>

            <div className="compact-grid">
              <label>
                Side
                <select value={humanSide} onChange={(event) => setHumanSide(event.target.value)}>
                  <option value="white">White</option>
                  <option value="black">Black</option>
                </select>
              </label>

              <label>
                Depth
                <select value={maxDepth} onChange={(event) => setMaxDepth(Number(event.target.value))}>
                  <option value={1}>1</option>
                  <option value={2}>2</option>
                  <option value={3}>3</option>
                  <option value={4}>4</option>
                  <option value={5}>5</option>
                  <option value={6}>6</option>
                  <option value={7}>7</option>
                  <option value={8}>8</option>
                </select>
              </label>

              <label className="time-control">
                Time (ms)
                <input
                  type="text"
                  inputMode="numeric"
                  value={timeMs}
                  onChange={(event) => handleTimeInputChange(event.target.value)}
                />
                <div className="time-presets">
                  {TIME_PRESETS_MS.map((preset) => (
                    <button
                      key={preset}
                      type="button"
                      className={`time-chip ${timeMs === preset ? "active" : ""}`}
                      onClick={() => setTimeMs(preset)}
                    >
                      {preset}
                    </button>
                  ))}
                </div>
              </label>
            </div>

            <div className="info-section">
              <h2>Principal Variation</h2>
              <p className="pv-line">{formatPvLine(search.pv)}</p>
            </div>

            <div className="split-columns">
              <div className="info-section">
                <h2>Candidates</h2>
                <div className="candidate-list">
                  {candidateList.slice(0, 8).map((candidate, idx) => (
                    <div className="candidate-row" key={`${candidate.move}-${idx}`}>
                      <span>{idx + 1}</span>
                      <span>{candidate.move}</span>
                      <strong>{formatEval(candidate.eval)}</strong>
                    </div>
                  ))}
                  {!candidateList.length && <p className="muted">No candidates</p>}
                </div>
              </div>

              <div className="info-section">
                <h2>Moves</h2>
                <div className="move-table">
                  {moveRows.map((row) => (
                    <div key={`row-${row.number}`} className="move-table-row">
                      <span className="move-no">{row.number}.</span>
                      <span>{row.white || "-"}</span>
                      <span>{row.black || "-"}</span>
                    </div>
                  ))}
                  {!moveRows.length && <p className="muted">No moves</p>}
                </div>
              </div>
            </div>

            <div className="info-section">
              <h2>Search Flow</h2>
              <div className="search-flow-layout">
                <div className="timeline-shell">
                  <div className="timeline-bars">
                    {searchTimeline.map((frame, idx) => {
                      const h = Math.max(10, Math.min(58, 10 + Math.abs(frame.eval_cp || 0) / 20));
                      const positive = (frame.eval_cp || 0) >= 0;
                      return (
                        <div
                          key={`frame-${idx}`}
                          className="timeline-bar"
                          style={{ height: `${h}px`, background: positive ? "#b84f3a" : "#6f2f2f" }}
                          title={`d${frame.depth} eval ${frame.eval_cp} nodes ${frame.nodes}`}
                        />
                      );
                    })}
                    {!searchTimeline.length && <span className="timeline-empty">No search data yet</span>}
                  </div>
                </div>
                <p className="search-flow-note">
                  Each bar is one live search snapshot. Taller bars mean stronger eval swings.
                  Brighter bars favor White, darker bars favor Black.
                </p>
              </div>
            </div>

            <div className="info-section dynamic-value-panel">
              <h2>Dynamic Value</h2>
              <div className="dynamic-value-content">
                {!trackedSquare && <p className="muted">Click a piece to inspect dynamic valuation.</p>}
                {trackedSquare && !trackedPieceSymbol && (
                  <p className="muted">{trackedSquare.toUpperCase()}: empty square</p>
                )}
                {trackedSquare && trackedPieceSymbol && (
                  <div className="dynamic-value-grid">
                    <span className="k">Square</span>
                    <span>{trackedSquare.toUpperCase()}</span>
                    <span className="k">Piece</span>
                    <span>{trackedPieceName}</span>
                    <span className="k">Dynamic</span>
                    <span>{formatCp(trackedPieceDynamicValue)}</span>
                    <span className="k">Base</span>
                    <span>{formatCp(trackedPieceDetail?.base ?? BASE_VALUE_CP[trackedPieceSymbol.toLowerCase()] ?? 0)}</span>
                    <span className="k">PST</span>
                    <span>{formatCp(trackedPieceDetail?.pst ?? 0)}</span>
                  </div>
                )}
              </div>
            </div>

            {error && <p className="error">{error}</p>}

            <label className="fen-control fen-bottom">
              FEN
              <input
                className="fen-input"
                type="text"
                maxLength={120}
                value={fenDraft}
                onChange={(event) => setFenDraft(event.target.value)}
              />
              <button type="button" onClick={loadFen}>
                Load FEN
              </button>
            </label>
          </section>

          <aside
            className={`coldstart-help ${coldStartHintOpen ? "open" : ""}`}
            onMouseLeave={() => setColdStartHintOpen(false)}
          >
            <button
              type="button"
              className="coldstart-help-trigger"
              aria-label="Cold start help"
              onClick={() => setColdStartHintOpen((prev) => !prev)}
            >
              ?
            </button>
            <p className="coldstart-help-tip">
              If the backend has been idle for a while, the first engine response can take around
              30 seconds because of cold start. Please wait.
            </p>
          </aside>
        </div>
      </main>

      <section className="panel legend-panel">
        <h2>Legend</h2>
        <div className="legend-grid">
          {LEGEND_ITEMS.map((item) => (
            <article key={item.term} className="legend-item">
              <h3>{item.term}</h3>
              <p>{item.meaning}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
