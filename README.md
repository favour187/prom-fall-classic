# Prom Fall Classic

> Competition-specific build pending rule verification.

ON HOLD — event rules unverified as of Sep 6, 2026. No submission will be made from this repo until the organizer's rules (build window, eligibility) are confirmed.

| | |
|---|---|
| **Event** | Prom Fall Classic (unverified — no public listing found) |
| **Theme / Track** | Unknown — awaiting organizer link/email |
| **Build window** | Unknown |
| **Deadline** | Unknown |
| **Event verified** | ⚠️ No — see docs/COMPLIANCE.md |

## What is in this repository

This repository currently contains the **shared engineering foundation** plus
a placeholder for the competition-specific product:

- `app/core/` — generic backend infrastructure: config, logging, error
  handling, HTTP factory, rate limiting, SQLAlchemy database layer, PBKDF2
  authentication with opaque session tokens, and an AI integration layer
  (remote LLM via an OpenAI-compatible API **with a deterministic local
  fallback**, so the demo runs with zero API keys).
- `app/features/event/` — **competition-specific module** (placeholder
  status router right now; the real product logic lands in its own build
  phase so it stays cleanly separated from the foundation).
- `web/` — React + TypeScript + Vite app shell with a typed API client,
  shared UI components (buttons, cards, inputs, badges, progress bars,
  modals), light/dark design tokens, and a dev proxy `/api -> :8000`.

The foundation is intentionally generic and is shared verbatim across the
other hackathon repos; **all competition-specific logic lives only in
`app/features/`** and is unique to this repo. See
[docs/COMPLIANCE.md](docs/COMPLIANCE.md) for per-event compliance notes.

## Quick start (backend)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/api/docs
- Health: http://localhost:8000/api/health
- Demo account (development only): `demo@example.com` / `demo-password-123`

## Run the tests

```bash
python -m pytest
```

## Quick start (web)

```bash
cd web
npm install
npm run dev        # http://localhost:5173 (proxies /api to :8000)
npm run build      # type-check + production build into web/dist
```

## AI configuration

| Variable | Default | Notes |
|---|---|---|
| `AI_MODE` | `auto` | `auto` (remote when a key exists, local otherwise), `remote`, `local` |
| `AI_BASE_URL` | `https://api.openai.com/v1` | any OpenAI-compatible endpoint |
| `AI_API_KEY` | *(empty)* | empty => deterministic local demo provider |
| `AI_MODEL` | `gpt-4o-mini` | |

With no key configured the app is fully functional via the local fallback;
with a key the real LLM powers the same flows. `POST /api/demo/ai-ping`
(development) is a smoke test for the gateway.

## Deployment

- `Dockerfile` + `docker compose up --build` serve the app with the built
  frontend on port 8000.
- `.github/workflows/ci.yml` runs backend tests and a frontend build on every
  push.
- `Makefile` wraps the common commands.

## Repo state

First commit: **Sep 6, 2026** (inside the event's build window).
Status: ON HOLD — event rules unverified as of Sep 6, 2026. No submission will be made from this repo until the organizer's rules (build window, eligibility) are confirmed.

**AI tools disclosure:** development in this repository is assisted by AI
coding tools (Claude-based agent tooling on the Arena.ai platform). All
submitted work is the author's own project; AI-generated sections of code are
reviewed, understood and validated by the author before commit. If the target
event requires a disclosure field at submission, this statement is reproduced
there.


## License

MIT — see [LICENSE](LICENSE).
