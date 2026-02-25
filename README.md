# JANUS: Chess Engine + Live Analysis Platform

<p align="center">
  <img src="frontend/public/janus-logo.jpg" alt="JANUS logo" width="180" />
</p>

**JANUS** is a performance-oriented classical chess engine with a real-time web visualization interface.

It combines:
- **Correct engine fundamentals** (bitboards, legal move generation, perft-tested correctness)
- **Search + evaluation transparency** (live PV, candidate moves, eval trends, piece breakdowns)
- **Production-style architecture** (FastAPI + WebSockets backend, React/SVG frontend)

This project is designed to be understandable for newcomers while still technically rigorous for engineers.

## What This Project Does
At a high level, JANUS lets you:
1. Play moves on an interactive board.
2. Run live engine analysis in real time.
3. See *why* the engine prefers a move through visual telemetry and dynamic piece valuation.

Unlike opaque chess bots, JANUS exposes internal search behavior as the engine thinks.

## Core Capabilities
- 64-bit bitboard board representation
- Full legal move generation with make/unmake
- Perft correctness testing against known reference values
- Iterative deepening negamax + alpha-beta pruning
- Time-controlled search
- Handcrafted centipawn evaluation:
  - material
  - piece-square tables
  - mobility
  - king safety
  - pawn structure
- Live instrumentation stream over WebSocket
- Interactive React + SVG analysis UI with:
  - search flow graph
  - principal variation
  - candidate move rankings
  - dynamic piece value inspection
  - board heatmaps

## Workflow Visualization

### Search / Telemetry Flow
![Search Flow](docs/images/search-flow.svg)

### UI Overview
![UI Overview](docs/images/ui-overview.svg)

## Tech Stack
- **Backend:** Python 3.11+, FastAPI, Uvicorn
- **Frontend:** React (Vite), SVG rendering
- **Engine:** Custom implementation (no heavy engine libraries)
- **Transport:** REST + WebSockets
- **Deployment:** Render (backend) + Cloudflare Pages (frontend)

## Repository Structure
```text
chess_engine/
├── api/                  # FastAPI server + websocket routes
├── engine/               # Core chess engine modules
├── frontend/             # React app (Vite)
├── tests/                # Perft + movegen + integration tests
├── docs/images/          # Visual assets for docs
├── Dockerfile            # Backend container
├── render.yaml           # Render service config
└── README.md
```

## Local Setup
### Prerequisites
- Python **3.11+**
- Node.js **18+** (or newer)
- npm

### 1) Clone and install backend
```bash
cd /path/to/your/workspace
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Install frontend
```bash
cd frontend
npm install
cd ..
```

## Run Locally
Open two terminals.

### Terminal A: backend
```bash
cd /path/to/<your-repo>
source .venv/bin/activate
python3 -m uvicorn api.server:app --host 127.0.0.1 --port 8000 --reload
```

### Terminal B: frontend
```bash
cd /path/to/<your-repo>/frontend
cp .env.example .env
npm run dev
```

Open the frontend URL shown by Vite (usually `http://127.0.0.1:5173`).

## How to Use (Quick)
1. Start a new game from the right panel.
2. Move pieces by drag-and-drop or click-to-move.
3. Click **Analyze** to run engine evaluation for the current position.
4. Use **Heatmap On/Off** to toggle board heat overlays.
5. Click any piece to lock its **Dynamic Value** panel.
   - Click another piece to switch tracking.
   - Click the same tracked piece again to deselect.

## Correctness and Testing
Engine correctness is validated with perft tests.

Known results:

| Position | Depth | Expected | Actual |
|---|---:|---:|---:|
| Start position | 1 | 20 | 20 |
| Start position | 2 | 400 | 400 |
| Start position | 3 | 8902 | 8902 |
| Start position | 4 | 197281 | 197281 |
| Kiwipete | 2 | 2039 | 2039 |
| Kiwipete | 3 | 97862 | 97862 |

Run all tests:
```bash
python3 -m pytest -q
```

## Performance Snapshot (Local)
Example measurements on this implementation:
- Search benchmark (start position, `max_depth=5`, `time_limit_ms=4000`)
  - completed depth: `3`
  - nodes: `3084`
  - nps: `5804`
  - elapsed: `531 ms`
- Perft benchmark (start position, depth 4)
  - nodes: `197281`
  - elapsed: `2555 ms`
  - nps: `77213`

## Deployment (Beginner-Friendly, Free)
Recommended stack:
- **Backend:** Render Free Web Service
- **Frontend:** Cloudflare Pages

### A) Deploy backend on Render
This repo already includes:
- `Dockerfile`
- `render.yaml`

Steps:
1. Push this repo to GitHub.
2. In Render: **New -> Web Service -> Connect repo**.
3. Render should detect Docker automatically.
4. Use Free plan.
5. After deploy, verify:
   - `https://<your-backend>.onrender.com/health`
   - should return `{"status":"ok"}`

### B) Deploy frontend on Cloudflare Pages
1. In Cloudflare: **Workers & Pages -> Create -> Pages -> Connect to Git**.
2. Select this repo.
3. Set build config:
   - Root directory: `frontend`
   - Build command: `npm run build`
   - Build output directory: `dist`
4. Add environment variable:
   - `VITE_API_BASE=https://<your-backend>.onrender.com`
5. Deploy.

### C) Final shareable URL
Use your Cloudflare Pages domain (or custom domain) as the public project URL.

## Troubleshooting
- Frontend loads but moves/analyze fail:
  - Check `VITE_API_BASE` points to deployed backend URL.
- First analysis call is slow on free tier:
  - Render free service may be waking from idle sleep.
- WebSocket issues in production:
  - Confirm backend is HTTPS and frontend uses that HTTPS API base.

## Known Limitations
- No transposition table / Zobrist hashing yet
- No quiescence search yet
- No opening book or tablebases in engine loop
- Search strength is correctness-first; further performance tuning is possible

## Why This Project Is Resume-Ready
- Demonstrates algorithmic depth (movegen/search/eval)
- Shows correctness discipline (perft gate + tests)
- Includes real-time observability and explainability
- Ships as a full-stack deployable product
