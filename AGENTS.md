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
uv run manage.py create_team_users --fund --csv teams.csv  # one login per team

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

## Migrations must never destroy data

This deploys to a production server that holds a live game. A migration may add,
backfill, tighten and drop *schema*; it may never delete or truncate rows to make
a schema change apply, and "the table is empty in CI" is not a reason — CI and
`pytest` always start from an empty database, so a migration that only works on
one passes every gate here and fails on the real server.

Adding a non-nullable column or FK is the usual trap: a bare non-null `AddField`
raises `IntegrityError` against any table that already has rows. Do it in three
operations instead — `AddField(null=True)`, a `RunPython` that backfills every
existing row, then `AlterField` tightening it to non-null. Where a backfill has
no correct value to write, pick a defensible one and say why in the migration's
docstring; if it cannot be picked safely, raise from the `RunPython` with an
instruction for the operator rather than dropping the rows.
`minesweeper/migrations/0002_minesweepergame_node.py` is the worked example.

Give every `RunPython` a reverse (`migrations.RunPython.noop` when the forward
step needs no undo) so a deploy can roll back, and test any migration that
touches existing rows against a database that actually has some.

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

**Auth / acting-as.** The event is played online: each team logs in as itself, one shared
account per team (`accounts.User.team`, username = `Team.code`), created by
`create_team_users`. Mentors are any user holding `game.act_as_mentor` (`IsMentor`) and no
longer move for a team — they only grade/release. A team-scoped endpoint (`claim-start/`,
`assign-question/`) is `permission_classes = [IsAuthenticated, IsOwnTeam, GameIsRunning]`:
`IsOwnTeam` (`game/permissions.py`) requires the `<team_code>` path segment to equal
`request.user.team.code`, so the URL is a claim the server verifies, not the whole
authorisation story. `grade/`, `release/` and `/api/submissions/…` stay `[IsMentor]`.
There is no `act-as` endpoint and no session key for mentors; the SPA still owns which team
a mentor is *viewing* (`localStorage`, `stores/acting.ts`) — that selection carries no
authority now, unlike a team's own session.
`GET /api/auth/csrf/` (`@ensure_csrf_cookie`) is the SPA's
CSRF entry point and also returns `{"csrf_token": "..."}` so the SPA does not have
to scrape `document.cookie`. `login()` rotates the token, and the login response
sets the new cookie. `GET /api/auth/me/` returns `is_mentor` (`has_perm("game.act_as_mentor")`,
not `is_staff`) and `team` (`{code, name}` or `null`) so the SPA can tell the two roles apart.
`GameIsRunning` rejects actions unless `GameSettings.load().is_running`; it is wired into the
two move endpoints above (closing a prior hole where `claim-start/` worked before the game
started) plus duel/questions, not auth or the team picker.
`STATIC_URL` must start with `/` (`"/static/"`) or Django's StaticFilesHandler will
not serve admin CSS.

**Four roles, not two.** Besides mentors (`act_as_mentor`), game gods
(`control_game`) and announcers (`send_announcement`, see **Notifications** below), a
**Designer** holds `game.design_map` (`IsDesigner`, `Designers` group,
`is_designer` on `/api/auth/me/`) and may change only how the board *looks*: neighbourhood
names/themes/colours and road style via `PATCH /api/map/design/`, and a per-node building-type
pin or tier move via `PATCH /api/map/nodes/<code>/`. A tier move is refused (409) while any team
holds a seat on the node, because capacity and entry cost hang off `Node.level`. Every logged-in
client reads `GET /api/map/design/` — **this is now the level-of-record for the SPA map**;
`frontend/src/lib/mapLevels.ts` mirrors `TYPE_TO_LEVEL` only as the fallback before that query
answers. Building-type keys are duplicated on purpose in `backend/game/design.py` and
`frontend/src/lib/house/archetypes.ts`; add to both. Sector membership is *not* stored: it is
`floor(theta / 45)` computed client-side (`lib/mapNeighborhoods.ts`), which lines up with the
connectivity groups in `generateGraph.mjs`. The 3D house panel, its rebuild-vs-repaint
invariant, and the Designer UI are documented in `docs/house-view.md` — read it before touching
`frontend/src/lib/house/`.

**Notifications are two models, fanned out at send time.** The `notifications` app splits
"what was written" (`Message` — body plus the audience it was aimed at) from "who has read
it" (`Notification` — one row per recipient). `services.send_message` resolves the audience
*once*, at send, and writes a row each: read state needs a row anyway, the bell's unread
count is then one indexed query, and a mentor added to a group an hour later must not
retroactively appear to have been addressed. A draft has no `Notification` rows at all.
The author is excluded from their own fan-out — an announcement belongs in Sent, not in its
writer's bell. **Nothing in `game/` writes to the inbox.** An earlier cut had the board narrate
itself (grade posted, attempt expired, clock started); it was removed deliberately in
`notifications/migrations/0006` — a notification per board event is noise, and noise is how a
player learns to ignore the bell. What the board did is on the board. If an organiser wants the
hall told the game has started, they send it.

