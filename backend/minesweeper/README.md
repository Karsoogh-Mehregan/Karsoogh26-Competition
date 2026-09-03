# Minesweeper

Django app that owns competition Minesweeper: the `MinesweeperGame` model, gameplay services, REST API, and public-board sanitization.

It is **not** a standalone project. It lives inside Karsoogh 26 (`INSTALLED_APPS` → `minesweeper`), uses the existing session-auth / `Team` identity, stores an association to a map `Node`, and follows the contest clock via `GameIsRunning`.

Gameplay is server-authoritative. The Vue client talks only to this API and must render the sanitized response; it must not place mines, flood-fill, score, or infer hidden mines.

---

## Architecture

```text
HTTP request
    ↓
views + serializers     auth, ownership, validation, HTTP mapping
    ↓
minesweeper.services    create / claim / reveal / flag, win-loss, scoring
    ↓
MinesweeperGame         persistent state + DB constraints
    ↓
database
```

| Layer | Responsibility |
| ----- | -------------- |
| `serializers.py` | Request validation (`node`, `difficulty`, `row`/`col`) and the **public** game JSON. Builds the client board from scratch; does not strip fields after dumping the stored JSON. |
| `views.py` | Session auth, team membership, contest-running gate, ownership lookup, calls into services, maps domain exceptions to HTTP. No gameplay. |
| `services.py` | All mutations. HTTP-unaware. Raises `minesweeper.exceptions` (or `MinesweeperGame.DoesNotExist`). |
| `models.py` | Stored board (including hidden mines), layout/status constraints, nullable `Team` FK, `Node` FK. |

`game.api_exceptions.Conflict` (409) and `Unprocessable` (422) are reused. OpenAPI uses `core.openapi.extend_schema`.

---

## Game model

`MinesweeperGame` (`related_name="minesweeper_games"` on both `Team` and `Node`). Default ordering: `-started_at`.

The game belongs to a map `Node` through a required foreign key. That only **identifies which node the instance is associated with**. Minesweeper does not check who occupies the node, does not capture it, and does not change `Occupancy` or any other map/economy state when a game is won or lost.

| Field | Type | Purpose |
| ----- | ---- | ------- |
| `id` | `BigAutoField` | Primary key; this is the `game_id` in URLs. |
| `team` | FK → `teams.Team`, **`PROTECT`**, **nullable** | Claimed team, or `NULL` until the first join. Deleting a team must not silently drop game records. |
| `node` | FK → `game.Node`, **`PROTECT`** | Associated map node. Historical: deleting a node must not drop games. Not an ownership record. |
| `difficulty` | `easy` / `medium` / `hard` | Layout key. Width/height/mine count are **not** caller-chosen. |
| `width`, `height`, `mine_count` | positive small ints | Copied from `DIFFICULTY_LAYOUTS` at create; constrained to match `difficulty`. |
| `board` | JSON | Full server-side grid. Default `{"cells": []}` until `create_game` fills it. |
| `status` | `in_progress` / `won` / `lost` | Default `in_progress`. |
| `score` | `PositiveIntegerField`, default `0` | Written on finish. Not `Team.balance`. |
| `started_at` | `auto_now_add` | Scoring clock. Also used for default ordering. |
| `finished_at` | nullable datetime | Set only when the game is won or lost. |
| `created_at` | `auto_now_add` | Audit timestamp. |

**Constraints**

- `minesweepergame_layout_matches_difficulty` — `(width, height, mine_count)` must equal `DIFFICULTY_LAYOUTS[difficulty]`.
- `minesweepergame_finished_at_matches_status` — `in_progress` ⇔ `finished_at` is null; `won`/`lost` ⇔ `finished_at` is set.

**Index:** `(team, status)` as `msweeper_team_status_idx`.

There is **no** uniqueness constraint of one in-progress game per team. `create_game` always inserts a new unclaimed row.

Django admin is the intended create path. Staff pick a node and difficulty (team may stay empty). `started_at` / `finished_at` / `created_at` are read-only; the stored board (including mines) is visible to staff. On add, admin calls `create_game` so the board is generated rather than saving an empty grid.

---

## Difficulty levels

Single source of truth: `DIFFICULTY_LAYOUTS` and `DIFFICULTY_BASE_SCORES` in `models.py`.

| Difficulty | Grid | Mines | Base score |
| ---------- | ---- | ----: | ---------: |
| `easy` | 9 × 9 | 10 | 100 |
| `medium` | 16 × 16 | 40 | 250 |
| `hard` | 30 × 16 | 99 | 500 |

