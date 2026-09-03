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
          │  start generates a new board unless this team already has an in-progress attempt on the node
          ▼
     MinesweeperGame         one random runtime layout
          │
          ▼
     MinesweeperAttempt      that team's progress and result
```

Example: Node `C34_0` has settings `difficulty=hard`.

```text
Team A enters  →  Game #1 (board A)  →  Attempt Team A
Team B enters  →  Game #2 (board B)  →  Attempt Team B
```

These games are completely independent. A single Node can generate unlimited games over time. Two teams entering the same Node do **not** share a board. **One active attempt per team per node:** returning while `status=in_progress` resumes that attempt. Finished attempts stay as history.

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
| `enabled` | bool, default `True` | Enter/start are rejected when false. |
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

Admin configures `MinesweeperSettings` on a map node (typically a `toll` / عوارضی node such as `C34_0`).

The graph node is the normal entry point. Vue routes are **not** authorization.

```text
GraphView click (type c34 / c45)
    → POST /api/minesweeper/nodes/<node_code>/enter/
    → session-bound, one-time, short-lived entry token
    → /minesweeper/node/<node_code>?entry=<token>
    → POST /api/minesweeper/nodes/<node_code>/start/  { "entry": token }
    → consume token, then start_play(node, team)
```

`start_play` still resumes an `in_progress` attempt for `(team, node)`, or creates a new `MinesweeperGame` + `MinesweeperAttempt`. Finished attempts stay as history. Different teams on the same node get independent games.

When the attempt becomes `won` or `lost`, the SPA navigates to `/` (the map). Leaving the page while `in_progress` does not finish the attempt; clicking the same node again issues a new entry token and resumes.

This entry token proves that this **authenticated session** requested entry for an **enabled Minesweeper node**. It does **not** prove a physical SVG click, and it does **not** check occupancy or reachability (those come later).

```text
issue_entry / consume_entry  → session authorization only
create_game_from_node(node)  → read settings; generate a new MinesweeperGame
create_attempt(game, team)   → always insert a new attempt
start_play(node, team)       → resume in-progress (team, node), else both of the above
reveal_cell / toggle_flag(attempt_id)  → attempt only
```

Enter / start / reveal / flag require `GameSettings.is_running`. **GET of the caller's attempt remains allowed** when the contest is not running.

Django admin: configure `MinesweeperSettings` (node, difficulty, enabled). Generated games and attempts are listed read-only.

---

## API

Mounted from `core/api_urls.py` as `path("minesweeper/", include("minesweeper.urls"))`.

| Method | Path | Name | Permissions |
| ------ | ---- | ---- | ----------- |
| `POST` | `/api/minesweeper/nodes/<node_code>/enter/` | `node-enter` | `IsAuthenticated`, `IsTeamMember`, `GameIsRunning` |
| `POST` | `/api/minesweeper/nodes/<node_code>/start/` | `node-start` | `IsAuthenticated`, `IsTeamMember`, `GameIsRunning` |
| `GET` | `/api/minesweeper/attempts/<pk>/` | `attempt-detail` | `IsAuthenticated`, `IsTeamMember` |
| `POST` | `/api/minesweeper/attempts/<pk>/reveal/` | `attempt-reveal` | `IsAuthenticated`, `IsTeamMember`, `GameIsRunning` |
| `POST` | `/api/minesweeper/attempts/<pk>/flag/` | `attempt-flag` | `IsAuthenticated`, `IsTeamMember`, `GameIsRunning` |

Session cookies + CSRF. Nodes are addressed by **`Node.code`** (the same ids as the graph: `C34_0`, …). Gameplay URLs use **attempt id**. Ownership is `request.user.team == attempt.team`.

### Enter

```http
POST /api/minesweeper/nodes/<node_code>/enter/
```

Empty JSON body. **200** `{ "entry": "<token>", "node": "C34_0" }`. Stores a one-time intent on the Django session (60s TTL), bound to this user and node. Missing node or missing settings: **404**. Disabled settings: **409**.

### Start

```http
POST /api/minesweeper/nodes/<node_code>/start/
```

Body `{ "entry": "<token>" }`. Consumes the session intent, then `start_play`. **201** + public attempt. Direct start without a valid unused token: **403** `اجازهٔ ورود به این بازی صادر نشده است.` (missing `entry` field is **400**). A token issued for node A cannot start node B.

Public `node` is the **code** string, not the integer PK.

### Get / reveal / flag

Paths are `/api/minesweeper/attempts/<pk>/…`. GET without that attempt, or an attempt owned by another team, is **404** (same body as a missing id). Reveal/flag operate on the in-progress attempt; a finished attempt is **409**.

### Error handling

| Condition | HTTP | `detail` / body |
| --------- | ---: | --------------- |
| Missing node / missing settings / missing or foreign attempt | 404 | `بازی پیدا نشد.` |
| Contest not running (enter / start / reveal / flag) | 403 | `The game is not running.` |
| Anonymous / no team / mentor | 403 | DRF permission denied |
| Missing / used / expired / wrong-node entry (`EntryUnauthorized`) | 403 | `اجازهٔ ورود به این بازی صادر نشده است.` |
| Settings disabled (`SettingsDisabled`) | 409 | `این بازی مین‌روب فعال نیست.` |
| Finished attempt (`GameFinished`) | 409 | `این بازی تمام شده است.` |
| Already revealed / flagged / flag-on-revealed | 409 | existing Persian messages |
| Out of bounds (`InvalidCell`) | 422 | `این خانه روی صفحه نیست.` |

---

## Security and data sanitization

- Layout `mine` / `adjacent_mines` never appear on in-progress unrevealed cells.
- Sanitization is constructive (`_public_cell`), merging two JSON blobs.
- Attempt lookup loads the row, then requires `attempt.team_id == request.user.team_id`. Other teams get the same 404 as a missing id.
- Start requires a server-issued, session-bound entry token. Opening `/minesweeper/node/<code>` without one does not start a game.
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

In Django admin, add `MinesweeperSettings` for a toll node (e.g. `C34_0`). Log in as a **player**, set the contest to running, then click that node on the map. There is no Minesweeper nav button.

Directly opening `/minesweeper/node/C34_0` without a fresh map-entry token is rejected by the start API; the SPA returns to the map.

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
| `tests/test_minesweeper_services.py` | Settings-driven create; map-entry tokens; resume vs new game; independent boards; reveal/flag/win/loss/scoring. `postgres_only` for row locks. |
| `tests/test_minesweeper_api.py` | Enter/start authorization, attempt ownership, sanitization, contest clock, HTTP mapping. |

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

`start_play` locks the **node** row (`select_for_update`), then looks for this team's `in_progress` attempt on that node. Two concurrent starts from the same team resume one attempt. Two teams starting the same node concurrently each get their own game and attempt. Reveal/flag lock the **attempt** row.

---

## Frontend integration

```text
GraphView.vue  (c34/c45 click → POST enter)
    ↓