**The audience is a union of three selections, not one choice.** `Message.scopes` is a list
of `AudienceScope` values (`all` / `teams` / `mentors` / `designers`), and `Message.teams`
and `Message.users` are M2Ms naming particular ones — so "these four teams plus every
mentor" is one message. `services.resolve_audience` takes plain values so the composer's
`POST /api/messages/audience-preview/` can count a selection that has not been saved yet;
`recipients_for` is the thin wrapper over a saved row. Two traps live in there: it starts
from `Q(pk__in=[])` because a bare `Q()` matches *everyone*, and `all` short-circuits the
rest. Migrations 0004/0005 replaced the old single-target `audience`/`audience_team`/
`audience_user` columns and backfilled them, so `scopes=['teams']` is what an old "all
teams" row now looks like. An empty audience is legal on a draft and refused on send.
`services.users_with_perm` resolves the mentor/designer scopes by *explicit* grant and
deliberately not through `has_perm`, which is True for every superuser; same reasoning as
`accounts.permissions.has_game_god_rights`. A permission that does not exist yet
(`game.design_map` predates the designer work landing) resolves to an empty audience rather
than raising. Sending is gated on `notifications.send_announcement`
(`CanSendAnnouncement`), backed by its own **Notifier** group — running the clock and
speaking to the hall are different jobs, so `migrations/0003` moved the grant off GameGods
onto Notifier and deliberately did *not* carry the members across — the group starts empty,
and someone who does both jobs goes in both groups.
`/api/auth/me/` reports it as `is_announcer`, and the SPA hides the composer on that flag
rather than on `is_game_god`. A message has a page of its own on both sides — `/inbox/:id`
reads one (`GET /api/notifications/<pk>/`, which deliberately does *not* mark it read, so
the page posts to `notifications/read/` instead of a GET mutating state) and `/messages/:id`
shows read receipts (`GET /api/messages/<pk>/recipients/`, unread first via an explicit
`nulls_first` — Postgres and SQLite disagree on where NULLs land by default). Inline
expansion was removed: it broke on long bodies, and any card, title or body that can hold
pasted text sets `overflow-wrap: anywhere`, because a line clamp alone still lets one
unbroken token push the layout sideways. The automatic half lives in
`notifications/alerts.py`, one function per moment, every one best-effort: an alert that
raises is logged and swallowed, because a notification must never roll back the move that
caused it. `game/` calls those with a **local import inside the function** — `notifications`
reaches back into `game.services.events` for the publisher, so a module-level import would
close the loop.

**SSE frames can be addressed.** `publish(..., recipients=[user_id, ...])` puts the ids in
their own stream field (`u`), never in the payload, and `game.sse._visible_to` drops the
frame for anyone not named — so a notification hint does not tell the whole hall who got
mail. An empty `recipients` still means everyone, so nothing else changed. As ever the frame
is only a hint: the client refetches `GET /api/notifications/`.

**The root `README.md` is a roadmap, not a description.** SSE and panzoom are installed
but unwired. Pinia and TanStack Query are wired (see **Frontend data layer**).
shadcn-vue is in use in the team picker.

**A move is one call.** `POST teams/<code>/nodes/<code>/assign-question/` reserves the node
*and* starts the attempt clock (`services.claim_node`): there is no separate "enter" endpoint,
because reserving without a question is not a game state. Reserving is not owning — the floor
is captured at grading. The target must be reachable from a holding that *expands* — a spawn,
or a node the team has already been graded on. An ungraded reservation is a dead end until it
is graded, and released rows never extend reach; reach follows `Edge.directed` one-way where
set. A team with no active holdings may only take the start node matching its `Team.color`.
It costs `LevelConfig.entry_cost` and takes the lowest free slot up to `capacity`. Posting
again to a node the team already holds only tops up a missing question — it never charges
twice. The team answers through `POST /api/occupancies/<pk>/question/` and
`/submit/` (`IsTeamMember`, ownership enforced inside `submit_answer`); a mentor grades the
resulting `Submission` through `/api/submissions/…`, so `assign-question/`'s response carries
no `submission_id` — none exists until the team actually answers.
`POST teams/<code>/claim-start/` is the other half — it writes the team's colour *and* seats
it on the matching spawn node (`services.claim_spawn`), which is what unblocks the first
`assign-question`. It is itself gated on the entry sheet (below). `grade/` and `release/`
still address an existing holding and 404 without one.

