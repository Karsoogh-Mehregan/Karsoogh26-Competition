# AGENTS.md

Guidance for coding agents working in this repository.
This is the canonical instruction file; `CLAUDE.md` imports it.

<!-- BEGIN:stack-version-rules -->

# ALWAYS search and read the docs before coding

This stack runs ahead of your training data. Do not write code from recall.

1. **Search the official docs** for the API you are about to use.
2. **Confirm against the installed version.** Versions are pinned in
   `backend/pyproject.toml` and `frontend/package.json`; the code itself is in
   `backend/.venv/lib/python*/site-packages/` and `frontend/node_modules/`.
   Neither ships a `docs/` dir, so read the source and the `.d.ts`.

Wrong recall here fails *silently* rather than loudly. Two examples: Django 6
renamed `CheckConstraint(check=)` to `condition=`, and Tailwind 4 has no
`tailwind.config.js` at all — a v3 config file is ignored, not rejected.

<!-- END:stack-version-rules -->

## Commands

Backend, in `backend/` (`SECRET_KEY` is the only required env var — `cp .env.example .env`):

```bash
uv sync                                   # .venv from uv.lock
uv run manage.py migrate
uv run manage.py runserver                # :8000, /admin/, /api/docs/ (DEBUG only)

uv run pytest
uv run pytest tests/test_constraints.py::TestCapacity                 # one class
uv run pytest tests/test_concurrency.py::test_only_one_team_wins_the_last_slot
uv run pytest -k slot                     # by substring
uv run pytest -m postgres_only            # row-lock tests only

uv run ruff check .
uv run ruff format --check .              # CI gate
uv run manage.py makemigrations --check --dry-run
```

Frontend, in `frontend/` (no test runner, no ESLint config):

```bash
npm run dev        # :3000, bound to 0.0.0.0
npm run build      # vue-tsc -b && vite build — type errors fail the build
```

PostgreSQL: `docker compose up -d db` from the repo root, then set `DATABASE_URL`.

## Architecture

**The frontend map and the backend graph are unrelated.** `frontend/src/data/graph_data.json`
(355 nodes) is static with **no generator in this repo**; each node carries baked-in
`x`/`y`/`color`/`shape`, so there is no layout engine. Django's `game.Node`/`game.Edge`
share no ids or vocabulary with it. The SPA still makes zero network calls; the Vite
dev server proxies `/api` to `:8000` so session cookies will be same-origin once the
frontend is wired. Clicking the map is a local adjacency demo, not a game move.

**Auth / acting-as.** Mentors are any authenticated user (`IsMentor`). They pick a team
via `POST /api/auth/act-as/` which stores `request.session["acting_team_id"]`. Every
game endpoint must call `accounts.acting.resolve_acting_team(request)` — do not read
the session key directly. `GET /api/auth/csrf/` (`@ensure_csrf_cookie`) is the SPA's
CSRF entry point; `login()` rotates the token, and the login response sets the new
cookie. `GameIsRunning` rejects actions unless `GameSettings.load().is_running`; apply
it to move/duel/questions, not to auth or the team picker.

**The root `README.md` is a roadmap, not a description.** SSE, Pinia, TanStack Query,
panzoom and shadcn-vue are installed but unwired.

**Occupancy is append-and-soft-release.** Rows are never deleted; a release sets
`released_at`. Every uniqueness rule is therefore a *partial* constraint scoped to
`released_at__isnull=True`. Query current state via `.active()` or you will see history.
`Edge` is normalised by `CheckConstraint(a__lt=F("b"))` — construct edges lower-id-first.

**SQLite gives false passes.** `select_for_update()` is ignored, not rejected, so
`conftest.py` force-skips `postgres_only` tests off Postgres. `uv run pytest` on SQLite
gives 49 passed / 1 skipped; on Postgres, 50 passed. Run row-lock work against real
Postgres. CI does.

**Money is Decimal-from-string, rounded half-up** (`_round_half_up`, since Python defaults
to banker's rounding). `FloorReward.networth`/`duel_cost`/`buyout_cost` are derived
properties, not columns. `GradeMultiplier.factor_for()` raises unless a `grade=0` row is
seeded; `game/migrations/0002_seed_economy.py` does that. The two ruff ignores in
`pyproject.toml` are deliberate and documented — do not "fix" them.

**Frontend.** `useGraph()` is a module-level singleton, so all callers share one reactive
`path` ref — that, not props or a store, syncs `GraphView` and `InfoPanel`. Adjacency is
built direction-agnostically, so the 102 `directed` edges draw arrowheads but do not
constrain traversal. The UI is Persian and RTL; fonts are self-hosted in
`src/assets/fonts/` via `--font-primary`/`--font-secondary` — do not reintroduce a Google
Fonts CDN import. Entry point is `src/main.js`; `App.vue` and `useGraph.js` are plain JS despite the TS config.

**Build UI from the shadcn-vue components in `src/components/ui/`** (Reka UI + Tailwind +
`cva`) rather than hand-rolling markup or bespoke scoped CSS. Available today: badge,
button, card, dialog, input, label, sheet, skeleton, sonner, textarea. Import via the
`@/components/ui/...` alias. Need one that is missing? Add it with
`npx shadcn-vue@latest add <name>` — do not write it by hand; the CLI wires variants and
Reka primitives that hand-written copies get wrong.

Two prerequisites, both currently unmet, so fix them before the first `<Button>` lands:
`src/style.css` never does `@import "tailwindcss"`, so no utility classes are emitted and
every one of those components renders unstyled; and `components.json` has `"rtl": false`
while the app is RTL, so CLI output needs an RTL pass. Nothing currently imports
`src/components/ui/` — the whole set is dead code until the Tailwind import exists.
