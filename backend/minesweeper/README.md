# Minesweeper

Django app that owns competition Minesweeper: the reusable `MinesweeperGame` definition, per-team `MinesweeperAttempt` rows, gameplay services, REST API, and public-board sanitization.

It is **not** a standalone project. It lives inside Karsoogh 26 (`INSTALLED_APPS` → `minesweeper`), uses the existing session-auth / `Team` identity, stores an association to a map `Node`, and follows the contest clock via `GameIsRunning`.

Gameplay is server-authoritative. The Vue client talks only to this API and must render the sanitized response; it must not place mines, flood-fill, score, or infer hidden mines.

---

## Architecture

```text
HTTP request
    ↓
views + serializers     auth, attempt lookup, validation, HTTP mapping
    ↓
minesweeper.services    create game / get_or_create attempt / reveal / flag
    ↓
MinesweeperGame         reusable mine layout on a Node
MinesweeperAttempt      one team's play (progress, status, score)
    ↓
database
```

| Layer | Responsibility |
| ----- | -------------- |
| `serializers.py` | Request validation and the **public** attempt JSON. Merges layout + progress into a client board; does not dump stored JSON. |
| `views.py` | Session auth, team membership, contest-running gate, resolve the caller's attempt, calls into services. No gameplay. |
| `services.py` | All mutations. HTTP-unaware. Raises `minesweeper.exceptions` (or `DoesNotExist`). |
| `models.py` | Game layout + attempt progress, constraints, indexes. |

`game.api_exceptions.Conflict` (409) and `Unprocessable` (422) are reused. OpenAPI uses `core.openapi.extend_schema`.

A `MinesweeperGame` is a **reusable definition** placed on a Node. It has **no team**. Each play session is a `MinesweeperAttempt`. Multiple teams can play the same game; each gets an isolated progress board. The mine layout is shared.

This app does **not** check node occupancy, capture the node, or change `Team.balance` / the leaderboard.

---

## MinesweeperGame

Reusable puzzle on one map node. `related_name="minesweeper_games"` on `Node`. Default ordering: `-created_at`.

| Field | Type | Purpose |
| ----- | ---- | ------- |
| `id` | `BigAutoField` | Primary key; this is the `game_id` in URLs (`/minesweeper/game/<id>/`). |
| `node` | FK → `game.Node`, **`PROTECT`** | Associated map node. Not an ownership record. |
| `difficulty` | `easy` / `medium` / `hard` | Layout key. Width/height/mine count are **not** caller-chosen. |
| `width`, `height`, `mine_count` | positive small ints | Copied from `DIFFICULTY_LAYOUTS` at create. |
| `board` | JSON | **Mine layout only** (`mine`, `adjacent_mines`). Never sent to teams while an attempt is in progress. |
| `created_at` | `auto_now_add` | Audit timestamp. |

**Constraint:** `minesweepergame_layout_matches_difficulty`.

The game row is **immutable during gameplay**. Reveal/flag/win/loss write the attempt only.

---

## MinesweeperAttempt

One team's execution of a game. `related_name="attempts"` on the game, `related_name="minesweeper_attempts"` on `Team`. Default ordering: `-started_at`.

| Field | Type | Purpose |
| ----- | ---- | ------- |
| `id` | `BigAutoField` | Attempt id (`attempt_id` in the public JSON). |
| `game` | FK → `MinesweeperGame`, **`CASCADE`** | Which layout this play uses. |
| `team` | FK → `teams.Team`, **`PROTECT`** | Who is playing. |
| `status` | `in_progress` / `won` / `lost` | Default `in_progress`. |
| `board` | JSON | **Progress only** (`revealed`, `flagged`). |
| `score` | `PositiveIntegerField`, default `0` | Written on finish. Not `Team.balance`. |
| `started_at` | `auto_now_add` | Scoring clock. |
| `finished_at` | nullable datetime | Set only when won or lost. |
| `created_at` | `auto_now_add` | Audit timestamp. |

**Constraint:** `minesweeperattempt_finished_at_matches_status` — `in_progress` ⇔ `finished_at` is null.

**Indexes:** `(team, status)` as `msweeper_att_team_status_idx`, `(game, team)` as `msweeper_att_game_team_idx`. There is **no** unique constraint; historical retries are allowed. Join reuses the current **in-progress** attempt for that team+game.

---

## Difficulty levels

Single source of truth: `DIFFICULTY_LAYOUTS` and `DIFFICULTY_BASE_SCORES` in `models.py`.

| Difficulty | Grid | Mines | Base score |
| ---------- | ---- | ----: | ---------: |
| `easy` | 9 × 9 | 10 | 100 |
| `medium` | 16 × 16 | 40 | 250 |
| `hard` | 30 × 16 | 99 | 500 |