`create_game` looks up the layout by key. Unknown keys raise `InvalidDifficulty`. It does not take a team.

---

## Board representation

Stored JSON (server-only until the public serializer copies a subset):

```json
{
  "cells": [
    [
      {
        "mine": false,
        "revealed": false,
        "flagged": false,
        "adjacent_mines": 0
      }
    ]
  ]
}
```

- `cells[row][col]`: row 0 is the top, col 0 is the left.
- Height rows, each of width cells.
- `mine` is the real mine map.
- `adjacent_mines` is the count of mines in the 8 neighbors (in-bounds only).
- Default / empty board: `{"cells": []}`. Services populate a full grid on create.

Mine placement: `random.sample` over all cells (`_generate_board`).

---

## Public board representation

The stored board and the API board are **intentionally different**. `PublicGameSerializer.get_board` → `public_board` → `_public_cell`.

### `status === "in_progress"`

Unrevealed cell (no `mine`, no `adjacent_mines`):

```json
{ "revealed": false, "flagged": false }
```

Revealed cell (still no `mine`):

```json
{ "revealed": true, "flagged": false, "adjacent_mines": 2 }
```

Clients must not infer hidden mines. Two unrevealed cells are indistinguishable in the JSON.

### `status === "won"` or `"lost"`

Every cell includes `revealed`, `flagged`, `adjacent_mines`, and `mine`, so the UI can show the final map. Unrevealed mines stay `revealed: false` in storage; they still get `"mine": true` on the wire once the game is finished.

---

## Game rules

Implemented only in `services.py`.

### Reveal

`reveal_cell(game_id, row, col)`:

1. Lock the row (`select_for_update` inside `transaction.atomic`).
2. Reject finished games (`GameFinished`).
3. Reject out-of-bounds (`InvalidCell`).
4. Reject already revealed (`CellAlreadyRevealed`) and flagged (`CellFlagged`).
5. Deep-copy the board, reveal the cell (and flood-fill if it is a zero).
6. If the clicked cell was a mine → **loss**.
7. Else if every non-mine cell is revealed → **win**.
8. Else save the board; status stays `in_progress`, score stays `0`.

Missing `game_id` raises `MinesweeperGame.DoesNotExist` (views map to 404).

### Flood-fill

Iterative BFS (`collections.deque`) from a revealed cell with `adjacent_mines == 0`:

- 8-neighbor walk.
- Does not open mines.
- Does not open flagged cells.
- Numbered safe cells (`adjacent_mines > 0`) are revealed as the boundary and are **not** enqueued.
- A mine click still sets that cell `revealed: true` and then finishes as a loss; neighbors are not flood-opened.

### Flag / unflag

`toggle_flag(game_id, row, col)`:

- Same lock and finished/bounds checks.
- Unrevealed unflagged → flagged; flagged → unflagged.
- Revealed cells raise `CannotFlagRevealed`.
- Does not reveal, does not score, does not win.
- **No flag cap.** Extra flags are allowed.
- Flags are **not** part of the win condition.

### Win

Every cell with `mine == false` is `revealed`. Flags on mines are irrelevant.

### Loss

Revealing a mine: `status=lost`, `score=0`, `finished_at` set. The clicked mine is revealed; other mines remain unrevealed in storage (but are exposed in the public board because the game is finished).

### Scoring

Written only in `_finish`. In-progress score is always `0`.

Win:

```text
elapsed_seconds = max(0, floor((finished_at - started_at).total_seconds()))
score = base + max(0, base - elapsed_seconds)
```

`base` is `DIFFICULTY_BASE_SCORES[difficulty]`. Clock is `services._now()` (wraps `timezone.now()`; tests monkeypatch it).

| Outcome | Score |
| ------- | ----- |
| Win, instant | `2 * base` |
| Win, slow (`elapsed >= base`) | `base` (bonus floors at 0) |
| Loss | `0` |

The frontend must display `game.score` from the API. It must not recompute it.

This app does **not** credit `Team.balance`.

---

## Game lifecycle

Games are prepared in Django admin (or the staff-only create API) **without a team**. The first player who opens the SPA URL claims the row.

