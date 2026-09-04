# Minesweeper

Django app that owns competition Minesweeper: editable `DifficultyConfig` rows, per-node `MinesweeperSettings`, generated `MinesweeperGame` boards, per-team `MinesweeperAttempt` results, gameplay services, REST API, and public-board sanitization.

It is **not** a standalone project. It lives inside Karsoogh 26 (`INSTALLED_APPS` → `minesweeper`), uses the existing session-auth / `Team` identity, stores an association to a map `Node`, and follows the contest clock via `GameIsRunning`.

It also owns the **toll gates**: a board on a `toll` node is the road through it, so beating one is how a team reaches the next ring. See [Toll gates](#toll-gates).

Gameplay is server-authoritative. The Vue client talks only to this API and must render the sanitized response; it must not place mines, flood-fill, or infer hidden mines.

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
MinesweeperAttempt      one team's play (progress, status)
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

## Toll gates

`C34_*` and `C45_*` are `toll` nodes, and their map edges are one-way: `L3 → C34 → L4`, `L4 → C45 → L5`. There are no `toll`-level `Question` rows and never will be — `game.services.movement.claim_node` refuses a gate outright — so the board **is** the crossing.

| | Building | Toll gate |
| --- | --- | --- |
| Entered by | `assign-question` | Minesweeper board |
| Costs | `LevelConfig[level].entry_cost` | `LevelConfig["toll"].entry_cost`, per board |
| Creates | an `Occupancy` | nothing |
| Capacity | 1–3 seats | none; every team may cross |
| Opens neighbours | once graded | once **won** |
| Reopening | — | an owned board (open or won) reopens free |
| Recorded as | `Occupancy` row | the won `MinesweeperAttempt` |

`minesweeper/crossings.py` is the whole record: a won attempt on a toll node. `game.services.movement.expandable_node_ids` unions those node ids into the team's reach (a local import — `minesweeper` depends on `game`), which is what opens the one-way roads out of a gate. Nothing else moves: no `Occupancy`, no floor, no networth, no duel or buyout.

`services.require_playable` gates entry on **every** board, not only the gates — a guessed URL must not open one the team could not have walked to:

- the settings row must exist and be enabled;
- `require_graph_access`: the node must be an expandable holding of the team's, a neighbour of one, or a cleared gate (`NodeUnreachable` → 409).

A board the team already owns here is exempt from the reach rule and from the fee, because it is already bought. `_existing_attempt` returns it:

- **unfinished** → resumes, so the map offers «ادامه بازی» instead of quoting the toll again;
- **won** → handed back as-is, so the finished grid can be looked at and the gate is never bought twice.

Either one reopens even if the holding the team reached the gate from has since been released. The two lists ride to the SPA on the team row as `cleared_tolls` and `active_tolls`.

`services._charge_entry` takes the fee whenever a **new** board is generated. Resuming an unfinished board is free; a lost board may be replayed at full price; an unaffordable one raises `EntryFeeUnaffordable` (409) before any board exists. The debit is a `BalanceEvent` with `reason=toll` and the node code as its detail. Winning does **not** award currency: it only sets `status=WON`, which is the crossing. Losing has no extra penalty; starting a new board after a loss charges the toll again.

Starting a board on a gate publishes `board.toll.started` and any win publishes `minesweeper.cleared`; both bump the board snapshot version so `/api/teams/` stops serving a cached row that predates the payment or the crossing. Both frames are **payload-free** — a hint must not tell the hall who crossed where, and the client refetches and sees only what it is allowed to. The SPA reads both lists off the team row (`cleared_tolls`, `active_tolls`), never off `holdings`.

### Provisioning

Gates are not configured one by one:

```bash
uv run manage.py sync_toll_boards                    # fill in gates with no board
uv run manage.py sync_toll_boards --difficulty hard  # and retune every gate
```

`services.ensure_toll_boards()` is the same call `import_graph` makes after importing nodes, and `migrations/0008_seed_toll_boards` backfills databases that already hold the map. All three are idempotent and never touch a gate an organiser has tuned or disabled. Defaults are `C34 → easy`, `C45 → medium` (`DEFAULT_TOLL_DIFFICULTIES`).

---

## DifficultyConfig

Difficulties are rows, the way `game.LevelConfig` is: organisers retune a board from admin between rounds instead of waiting for a deploy.

| Field | Type | Purpose |
| ----- | ---- | ------- |
| `key` | slug, **primary key** | `easy` / `medium` / `hard` as seeded; more may be added. |
| `label` | text | Shown to players, in Persian; travels on the API as `difficulty_label`. |
| `width`, `height` | 2–40 | Grid for the next board generated at this difficulty. |
| `mine_count` | ≥ 1 and `< width * height` | Constraint-checked, so a typo cannot make an empty or unwinnable board. |
| `sort_order` | small int | Ordering in admin. |

Seeded by `migrations/0007_difficultyconfig` with exactly the numbers that used to be constants: easy 9×9/10, medium 16×16/40, hard 30×16/99.

**A board is a snapshot.** `MinesweeperGame` copies `width`, `height` and `mine_count` at creation, and the old `minesweepergame_layout_matches_difficulty` check is gone precisely so it can: retuning reshapes the *next* board, never one a team is playing. `PROTECT` on both FKs stops a difficulty in use from being deleted.

---

## MinesweeperSettings

Per-node configuration. `related_name="minesweeper_settings"` on `Node` (`OneToOne`). Does **not** store a board, team, status, or result.

| Field | Type | Purpose |
| ----- | ---- | ------- |
| `node` | OneToOne → `game.Node`, **`CASCADE`** | Which map node this config belongs to. |
| `enabled` | bool, default `True` | Enter/start are rejected when false. |
| `difficulty` | FK → `DifficultyConfig`, **`PROTECT`** | Layout used when generating a game. |
| `created_at` / `updated_at` | timestamps | Audit. |

Django admin is the intended configuration path: pick a node, pick a difficulty, enable or disable.

---

## MinesweeperGame

One generated board, created when a team starts play. `related_name="minesweeper_games"` on `Node`. Default ordering: `-created_at`.

| Field | Type | Purpose |
| ----- | ---- | ------- |
| `id` | `BigAutoField` | Primary key (`game_id` in the public JSON). |
| `node` | FK → `game.Node`, **`PROTECT`** | Associated map node. Not an ownership record. |
| `difficulty` | FK → `DifficultyConfig`, **`PROTECT`** | Copied from settings at create. |
| `width`, `height`, `mine_count` | positive small ints | Snapshot of the config at create. |
| `board` | JSON | **Mine layout only** (`mine`, `adjacent_mines`). Never sent to teams while an attempt is in progress. |
| `created_at` | `auto_now_add` | Audit timestamp. |

There is **no** team, status, or `finished_at` on the game. Each start generates a **new** random mine placement. The game row is **immutable during gameplay**. Reveal/flag/win/loss write the attempt only.

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
| `started_at` | `auto_now_add` | When the attempt began. |
| `finished_at` | nullable datetime | Set only when won or lost. |
| `created_at` | `auto_now_add` | Audit timestamp. |

**Constraint:** `minesweeperattempt_finished_at_matches_status` — `in_progress` ⇔ `finished_at` is null.

**Indexes:** `(team, status)` as `msweeper_att_team_status_idx`, `(game, team)` as `msweeper_att_game_team_idx`.

Mine layout comes from `attempt.game.board`. Revealed/flagged state comes from `attempt.board`. Progress of one attempt never affects another.

---

## Difficulty levels

Single source of truth: the `DifficultyConfig` table (above). `create_game` takes a row or its key and copies the numbers onto the board. Unknown keys raise `InvalidDifficulty`. The SPA never sends difficulty; it comes from `MinesweeperSettings`.

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

Every cell includes `revealed`, `flagged`, `adjacent_mines`, and `mine`. The SPA renders this as a read-only result board (all mines and numbers visible). Active games never include `mine`.

Public fields: `game_id`, `attempt_id`, `node`, `difficulty`, `difficulty_label`, `width`, `height`, `mine_count`, `status`, `started_at`, `finished_at`, `board`. **No `team`.** Minesweeper does not award a score.

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

### Flood-fill / flag / win / loss

Mines are read from `attempt.game.board`. Flags and reveals are stored on `attempt.board`. A win sets `status=WON` and `finished_at` and publishes `minesweeper.cleared`. A loss sets `status=LOST` and `finished_at` with no extra economy effect. Clock is `services._now()`. Minesweeper determines completion and (on a toll) accessibility; it does not award a Minesweeper score.

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

When the attempt becomes `won` or `lost`, the SPA stays on the Minesweeper page, shows the final board (mines included), and the player returns to `/` with **بازگشت به نقشه**. Leaving the page while `in_progress` does not finish the attempt; clicking the same node again issues a new entry token and resumes.

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
| Node out of the team's reach (`NodeUnreachable`) | 409 | `این خانه از مسیر فعلی تیم در دسترس نیست.` |
| Cannot pay the toll (`EntryFeeUnaffordable`) | 409 | `موجودی تیم برای ورود به این عوارضی کافی نیست.` |
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

`import_graph` has already given every toll node a board, so log in as a **player**, set the contest to running, take a spawn, work out to a node beside a `C34_*` gate, and click it. There is no Minesweeper nav button. To change what the gates play, edit `DifficultyConfig` in admin or run `manage.py sync_toll_boards --difficulty medium`.

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
| `tests/test_minesweeper_models.py` | Settings OneToOne; game has no team/status; attempt FKs; layout/status constraints; `PROTECT` / `CASCADE`. |
| `tests/test_minesweeper_services.py` | Settings-driven create; map-entry tokens; resume vs new game; independent boards; reveal/flag/win/loss. `postgres_only` for row locks. |
| `tests/test_minesweeper_api.py` | Enter/start authorization, attempt ownership, sanitization, contest clock, HTTP mapping. |
| `tests/test_toll_gates.py` | Gates: adjacency, the fee, replay after a loss, the crossing opening one-way roads, no occupancy, provisioning, retuning. |

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
won/lost → stay on the page, show the final board
    ↓
بازگشت به نقشه → router.push({ name: 'map' })  → /
```

Mines stay hidden while `in_progress`. After win/loss the sanitized response includes the full layout so the result board can be shown. The player leaves with the return button, not an automatic redirect.

The SPA does **not** send difficulty. Frontend `type === "c34"|"c45"` only chooses the click branch; the server decides whether the node is Minesweeper-enabled.

---

## Design decisions

- **Settings vs game vs attempt.** Configuration lives on the node. Progress and `status` belong to the attempt. A win is a completion (and, on a toll, a crossing), not a score.
- **No shared board.** Two teams on the same node get two random layouts.
- **One active attempt per team per node.** Returning while in progress resumes that attempt. After it finishes, a new visit creates a new game. Finished attempts are kept as history.
- **Map entry is server-authorized.** A session-bound one-time token is required to start. The Vue route is not the security mechanism.
- **`node` is association only, off the gates.** On a `toll` node the association is the game: entry is charged, reachability is checked, and a win is a crossing. Anywhere else, win and loss still move nothing.
- **The crossing is the won attempt, not an `Occupancy`.** A gate has no owner, no floor and no capacity, so an occupancy row would only be a claim the rest of the game could contradict.
- **Difficulty is data; a board is a snapshot of it.** Organisers retune between rounds and nobody loses a grid mid-game.
- **404 for foreign GET/reveal/flag.** Same body as missing.
- **Completing Minesweeper shows the result, then the player returns to the map.** `/` via `name: 'map'`, only after **بازگشت به نقشه**.

---

## Current scope and limitations

- No WebSocket/SSE; no live sync across tabs.
- Returning to the same node while an attempt is in progress resumes the existing attempt for that team. After the attempt finishes, a new visit creates a new game.
- No list/delete endpoints. Normal entry is a map click, not a typed URL.
- Winning a **toll** opens the road past it, for that team, permanently. Winning anywhere else still captures nothing.
- Start/reveal/flag follow the contest clock; GET does not.
- No flag limit; no chord/middle-click API.
- Minesweeper does not award a score or pay into the team economy. The only money movement is the toll entry fee on a new board.
- Admin can see unsanitized layouts and attempt boards.
