# Minesweeper

Django app that owns competition Minesweeper: per-node `MinesweeperSettings`, generated `MinesweeperGame` boards, per-team `MinesweeperAttempt` results, gameplay services, REST API, and public-board sanitization.

It is **not** a standalone project. It lives inside Karsoogh 26 (`INSTALLED_APPS` → `minesweeper`), uses the existing session-auth / `Team` identity, stores an association to a map `Node`, and follows the contest clock via `GameIsRunning`.

Gameplay is server-authoritative. The Vue client talks only to this API and must render the sanitized response; it must not place mines, flood-fill, score, or infer hidden mines.

---

## Architecture

```text
Node
 └── MinesweeperSettings     configuration only (difficulty, enabled)
          │
          │  each entry generates a new board
          ▼
     MinesweeperGame         one random runtime layout
          │
          ▼
     MinesweeperAttempt      that team's progress and result
```

Example: Node #10 has settings `difficulty=hard`.

```text
Team A enters  →  Game #1 (board A)  →  Attempt Team A
Team B enters  →  Game #2 (board B)  →  Attempt Team B
```

These games are completely independent. A single Node can generate unlimited games over time. Two teams entering the same Node do **not** share a board.

```text
HTTP request
    ↓
views + serializers     auth, attempt ownership, validation, HTTP mapping
    ↓
minesweeper.services    start from node / reveal / flag
    ↓
MinesweeperSettings     Node configuration
MinesweeperGame         generated mine layout
MinesweeperAttempt      one team's play (progress, status, score)
    ↓
database
```

| Layer | Responsibility |
| ----- | -------------- |
| `serializers.py` | Request validation and the **public** attempt JSON. Merges layout + progress into a client board; does not dump stored JSON. |
| `views.py` | Session auth, team membership, contest-running gate, attempt ownership, calls into services. No gameplay. |
| `services.py` | All mutations. HTTP-unaware. Raises `minesweeper.exceptions` (or `DoesNotExist`). |
| `models.py` | Settings, game layout, attempt progress, constraints, indexes. |

`game.api_exceptions.Conflict` (409) and `Unprocessable` (422) are reused. OpenAPI uses `core.openapi.extend_schema`.

This app does **not** check node occupancy, capture the node, or change `Team.balance` / the leaderboard.

---

## MinesweeperSettings

Per-node configuration. `related_name="minesweeper_settings"` on `Node` (`OneToOne`). Does **not** store a board, team, status, or score.

| Field | Type | Purpose |
| ----- | ---- | ------- |
| `node` | OneToOne → `game.Node`, **`CASCADE`** | Which map node this config belongs to. |
| `enabled` | bool, default `True` | Start is rejected when false. |
| `difficulty` | `easy` / `medium` / `hard` | Layout used when generating a game. |
| `created_at` / `updated_at` | timestamps | Audit. |

Django admin is the intended configuration path: pick a node, pick a difficulty, enable or disable.

---

## MinesweeperGame

One generated board, created when a team starts play. `related_name="minesweeper_games"` on `Node`. Default ordering: `-created_at`.

| Field | Type | Purpose |
| ----- | ---- | ------- |
| `id` | `BigAutoField` | Primary key (`game_id` in the public JSON). |
| `node` | FK → `game.Node`, **`PROTECT`** | Associated map node. Not an ownership record. |
| `difficulty` | `easy` / `medium` / `hard` | Copied from settings at create. |
| `width`, `height`, `mine_count` | positive small ints | Copied from `DIFFICULTY_LAYOUTS` at create. |
| `board` | JSON | **Mine layout only** (`mine`, `adjacent_mines`). Never sent to teams while an attempt is in progress. |
| `created_at` | `auto_now_add` | Audit timestamp. |

**Constraint:** `minesweepergame_layout_matches_difficulty`.

There is **no** team, status, score, or `finished_at` on the game. Each start generates a **new** random mine placement. The game row is **immutable during gameplay**. Reveal/flag/win/loss write the attempt only.

---

## MinesweeperAttempt

One team's execution of a generated game. `related_name="attempts"` on the game, `related_name="minesweeper_attempts"` on `Team`. Default ordering: `-started_at`.

