export const FILES = "abcdefgh";

export function squareToIndex(square) {
  const file = square.charCodeAt(0) - 97;
  const rank = Number(square[1]) - 1;
  return rank * 8 + file;
}

export function indexToSquare(index) {
  const file = index % 8;
  const rank = Math.floor(index / 8);
  return `${String.fromCharCode(97 + file)}${rank + 1}`;
}

export function parseFenBoard(fen) {
  const board = Array(64).fill(null);
  const [placement = "8/8/8/8/8/8/8/8"] = fen.split(" ");
  const ranks = placement.split("/");

  if (ranks.length !== 8) {
    return board;
  }

  for (let rank = 0; rank < 8; rank += 1) {
    let file = 0;
    for (const char of ranks[rank]) {
      if (/\d/.test(char)) {
        file += Number(char);
      } else if (file < 8) {
        const sq = (7 - rank) * 8 + file;
        board[sq] = char;
        file += 1;
      }
    }
  }

  return board;
}

export function pieceColor(piece) {
  if (!piece) return null;
  return piece === piece.toUpperCase() ? "w" : "b";
}

export function moveToArrow(move, color = "#ff8243", width = 9, opacity = 0.86) {
  if (!move || move.length < 4) return null;
  return {
    from: move.slice(0, 2),
    to: move.slice(2, 4),
    color,
    width,
    opacity
  };
}

export function formatCp(scoreCp) {
  if (scoreCp === null || scoreCp === undefined) return "--";
  const sign = scoreCp > 0 ? "+" : "";
  return `${sign}${(scoreCp / 100).toFixed(2)}`;
}

export function formatEval(evalPawns) {
  if (evalPawns === null || evalPawns === undefined) return "--";
  const sign = evalPawns > 0 ? "+" : "";
  return `${sign}${Number(evalPawns).toFixed(2)}`;
}