`create_game` looks up the layout by key. Unknown keys raise `InvalidDifficulty`.

---

## Board representation

**Game layout** (server-only):

```json
{
  "cells": [
    [{ "mine": false, "adjacent_mines": 1 }]
  ]
}
```

**Attempt progress:**

```json
{
  "cells": [
    [{ "revealed": false, "flagged": false }]
  ]
}
```

Two teams on the same game share mines and adjacency. They do **not** share revealed cells or flags.

Mine placement: `random.sample` over all cells (`_generate_layout`) once at `create_game`. Attempts copy dimensions into an all-hidden progress board; they do **not** regenerate mines.

---

## Public board representation

`PublicGameSerializer.get_board` merges layout + progress through `_public_cell`. Hidden mines stay off the wire until the **attempt** is finished.

### `status === "in_progress"`

Unrevealed: `{ "revealed": false, "flagged": false }`

Revealed: `{ "revealed": true, "flagged": false, "adjacent_mines": 2 }` (still no `mine`)

### `status === "won"` or `"lost"`

Every cell includes `revealed`, `flagged`, `adjacent_mines`, and `mine`.

Public fields: `id` (game id), `attempt_id`, `node`, `difficulty`, `width`, `height`, `mine_count`, `status`, `score`, `started_at`, `finished_at`, `board`. **No `team`.**

---

## Game rules

Implemented only in `services.py`, against an **attempt**.

### Reveal

`reveal_cell(attempt_id, row, col)`:

1. Lock the attempt (`select_for_update` inside `transaction.atomic`).
2. Reject finished attempts (`GameFinished`).
3. Reject out-of-bounds (`InvalidCell`).
4. Reject already revealed / flagged on the **progress** board.
5. Deep-copy progress, reveal (and flood-fill zeros using the **layout**).
6. Mine click → **loss** on the attempt.
7. Else if every non-mine layout cell is revealed → **win** on the attempt.
8. Else save progress only. The game layout is not written.

### Flood-fill / flag / win / loss / scoring

Same rules as before, with mines read from the game and flags/reveals stored on the attempt. Score is written on the attempt: `base + max(0, base - floor(elapsed))`. Loss scores `0`. Clock is `services._now()`.

---

## Game lifecycle

Admin creates:

```text
MinesweeperGame(node=10, difficulty=medium)   # mine layout generated
```

Team A opens `/minesweeper/game/1/`:

```text
get_or_create_attempt(1, Team A)
    → in-progress attempt if one exists, else a new progress board
reveal / flag update that attempt
```

Team B opens the same URL later and gets a **different** attempt on the same game. There is no "already claimed" error.

```text
create_game(node, difficulty)          → layout only; no team
get_or_create_attempt(game_id, team)   → reuse in-progress, else insert
create_attempt(game_id, team)          → always insert
reveal_cell / toggle_flag(attempt_id)  → attempt only
```

Join / reveal / flag require `GameSettings.is_running`. **GET of the caller's attempt remains allowed** when the contest is not running. Staff create is not gated on the contest clock.

Django admin: add a game by node + difficulty (`create_game` generates the layout). Attempts are listed inline (read-only).

---

## API

Mounted from `core/api_urls.py` as `path("minesweeper/", include("minesweeper.urls"))`.

| Method | Path | Name | Permissions |
| ------ | ---- | ---- | ----------- |
| `POST` | `/api/minesweeper/games/` | `game-create` | `IsAuthenticated`, `IsAdminUser` (SPA must not call this) |
| `POST` | `/api/minesweeper/games/<pk>/join/` | `game-join` | `IsAuthenticated`, `IsTeamMember`, `GameIsRunning` |
| `GET` | `/api/minesweeper/games/<pk>/` | `game-detail` | `IsAuthenticated`, `IsTeamMember` |
| `POST` | `/api/minesweeper/games/<pk>/reveal/` | `game-reveal` | `IsAuthenticated`, `IsTeamMember`, `GameIsRunning` |
| `POST` | `/api/minesweeper/games/<pk>/flag/` | `game-flag` | `IsAuthenticated`, `IsTeamMember`, `GameIsRunning` |

Session cookies + CSRF. The URL still uses **game id**. Join/GET/reveal/flag resolve **the caller's attempt** automatically.

### Join

```http
POST /api/minesweeper/games/<pk>/join/
```

Empty JSON body. `200` + public attempt. Creates an in-progress attempt if the team has none; otherwise returns the existing one. A second team on the same game gets its own attempt.

### Get / reveal / flag