| Field | Type | Purpose |
| ----- | ---- | ------- |
| `id` | `BigAutoField` | Attempt id (`attempt_id` in the public JSON and in gameplay URLs). |
| `game` | FK → `MinesweeperGame`, **`CASCADE`** | Which generated board this play uses. |
| `team` | FK → `teams.Team`, **`PROTECT`** | Who is playing. |
| `status` | `in_progress` / `won` / `lost` | Default `in_progress`. |
| `board` | JSON | **Progress only** (`revealed`, `flagged`). |
| `score` | `PositiveIntegerField`, default `0` | Written on finish. Not `Team.balance`. |
| `started_at` | `auto_now_add` | Scoring clock. |
| `finished_at` | nullable datetime | Set only when won or lost. |
| `created_at` | `auto_now_add` | Audit timestamp. |

**Constraint:** `minesweeperattempt_finished_at_matches_status` — `in_progress` ⇔ `finished_at` is null.

**Indexes:** `(team, status)` as `msweeper_att_team_status_idx`, `(game, team)` as `msweeper_att_game_team_idx`.

Mine layout comes from `attempt.game.board`. Revealed/flagged state comes from `attempt.board`. Progress of one attempt never affects another.

---

## Difficulty levels

Single source of truth: `DIFFICULTY_LAYOUTS` and `DIFFICULTY_BASE_SCORES` in `models.py`.

| Difficulty | Grid | Mines | Base score |
| ---------- | ---- | ----: | ---------: |
| `easy` | 9 × 9 | 10 | 100 |
| `medium` | 16 × 16 | 40 | 250 |
| `hard` | 30 × 16 | 99 | 500 |

`create_game` looks up the layout by key. Unknown keys raise `InvalidDifficulty`. The SPA never sends difficulty; it comes from `MinesweeperSettings`.

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

Mine placement: `random.sample` over all cells (`_generate_layout`) once per `create_game` / `create_game_from_node`. Attempts copy dimensions into an all-hidden progress board; they do **not** regenerate mines.

---

## Public board representation

`PublicGameSerializer.get_board` merges layout + progress through `_public_cell`. Hidden mines stay off the wire until the **attempt** is finished.

### `status === "in_progress"`

Unrevealed: `{ "revealed": false, "flagged": false }`

Revealed: `{ "revealed": true, "flagged": false, "adjacent_mines": 2 }` (still no `mine`)

### `status === "won"` or `"lost"`

Every cell includes `revealed`, `flagged`, `adjacent_mines`, and `mine`.

Public fields: `game_id`, `attempt_id`, `node`, `difficulty`, `width`, `height`, `mine_count`, `status`, `score`, `started_at`, `finished_at`, `board`. **No `team`.**

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

Mines are read from `attempt.game.board`. Flags and reveals are stored on `attempt.board`. Score is written on the attempt: `base + max(0, base - floor(elapsed))`. Loss scores `0`. Clock is `services._now()`.

---

## Game lifecycle

Admin configures:

```text
MinesweeperSettings(node=10, difficulty=hard, enabled=True)
```

Team A opens `/minesweeper/node/10/`:

```text
start_play(node 10, Team A)
    → create_game_from_node  → MinesweeperGame (random board, difficulty=hard)
    → create_attempt         → MinesweeperAttempt for Team A
reveal / flag update that attempt
```

Team B opening the same URL at the same time gets **Game B + Attempt B**, with a different random board.

Every entry creates a new game. The same team entering twice also gets two independent games and attempts.

```text
create_game_from_node(node)   → read settings; generate a new MinesweeperGame
create_attempt(game, team)    → always insert a new attempt
start_play(node, team)        → both of the above
reveal_cell / toggle_flag(attempt_id)  → attempt only
```

Start / reveal / flag require `GameSettings.is_running`. **GET of the caller's attempt remains allowed** when the contest is not running.

Django admin: configure `MinesweeperSettings` (node, difficulty, enabled). Generated games and attempts are listed read-only.

---

## API

Mounted from `core/api_urls.py` as `path("minesweeper/", include("minesweeper.urls"))`.

| Method | Path | Name | Permissions |
| ------ | ---- | ---- | ----------- |
| `POST` | `/api/minesweeper/nodes/<node_id>/start/` | `node-start` | `IsAuthenticated`, `IsTeamMember`, `GameIsRunning` |
| `GET` | `/api/minesweeper/attempts/<pk>/` | `attempt-detail` | `IsAuthenticated`, `IsTeamMember` |
| `POST` | `/api/minesweeper/attempts/<pk>/reveal/` | `attempt-reveal` | `IsAuthenticated`, `IsTeamMember`, `GameIsRunning` |
| `POST` | `/api/minesweeper/attempts/<pk>/flag/` | `attempt-flag` | `IsAuthenticated`, `IsTeamMember`, `GameIsRunning` |