```text
create_game(node, difficulty)
    → team=NULL, status=in_progress, score=0, finished_at=null, started_at stamped; node stored
assign_game_to_team(game_id, team)
    → first join sets team; same team is a no-op; another team → GameAlreadyClaimed
reveal / flag
    → still in_progress, or won / lost
won | lost
    → finished_at set, score written; further reveal/flag → GameFinished
    → node row is unchanged
```

`team is NULL` means the game has not been claimed. Status stays `in_progress` until win/loss — there is no separate waiting status.

Mutating player endpoints (`join`, `reveal`, `flag`) require `GameSettings.is_running` (`status == running`). **GET of an owned game remains allowed** when the contest is not running. Staff create is **not** gated on the contest clock.

There is no delete/archive API. The SPA does not create games.

Staff workflow:

1. Admin → Minesweeper games → add. Node + difficulty; leave Team empty.
2. Give the team `http://localhost:3000/minesweeper/game/<id>/`.
3. First authenticated player visit POSTs join and claims the game.

---

## API

Mounted from `core/api_urls.py` as `path("minesweeper/", include("minesweeper.urls"))`.

`app_name = "minesweeper"`.

| Method | Path | Name | Permissions |
| ------ | ---- | ---- | ----------- |
| `POST` | `/api/minesweeper/games/` | `game-create` | `IsAuthenticated`, `IsAdminUser` (staff; SPA must not call this) |
| `POST` | `/api/minesweeper/games/<pk>/join/` | `game-join` | `IsAuthenticated`, `IsTeamMember`, `GameIsRunning` |
| `GET` | `/api/minesweeper/games/<pk>/` | `game-detail` | `IsAuthenticated`, `IsTeamMember` |
| `POST` | `/api/minesweeper/games/<pk>/reveal/` | `game-reveal` | `IsAuthenticated`, `IsTeamMember`, `GameIsRunning` |
| `POST` | `/api/minesweeper/games/<pk>/flag/` | `game-flag` | `IsAuthenticated`, `IsTeamMember`, `GameIsRunning` |

Session cookies + CSRF (`X-CSRFToken`). Same as the rest of the API: `GET /api/auth/csrf/` first, then login. With `DEBUG`, schema is at `/api/schema/` and Swagger at `/api/docs/`. OpenAPI examples use the sanitized in-progress shape (no hidden mines).

### Authentication and ownership

- Auth: Django session (`SessionAuthentication`). No JWT.
- Team: **`request.user.team` only**, assigned at join. The join body is empty.
- Node: create (staff) accepts a node **id** and checks that the row exists. There is **no** occupancy/ownership check on that node.
- Players: `IsTeamMember` requires `request.user.team_id`.
- Mentors typically have `team=None`. They cannot join or play. The SPA “acting team” (`localStorage`) is not sent and is not trusted.
- Staff: `IsAdminUser` may create unclaimed games. Django admin is the intended UI.
- Anonymous users: **403** (project convention for unauthenticated API calls).
- Users without a team: **403** on join/play.
- Other team’s `pk`, or a missing `pk`, on GET/reveal/flag: **404** with the same body (`{"detail": "بازی پیدا نشد."}`). Existence is not leaked on those routes.
- Join of a game already claimed by another team: **409** (the URL was shared; first claim wins).
- Unclaimed GET: **404** until the caller has joined.

### Create game (staff)

```http
POST /api/minesweeper/games/
```

```json
{ "node": 25, "difficulty": "easy" }
```

`201` + public game with `team` still null. The SPA does **not** call this. `difficulty` must be one of the `MinesweeperDifficulty` choices. `node` must be the primary key of an existing `game.Node`. Missing or unknown node → **400** field error. The service does not verify occupancy.

### Join game

```http
POST /api/minesweeper/games/<pk>/join/
```

Empty JSON body. `200` + public game. First visitor with a team claims the row (`assign_game_to_team`). The same team may join again. Another team gets **409**.

### Get game

```http
GET /api/minesweeper/games/<pk>/
```

`200` + public game. No request body.

### Reveal cell / toggle flag

```http
POST /api/minesweeper/games/<pk>/reveal/
POST /api/minesweeper/games/<pk>/flag/
```

```json
{ "row": 3, "col": 5 }
```

`200` + public game after the service returns. Reveal of a mine is a **successful** `200` with `status: "lost"`, not an error.

Coordinates are integers; out-of-bounds is a domain `422`, not serializer validation (the serializer does not check board size).

### API responses

Public game fields: `id`, `node`, `difficulty`, `width`, `height`, `mine_count`, `status`, `score`, `started_at`, `finished_at`, `board`. **No `team`.** `node` is the integer id only — not code, name, or occupancy.