Same paths as before. GET without an attempt for that team is **404** (same body as a missing game). Reveal/flag operate on the in-progress attempt; a finished attempt is **409**.

Staff create returns a definition only (`id`, `node`, `difficulty`, `width`, `height`, `mine_count`) — no mine layout.

### Error handling

| Condition | HTTP | `detail` / body |
| --------- | ---: | --------------- |
| Invalid JSON / unknown `difficulty` / missing or unknown `node` | 400 | DRF field errors |
| Missing game, or no attempt for this team | 404 | `بازی پیدا نشد.` |
| Contest not running (join / reveal / flag) | 403 | `The game is not running.` |
| Anonymous / no team / mentor / non-staff create | 403 | DRF permission denied |
| Finished attempt (`GameFinished`) | 409 | `این بازی تمام شده است.` |
| Already revealed / flagged / flag-on-revealed | 409 | existing Persian messages |
| Out of bounds (`InvalidCell`) | 422 | `این خانه روی صفحه نیست.` |

---

## Security and data sanitization

- Layout `mine` / `adjacent_mines` never appear on in-progress unrevealed cells.
- Sanitization is constructive (`_public_cell`), merging two JSON blobs.
- Attempt lookup is `filter(game_id=…, team_id=…)`. Other teams get the same 404 as a missing id on GET/reveal/flag.
- Admin and the database **do** contain the real mine map.

---

## Running locally

Assume the repo is already set up (see the root `README.md`: `uv sync`, `.env`, migrate).

```bash
cd backend
uv run manage.py runserver
```

```bash
cd frontend
npm run dev
```

Log in as a **player**. There is no nav button. Open a prepared game:

```text
http://localhost:3000/minesweeper/game/1/
```

The page joins, stores `attempt_id` internally, and renders the existing board UI. The frontend does not create games.

Mutating endpoints require `GameSettings.status == running`. Set that in admin (Game settings) or:

```bash
cd backend
uv run manage.py shell -c "from game.models import GameSettings, GameStatus; s=GameSettings.load(); s.status=GameStatus.RUNNING; s.save(update_fields=['status'])"
```

---

## Testing

```bash
cd backend
uv run pytest tests/test_minesweeper_models.py -q
uv run pytest tests/test_minesweeper_services.py -q
uv run pytest tests/test_minesweeper_api.py -q
uv run pytest -q
```

| File | What it covers |
| ---- | -------------- |
| `tests/test_minesweeper_models.py` | Game has no team; attempt FKs; layout/status constraints; `PROTECT` / `CASCADE`. |
| `tests/test_minesweeper_services.py` | Create game, get_or_create attempt, independent boards, shared mines, reveal/flag/win/loss/scoring. `postgres_only` for row locks. |
| `tests/test_minesweeper_api.py` | Join isolation, sanitization, contest clock, HTTP mapping. |

```bash
uv run ruff check .
uv run ruff format --check .
uv run manage.py check
uv run manage.py makemigrations --check --dry-run
```

`postgres_only` tests are skipped on SQLite (`conftest.py`).

---

## Concurrency and transactions

`create_game`, `create_attempt`, `get_or_create_attempt`, `reveal_cell`, and `toggle_flag` are `@transaction.atomic`.

`get_or_create_attempt` locks the **game** row so two joins for the same team cannot insert two in-progress attempts. Reveal/flag lock the **attempt** row.

---

## Frontend integration

```text
MinesweeperPage.vue  (/minesweeper/game/:id/ — join on enter, then board)
    ↓
useMinesweeper(gameId)   stores attempt_id from the join response
    ↓
queries/minesweeper.ts
    ↓
services/minesweeper.ts
    ↓
this REST API  (still /games/<game_id>/… ; server resolves the attempt)
```

The SPA does **not** call `POST /api/minesweeper/games/`.

---

## Design decisions

- **Game vs attempt.** Layout is shared; progress and score belong to the attempt.
- **No team on `MinesweeperGame`.** Claim-the-game is gone.
- **Join reuses in-progress.** A finished attempt does not block another team.
- **`node` is association only.** Win/loss do not modify `Node`, occupancy, or `Team.balance`.
- **404 for foreign GET/reveal/flag.** Same body as missing.
- **Frontend does not create games.** Entry is `/minesweeper/game/<id>/`.

---

## Current scope and limitations

- No WebSocket/SSE; no live sync across tabs.
- Multiple historical attempts per team+game are allowed.
- No list/delete endpoints. Teams enter by URL id.
- Winning does not capture the node.
- Join/reveal/flag follow the contest clock; GET and staff create do not.
- No flag limit; no chord/middle-click API.
- Score is not paid into the team economy.
- Admin can see unsanitized layouts and attempt boards.