**The entry sheet gates the spawn.** Before a team may claim a start node it must clear
`GameSettings.entry_required_correct` of the `entry_question_count` questions on its sheet
(defaults: 2 of 3). `EntryQuestion.answer` is an **integer**, so `services/entry.py` grades
the moment a team submits — no mentor, no `Submission`, no `Occupancy`; this is a separate
model from `Question` precisely because the sheet is answered before a team holds any node.
`GET /api/entry/sheet/` draws the sheet on first read (least-served + random tiebreak, same
as `assign_question`) and is stable after that; `POST /api/entry/questions/<code>/answer/`
is one answer per *try* — a second POST is a 409. A team that got one wrong may open a
fresh try at **the same question** via `POST /api/entry/questions/<code>/retry/`, up to
`entry_max_retries` times across the whole sheet (default 3; 0 makes every answer final).
The question never changes — only the initial sheet draw picks questions. A retry
soft-retires the failed `EntryAttempt` (`superseded_at`, the same append-and-retire shape
as `Occupancy`) and opens a new row for the same question at the same `position`, so every
guess stays on the record; `entryattempt_no_repeat` is therefore scoped to current rows.
Read the sheet through `EntryAttempt.objects.current()` or you will see superseded tries.
Clearing the sheet stamps `Team.draft_order` (finishing order). After
`entry_grace_minutes` past `GameSettings.started_at` — stamped once, the first time status
becomes running — the gate opens for everyone regardless, per the design doc. There are no
seed commands: fill the pool through the admin, and create logins with
`create_team_users --fund`, which tops every team up to `GameSettings.initial_balance`
(400 — the design doc's 200+200, paid to every team whether it cleared the sheet or only
waited out the grace).

**Occupancy is append-and-soft-release.** Rows are never deleted; a release sets
`released_at`. Every uniqueness rule is therefore a *partial* constraint scoped to
`released_at__isnull=True`. Query current state via `.active()` or you will see history.
`Edge` is normalised by `CheckConstraint(a__lt=F("b"))` — construct edges lower-id-first.

**SQLite gives false passes.** `select_for_update()` is ignored, not rejected, so
`conftest.py` force-skips `postgres_only` tests off Postgres. `uv run pytest` on SQLite
gives 501 passed / 6 skipped; on Postgres, 507 passed. Run row-lock work against real
Postgres. CI does — and CI is the only place the skipped six ever run, so a break in them
surfaces on the PR, not on your machine.

**A `transaction=True` test starts on a flushed database.** `TransactionTestCase`
truncates every table at teardown, migration-seeded rows included, so the next
transactional test finds no `LevelConfig` and no `GradeMultiplier`. `conftest.py`'s
`_reseed_after_flush` re-runs the economy seed migrations for those tests; a transactional
test that needs the group or map-design seeds adds its migration to `_SEED_MIGRATIONS`
rather than restating the rows. Never rely on being the first transactional test in the
session — that green flips the moment a test file lands ahead of yours alphabetically.

**Money is Decimal-from-string, rounded half-up** (`_round_half_up`, since Python defaults
to banker's rounding). `FloorReward.networth`/`duel_cost`/`buyout_cost` are derived
properties, not columns. `GradeMultiplier.factor_for()` raises unless a `grade=0` row is
seeded; `game/migrations/0002_seed_economy.py` does that. The two ruff ignores in
`pyproject.toml` are deliberate and documented — do not "fix" them.

**Frontend.** `useGraph()` is a module-level singleton, so all callers share one reactive
`path` ref. Adjacency is built direction-agnostically, so the 102 `directed` edges draw
arrowheads but do not constrain traversal. The side panel is the team picker (`InfoPanel`):
it lists `GET /api/teams/` and selects locally. Selecting a team hits no endpoint. The UI
is Persian and RTL; fonts are self-hosted in `src/assets/fonts/` via
`--font-primary`/`--font-secondary` — do not reintroduce a Google Fonts CDN import.
Entry point is `src/main.ts`; `App.vue`, `useGraph.js`, `startColors.js`, `GraphView.vue`
and `InfoPanel.vue` are still plain JS — `tsconfig.app.json` sets `allowJs` with
`checkJs: false`, so they resolve but are not type-checked.

**Frontend data layer — one direction only.** `lib/http.ts` (transport: CSRF, JSON,
`ApiError`) ← `services/*.ts` (the only place URL strings live) ← `queries/*.ts`
(TanStack Query keys, queries, mutations) ← `composables/useActing.ts` (the facade
components use). A component never imports `http.ts`. Server state belongs to Query,
keyed through `queries/keys.ts` — never write a bare `['teams']` array elsewhere, and
never hand-merge a cached list; invalidate instead. Client state (which team the mentor
acts for) is the Pinia store `stores/acting.ts`, which holds a team *code* in
`localStorage` and must not import from `queries/`; `actingTeam` is a computed re-match
against the team list. Every non-2xx throws `ApiError` carrying `status`, `detail` and
DRF `fieldErrors` — branch on `status`, and keep Persian user-facing copy in
`useActing.ts`, not in the transport. `http.ts` fetches the CSRF token lazily before the
first unsafe method, so nothing else should call `ensureCsrf()`.

**Build UI from the shadcn-vue components in `src/components/ui/`** (Reka UI + Tailwind +
`cva`) rather than hand-rolling markup or bespoke scoped CSS. Available today: badge,
button, card, dialog, input, label, sheet, skeleton, sonner, textarea. Import via the
`@/components/ui/...` alias. Need one that is missing? Add it with
`npx shadcn-vue@latest add <name>` — do not write it by hand; the CLI wires variants and
Reka primitives that hand-written copies get wrong. `src/style.css` imports Tailwind v4
and the shadcn token theme; `components.json` has `"rtl": true`.