In-progress example (truncated board):

```json
{
  "id": 1,
  "node": 25,
  "difficulty": "easy",
  "width": 9,
  "height": 9,
  "mine_count": 10,
  "status": "in_progress",
  "score": 0,
  "started_at": "2026-09-02T10:00:00Z",
  "finished_at": null,
  "board": {
    "cells": [
      [
        { "revealed": false, "flagged": false },
        { "revealed": true, "flagged": false, "adjacent_mines": 1 }
      ]
    ]
  }
}
```

### Error handling

Domain exceptions stay in `minesweeper.exceptions`. Views map them in `_map_service_error`.

| Condition | HTTP | `detail` / body |
| --------- | ---: | --------------- |
| Invalid JSON / unknown `difficulty` / missing or unknown `node` (serializer) | 400 | DRF field errors, e.g. `{"difficulty": ["..."]}` or `{"node": ["..."]}` |
| Missing or other-team game | 404 | `بازی پیدا نشد.` |
| Contest not running (join / reveal / flag) | 403 | `The game is not running.` (`GameIsRunning.message`) |
| Anonymous / no team / mentor / non-staff create | 403 | DRF permission denied (not a Minesweeper domain exception) |
| Finished game (`GameFinished`) | 409 | `این بازی تمام شده است.` |
| Already claimed by another team (`GameAlreadyClaimed`) | 409 | `این بازی قبلاً گرفته شده است.` |
| Already revealed (`CellAlreadyRevealed`) | 409 | `این خانه قبلاً باز شده است.` |
| Reveal flagged cell (`CellFlagged`) | 409 | `خانهٔ پرچم‌دار را نمی‌توان باز کرد.` |
| Flag revealed cell (`CannotFlagRevealed`) | 409 | `خانهٔ بازشده را نمی‌توان پرچم زد.` |
| Out of bounds (`InvalidCell`) | 422 | `این خانه روی صفحه نیست.` |
| `InvalidDifficulty` from the service | 422 | `سطح بازی نامعتبر است.` (create normally fails earlier with 400) |

Unknown `MinesweeperServiceError` subclasses would become 422 with `str(exc)`.

---

## Security and data sanitization

- Hidden `mine` / `adjacent_mines` never appear on in-progress unrevealed cells.
- In-progress revealed cells still omit `mine`.
- Sanitization is constructive (`_public_cell`), not a post-hoc key deletion on the stored dict.
- Ownership is `filter(pk=…, team_id=…)`. Other teams get the same 404 as a missing id.
- Do not log or return the stored board from error handlers.

Admin and the database **do** contain the real mine map. Treat staff access accordingly.

---

## Running locally

Assume the repo is already set up (see the root `README.md`: `uv sync`, `.env`, migrate).

### Backend

```bash
cd backend
uv run manage.py runserver
```

API: `http://127.0.0.1:8000`. Admin: `/admin/`.

### Frontend

```bash
cd frontend
npm run dev
```

App: `http://localhost:3000`. Vite proxies `/api` to `:8000`.

### Minesweeper UI

Log in as a **player** (user with `User.team`). There is no nav button. Open a prepared game by id:

```text
http://localhost:3000/minesweeper/game/1/
```

Route `meta.requiresPlayer` redirects anyone without a team to the map. The page joins (`POST .../join/`) then renders the board. The frontend does not create games.

### Start / stop the contest

Mutating Minesweeper endpoints require `GameSettings.status == running` (`is_running`). There is no dedicated management command.

**Preferred:** Django admin → **Game settings** → set **Status** to running (`running` / «در حال اجرا»). `started_at` is read-only in admin; `GameSettings.save()` stamps it the first time status becomes running — do not set `started_at` yourself if you only want the contest clock.

**CLI** (same model path; `save(update_fields=["status"])` still stamps `started_at` when it is null):

```bash
cd backend
uv run manage.py shell -c "from game.models import GameSettings, GameStatus; s=GameSettings.load(); s.status=GameStatus.RUNNING; s.save(update_fields=['status']); print('status =', s.status); print('is_running =', s.is_running); print('started_at =', s.started_at)"
```

To pause or end the contest, set `status` to `paused` or `finished` (admin or shell). `is_running` is false unless status is exactly `running`. GET of an owned Minesweeper game still works.

You also need a team login (`create_team_users` in the root docs, or a user with `team` set in admin).

