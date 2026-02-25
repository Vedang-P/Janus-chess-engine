export const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

function wsBaseFromApi(apiBase) {
  return apiBase.replace(/^http/, "ws").replace(/\/$/, "");
}

async function post(path, payload = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (body?.detail) {
        detail = String(body.detail);
      }
    } catch {
      // Keep generic detail fallback.
    }
    throw new Error(detail);
  }

  return response.json();
}

export function fetchLegalMoves(fen) {
  return post("/legal-moves", { fen });
}

export function movePosition(fen, move) {
  return post("/move", { fen, move });
}

export function resetPosition(fen) {
  if (!fen) {
    return post("/reset", {});
  }
  return post("/reset", { fen });
}

export function createSearchSocket() {
  return new WebSocket(`${wsBaseFromApi(API_BASE)}/ws/search`);
}
