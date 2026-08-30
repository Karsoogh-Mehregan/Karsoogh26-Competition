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

**`graph_data.json` is the map's single source of truth.** `frontend/src/data/graph_data.json`
(473 nodes, 780 edges) is static with **no generator in this repo**; each node carries baked-in
`x`/`y`/`color`/`shape`/`theta`/`r`, so there is no layout engine. Those layout fields stay
frontend-only; the backend takes just the topology, via
`uv run manage.py import_graph` (`game/management/commands/import_graph.py`), so `game.Node.code`
holds the same ids the SPA uses (`L1_0`, `CENTER`, …). Re-running upserts and never deletes,
so `Occupancy`'s `PROTECT` FK is safe mid-game. `TYPE_TO_LEVEL` in that command maps the 11
frontend `type` values onto the four playable levels plus `toll`; the `c34`/`c45` connectors are
imported as `toll` nodes with no `FloorReward` rows, which makes them inert — their real
pass-through rules are not designed yet. The Vite dev server proxies `/api` to `:8000` so
session cookies stay same-origin. The side panel lists teams from the API; the map
is locked until the mentor is logged in (clicks do nothing, nodes stay disabled).
The map itself is still a local adjacency demo, not a game move.

**Auth / acting-as.** Mentors are any user holding `game.act_as_mentor` (`IsMentor`). The
team a mentor acts for is **a path segment, never server state**: `/api/teams/<team_code>/…`,
as in `claim-start/` and the `MentorActionView` routes. There is no `act-as` endpoint and no
session key; the SPA owns the selection (`localStorage`, `useActing.js`). A team-scoped
endpoint therefore MUST keep `permission_classes = [IsMentor]` — a mentor may act for any
team, so the URL is the whole authorisation story. When non-mentor players get endpoints,
those must check `request.user.team_id` against the URL team.
`GET /api/auth/csrf/` (`@ensure_csrf_cookie`) is the SPA's
CSRF entry point and also returns `{"csrf_token": "..."}` so the SPA does not have
to scrape `document.cookie`. `login()` rotates the token, and the login response
sets the new cookie. `GameIsRunning` rejects actions unless `GameSettings.load().is_running`;
apply it to move/duel/questions, not to auth or the team picker.
`STATIC_URL` must start with `/` (`"/static/"`) or Django's StaticFilesHandler will
not serve admin CSS.

**The root `README.md` is a roadmap, not a description.** SSE, Pinia, TanStack Query,
and panzoom are installed but unwired. shadcn-vue is in use in the team picker.

**Occupancy is append-and-soft-release.** Rows are never deleted; a release sets
`released_at`. Every uniqueness rule is therefore a *partial* constraint scoped to
`released_at__isnull=True`. Query current state via `.active()` or you will see history.
`Edge` is normalised by `CheckConstraint(a__lt=F("b"))` — construct edges lower-id-first.

**SQLite gives false passes.** `select_for_update()` is ignored, not rejected, so
`conftest.py` force-skips `postgres_only` tests off Postgres. `uv run pytest` on SQLite
gives 111 passed / 2 skipped; on Postgres, 113 passed. Run row-lock work against real
Postgres. CI does.

**Money is Decimal-from-string, rounded half-up** (`_round_half_up`, since Python defaults
to banker's rounding). `FloorReward.networth`/`duel_cost`/`buyout_cost` are derived
properties, not columns. `GradeMultiplier.factor_for()` raises unless a `grade=0` row is
seeded; `game/migrations/0002_seed_economy.py` does that. The two ruff ignores in
`pyproject.toml` are deliberate and documented — do not "fix" them.

**Frontend.** `useGraph()` is a module-level singleton, so all callers share one reactive
`path` ref. Adjacency is built direction-agnostically, so the 102 `directed` edges draw
arrowheads but do not constrain traversal. The side panel is the team picker (`InfoPanel`):
it lists `GET /api/teams/` and selects locally — `useActing()` is a second module-level
singleton holding `actingTeam` (persisted as a team code in `localStorage`, re-matched
against the team list on bootstrap), and that code is what team-scoped URLs are built
from. Selecting a team hits no endpoint. The UI is Persian and
RTL; fonts are self-hosted in `src/assets/fonts/` via `--font-primary`/`--font-secondary` —
do not reintroduce a Google Fonts CDN import. Entry point is `src/main.js`; `App.vue` and
`useGraph.js` are plain JS despite the TS config.

**Build UI from the shadcn-vue components in `src/components/ui/`** (Reka UI + Tailwind +
`cva`) rather than hand-rolling markup or bespoke scoped CSS. Available today: badge,
button, card, dialog, input, label, sheet, skeleton, sonner, textarea. Import via the
`@/components/ui/...` alias. Need one that is missing? Add it with
`npx shadcn-vue@latest add <name>` — do not write it by hand; the CLI wires variants and
Reka primitives that hand-written copies get wrong. `src/style.css` imports Tailwind v4
and the shadcn token theme; `components.json` has `"rtl": true`.