---

## Testing

From `backend/`:

```bash
uv run pytest tests/test_minesweeper_models.py -q
uv run pytest tests/test_minesweeper_services.py -q
uv run pytest tests/test_minesweeper_api.py -q
uv run pytest -q
```

| File | What it covers |
| ---- | -------------- |
| `tests/test_minesweeper_models.py` | Layout/status constraints, nullable team, `PROTECT` on team delete, defaults. |
| `tests/test_minesweeper_services.py` | Create without team, claim, reveal, flood-fill, flags, win/loss, scoring. Three classes are `@pytest.mark.postgres_only`. |
| `tests/test_minesweeper_api.py` | Auth, join/claim, ownership/404, sanitization, contest clock, HTTP mapping. |

CI-style checks (same as the rest of the backend):

```bash
uv run ruff check .
uv run ruff format --check .
uv run manage.py check
uv run manage.py makemigrations --check --dry-run
```

`postgres_only` tests are **skipped** on SQLite (`conftest.py`): `select_for_update()` is ignored there, so a pass would be a false pass. Run them against PostgreSQL (`DATABASE_URL` + `docker compose up -d db`).

---

## Concurrency and transactions

`create_game`, `assign_game_to_team`, `reveal_cell`, and `toggle_flag` are `@transaction.atomic`. Claim, reveal, and flag load the row with `select_for_update()` before read-modify-write so two simultaneous joins cannot both win, and two clicks cannot last-write-wins the board.

That lock is real on PostgreSQL. SQLite does not apply it; do not treat SQLite pytest as coverage of concurrent claims/reveals/flags.

`create_game` does not lock an existing row; it only inserts.

---

## Frontend integration

Briefly, the SPA is a client of this API:

```text
MinesweeperPage.vue  (/minesweeper/game/:id/ — join on enter, then board)
    ↓
useMinesweeper(gameId)
    ↓
queries/minesweeper.ts   (GET query after join; join/reveal/flag mutations)
    ↓
services/minesweeper.ts  (http.ts only)
    ↓
this REST API
```

The SPA **does not** call `POST /api/minesweeper/games/`. Mutations `setQueryData` with the response board; they do not refetch. There is no Minesweeper SSE. Two browsers on the same team login sharing one id see separate fetches; the same id is not live-synced.

Relevant paths: `frontend/src/services/minesweeper.ts`, `queries/minesweeper.ts`, `composables/useMinesweeper.ts`, `pages/MinesweeperPage.vue`, `components/minesweeper/`.

---

## Design decisions

- **`Team` is nullable `PROTECT`.** Unclaimed games have `team=NULL`. After join, deleting a team must not drop history.
- **`node` is association only.** Create stores the provided Node. Win/loss do not modify `Node`, occupancy, or `Team.balance`.
- **`DIFFICULTY_LAYOUTS` is the only layout table.** Width/height/mines are not request fields; a DB check constraint backs that up.
- **`random.sample` for mines.** Adjacency is computed once at create.
- **Iterative BFS** for zeros, not recursion, so large opens cannot blow the stack.
- **Services do not import DRF.** Views own Persian HTTP `detail` strings (except `GameIsRunning`, which is the shared English permission message).
- **No one-active-game DB constraint.** History is append-only; admin creates another row to prepare another puzzle.
- **Score lives on `MinesweeperGame`.** This phase does not pay `Team.balance` or touch the leaderboard.
- **Public board is a new dict.** Hidden mines cannot leak via leftover serializer fields.
- **404 for foreign GET/reveal/flag.** Same body as missing, so clients cannot probe ids. Join of a claimed game is 409.
- **Frontend does not create games.** Entry is `/minesweeper/game/<id>/`.

---

## Current scope and limitations

- No WebSocket/SSE for Minesweeper; no live sync across tabs.
- Multiple in-progress games per team are allowed.
- No list/delete/resume-last-game endpoints. Teams enter by URL id.
- The SPA does not create games and has no Minesweeper nav button.
- Winning or losing does not capture the node or change occupancy.
- Join/reveal/flag follow the contest clock; GET and staff create do not.
- `GameIsRunning` returns English `"The game is not running."` (shared permission). Other Minesweeper API errors are Persian.
- No flag limit; no chord/middle-click API.
- Score is not paid into the team economy.
- Admin can see unsanitized boards.
- This phase does not add node-ownership or access-control rules beyond first-claim-wins.
