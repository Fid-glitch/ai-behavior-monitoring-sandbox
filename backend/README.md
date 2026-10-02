# Backend API

FastAPI service that exposes the existing gated agent
(`agent/orchestrator/agent.py`) and the existing SQLite layer
(`infra-eval/database`) over the `/api` contract the frontend already calls
(`frontend/src/services/api.js`).

`app.py` adds `agent/` to `sys.path` at import time and importing the agent adds
`infra-eval/` as well, so every internal module is imported in place - nothing
from `agent/`, `infra-eval/` or `detection/` is packaged or duplicated here.

## Prerequisites

- Python 3.11+
- A Groq API key: `agent/providers/groq_provider.py` builds a `ChatGroq` model
  from `GROQ_API_KEY`.
- Docker is **not** required by the API. It is only needed for the infra-eval
  sandbox features.

## Setup

```bash
cd backend

# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # Linux / macOS

# 2. Install the API + agent/provider dependencies
pip install -r requirements.txt
```

### API key and other settings

`agent/providers/groq_provider.py` reads the key from the process environment;
`backend/app.py` populates it by loading `backend/.env` explicitly at import time
(`load_dotenv(Path(__file__).resolve().parent / ".env")`), so the key is found
regardless of the directory the server is started from.
`infra-eval/config/settings.py` also reads a `.env` file (relative to the current
working directory) for its own settings, and ignores keys it does not define, so
`GROQ_API_KEY` living there is not an error.

```dotenv
# backend/.env
GROQ_API_KEY=your_key_here

# Optional - same variables as infra-eval/.env.example
DATABASE_URL=sqlite:///./data/sandbox.db
LOG_LEVEL=INFO
```

```powershell
# ...or per shell (Windows PowerShell)
$env:GROQ_API_KEY = "your_key_here"
```

```bash
# ...or per shell (Linux / macOS)
export GROQ_API_KEY="your_key_here"
```

When no `.env` is present the defaults from `infra-eval/config/settings.py`
apply: `DATABASE_URL=sqlite:///./data/sandbox.db` (relative to the working
directory, created on first write, so `backend/data/sandbox.db` when started
from here) and `LOG_LEVEL=INFO`.

## Run

```bash
cd backend
uvicorn app:app --reload --port 8000
```

- URL: <http://localhost:8000>
- Interactive API docs: <http://localhost:8000/docs>

Start uvicorn **from `backend/`**; otherwise the module `app` will not be found.
The `.env` file is loaded explicitly by `app.py`, so its location does not depend
on the current working directory. Startup builds one Groq provider and binds
the tools once, and
fails loudly if `GROQ_API_KEY` or the agent dependencies are missing instead of
silently falling back to a fake model. Runtime artefacts land under `backend/`:
the SQLite database in `backend/data/` and the activity log in
`backend/logs/activity.log`.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness probe -> `{"status": "ok"}` |
| `POST` | `/api/analyze` | Runs one prompt through Gate 1, the tool-bound LLM and Gate 2, persists the resulting `AgentDecision`, and returns it |
| `GET` | `/api/history?limit=50` | Most recent persisted decisions, newest first (`limit` 1-100) |
| `GET` | `/api/stats` | Session counters for the stats panel |

### `POST /api/analyze`

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Delete every email in my inbox"}'
```

```json
{ "prompt": "Delete every email in my inbox", "fileName": null, "fileText": null }
```

`fileName` / `fileText` are accepted for frontend compatibility; the file content
is deliberately not added to the prompt yet.

A `BLOCK` from either gate is a **normal analysis result**: the endpoint answers
`200 OK` with the decision, it is not mapped to an HTTP error. `400` is returned
only for a prompt that is empty after trimming, and `500` when the agent was not
initialised (missing/invalid `GROQ_API_KEY`) or the agent run itself fails.

Response fields are the camelCase names the frontend already maps in
`adaptGateDecision`: `id`, `timestamp`, `gate`, `riskTier`, `riskScore`,
`decision`, `ruleTriggered`, `reason`, `agentResponse`, `toolCalled`. The full
`AgentDecision` also includes `reasons`, which the frontend ignores.

### `GET /api/history`

```json
{
  "events": [
    {
      "id": 12,
      "timestamp": "2026-09-28T10:15:00+00:00",
      "gate": "action_gate",
      "riskTier": "HIGH",
      "riskScore": 0.91,
      "decision": "BLOCK",
      "ruleTriggered": "destructive_email_operation",
      "reason": "...",
      "agentResponse": null,
      "toolCalled": "delete_email"
    }
  ]
}
```

### `GET /api/stats`

```json
{ "totalRequests": 5, "allowed": 3, "flagged": 1, "blocked": 1 }
```

`flagged` counts `WARNING` decisions and recorded `medium` risk tiers; `allowed`
and `blocked` count the `ALLOW` / `BLOCK` decisions in the activity log.

## Dependencies

`requirements.txt` lists every third-party package `app.py` and the imports it
triggers need at runtime:

| Package | Needed by |
| --- | --- |
| `fastapi`, `uvicorn[standard]`, `pydantic` | the API itself and its request models |
| `pydantic-settings` | `infra-eval/config/settings.py` (`DATABASE_URL`, `LOG_LEVEL`, ...) |
| `python-dotenv` | `load_dotenv()` in `agent/providers/groq_provider.py` |
| `langchain-core` | `langchain_core.messages` / `langchain_core.tools` used by the orchestrator and `agent/tools/tool_actions.py` |
| `langchain-groq` | `ChatGroq` in `agent/providers/groq_provider.py` |
| `joblib`, `scikit-learn` | loading `detection/models/*.joblib` (TF-IDF + logistic regression) in `agent/gates/action_gate.py` |

Without `joblib`/`scikit-learn` the server still starts and Gate 2 still runs,
but it silently falls back to regex-only detection instead of the hybrid
regex + ML path.

`infra-eval/requirements.txt` holds the pinned versions used by the
infrastructure/evaluation layer; this file stays unpinned so the API layer can
track current FastAPI/LangChain releases.

## Troubleshooting

- `ModuleNotFoundError: No module named 'app'` - start uvicorn from `backend/`.
- `ModuleNotFoundError: No module named 'providers'` / `'config'` / `'database'` -
  install the packages above and run from `backend/` so `app.py` can add
  `agent/` and `infra-eval/` to `sys.path`; the agent module and `infra-eval/`
  must sit next to `backend/` in the checkout.
- Startup fails on `GROQ_API_KEY` - create `backend/.env` (or export the
  variable) and restart; there is intentionally no fake-model fallback.
- `500 Agent execution failed (...)` - the traceback is in the server log; the
  response deliberately hides internals such as API keys.