Session cookies + CSRF. The SPA provides only the **node id** to start. Gameplay URLs use **attempt id**. Ownership is `request.user.team == attempt.team`.

### Start

```http
POST /api/minesweeper/nodes/<node_id>/start/
```

Empty JSON body. **201** + public attempt. Always creates a new `MinesweeperGame` and `MinesweeperAttempt`. The client does not send difficulty.

Missing node or missing settings: **404**. Disabled settings: **409**.

### Get / reveal / flag

Paths are `/api/minesweeper/attempts/<pk>/…`. GET without that attempt, or an attempt owned by another team, is **404** (same body as a missing id). Reveal/flag operate on the in-progress attempt; a finished attempt is **409**.

### Error handling

| Condition | HTTP | `detail` / body |
| --------- | ---: | --------------- |
| Missing node / missing settings / missing or foreign attempt | 404 | `بازی پیدا نشد.` |
| Contest not running (start / reveal / flag) | 403 | `The game is not running.` |
| Anonymous / no team / mentor | 403 | DRF permission denied |
| Settings disabled (`SettingsDisabled`) | 409 | `این بازی مین‌روب فعال نیست.` |
| Finished attempt (`GameFinished`) | 409 | `این بازی تمام شده است.` |
| Already revealed / flagged / flag-on-revealed | 409 | existing Persian messages |
| Out of bounds (`InvalidCell`) | 422 | `این خانه روی صفحه نیست.` |

---

## Security and data sanitization

- Layout `mine` / `adjacent_mines` never appear on in-progress unrevealed cells.
- Sanitization is constructive (`_public_cell`), merging two JSON blobs.
- Attempt lookup loads the row, then requires `attempt.team_id == request.user.team_id`. Other teams get the same 404 as a missing id.
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

In Django admin, add `MinesweeperSettings` for a node (difficulty + enabled). Log in as a **player**. There is no nav button. Open that node:

```text
http://localhost:3000/minesweeper/node/<node_id>/
```

The page calls start, stores `attempt_id`, and renders the existing board UI. There is no difficulty picker and no start button. The frontend does not create games directly.

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
| `tests/test_minesweeper_models.py` | Settings OneToOne; game has no team/status/score; attempt FKs; layout/status constraints; `PROTECT` / `CASCADE`. |
| `tests/test_minesweeper_services.py` | Settings-driven create; each entry a new game; independent boards; reveal/flag/win/loss/scoring. `postgres_only` for row locks. |
| `tests/test_minesweeper_api.py` | Start endpoint, attempt ownership, sanitization, contest clock, HTTP mapping. |

```bash
uv run ruff check .
uv run ruff format --check .
uv run manage.py check
uv run manage.py makemigrations --check --dry-run
```

`postgres_only` tests are skipped on SQLite (`conftest.py`).

---

## Concurrency and transactions

`create_game`, `create_game_from_node`, `create_attempt`, `start_play`, `reveal_cell`, and `toggle_flag` are `@transaction.atomic`.

Reveal/flag lock the **attempt** row. Two teams starting the same node concurrently each get their own game and attempt.

---

## Frontend integration

```text
MinesweeperPage.vue  (/minesweeper/node/:id/ — start on enter, then board)
    ↓
useMinesweeper(nodeId)   stores attempt_id from the start response
    ↓
queries/minesweeper.ts
    ↓
services/minesweeper.ts
    ↓
POST /nodes/<node_id>/start/
GET/POST /attempts/<attempt_id>/…
```

The SPA does **not** send difficulty and does not create games by id.

---

## Design decisions

- **Settings vs game vs attempt.** Configuration lives on the node. Each entry generates a new board. Progress and score belong to the attempt.
- **No shared board.** Two teams on the same node get two random layouts.
- **Every entry creates a new game.** The same team entering twice gets two independent plays.
- **`node` is association only.** Win/loss do not modify `Node`, occupancy, or `Team.balance`.
- **404 for foreign GET/reveal/flag.** Same body as missing.
- **Frontend does not create games.** Entry is `/minesweeper/node/<node_id>/`.

---

## Current scope and limitations

- No WebSocket/SSE; no live sync across tabs.
- Refreshing `/minesweeper/node/<id>/` starts a **new** game.
- No list/delete endpoints. Teams enter by node URL.
- Winning does not capture the node.
- Start/reveal/flag follow the contest clock; GET does not.
- No flag limit; no chord/middle-click API.
- Score is not paid into the team economy.
- Admin can see unsanitized layouts and attempt boards.