/minesweeper/node/:id?entry=…
    ↓
MinesweeperPage.vue  consumes entry via POST start, then board
    ↓
won/lost → router.push({ name: 'map' })  → /
```

The SPA does **not** send difficulty. Frontend `type === "c34"|"c45"` only chooses the click branch; the server decides whether the node is Minesweeper-enabled.

---

## Design decisions

- **Settings vs game vs attempt.** Configuration lives on the node. Progress and score belong to the attempt.
- **No shared board.** Two teams on the same node get two random layouts.
- **One active attempt per team per node.** Returning while in progress resumes that attempt. After it finishes, a new visit creates a new game. Finished attempts are kept as history.
- **Map entry is server-authorized.** A session-bound one-time token is required to start. The Vue route is not the security mechanism.
- **`node` is association only.** Win/loss do not modify `Node`, occupancy, or `Team.balance`. Reachability/occupancy are intentionally not checked in this phase.
- **404 for foreign GET/reveal/flag.** Same body as missing.
- **Completing Minesweeper returns to the map.** `/` via `name: 'map'`.

---

## Current scope and limitations

- No WebSocket/SSE; no live sync across tabs.
- Returning to the same node while an attempt is in progress resumes the existing attempt for that team. After the attempt finishes, a new visit creates a new game.
- No list/delete endpoints. Normal entry is a map click, not a typed URL.
- Winning does not capture the node. Reachability/occupancy/ownership are out of scope here.
- Start/reveal/flag follow the contest clock; GET does not.
- No flag limit; no chord/middle-click API.
- Score is not paid into the team economy.
- Admin can see unsanitized layouts and attempt boards.
