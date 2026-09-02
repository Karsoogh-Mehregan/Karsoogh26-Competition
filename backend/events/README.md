# Events

This document describes only the competition event subsystem. The Django app lives in
`backend/events/`; its Vue pages and client data layer live under `frontend/src/`.

The app currently contains two independent events:

- **Territory Control** — a two-team, 20-turn board game.
- **Charity Bag** — a timed, shared risk/reward event using team Glorium balances.

Both events reuse the existing `teams.Team` model and session authentication. Domain mutations
belong in `events/services.py`; API views validate input and translate domain errors, but do not
implement game rules themselves.

## Structure

### Backend

- `models.py` — event state, immutable/auditable turn and participation records, and database
  constraints.
- `services.py` — authoritative game rules, transactions, row locks, dice generation, balance
  changes, and settlement.
- `serializers.py` — public API shapes and Charity Bag visibility filtering.
- `views.py` / `urls.py` — authenticated REST endpoints.
- `permissions.py` — Territory Control participant access.
- `admin.py` — staff inspection of matches, cells, turns, Charity Bag instances, and entries.
- `management/commands/` — Charity Bag scheduling and lifecycle resolution.
- `migrations/` — both event schemas.

### Frontend

- `frontend/src/pages/TerritoryEventPage.vue`
- `frontend/src/components/territory/TerritoryBoard.vue`
- `frontend/src/pages/CharityBagPage.vue`
- `frontend/src/services/events.ts` — all event API paths.
- `frontend/src/queries/events.ts` — TanStack Query polling, mutations, and cache updates.
- `frontend/src/queries/keys.ts` — event query keys.
- `frontend/src/types/api.ts` — event response and request types.
- `frontend/src/lib/gameAudio.ts` — synthesized dice, result, and coin sounds using the Web Audio
  API; there are no external sound assets.

The SPA routes are:

- `/events/territory-control`
- `/events/charity-bag`

Both routes require an authenticated session. Navigation is exposed through `InfoPanel.vue`.

## Authentication and authority

Each team signs in through its shared `accounts.User`; `User.team` identifies the authoritative
team. Client-selected team state is never accepted as permission to act.

- Team accounts may play only as their own team.
- Mentors may create Territory matches and Charity Bag instances.
- Mentors can inspect Territory matches but cannot take a team's turn.
- Mentors cannot participate in Charity Bag unless they are using a real team account.
- Dice results, legal moves, timing, balance checks, deductions, and payouts are always decided by
  the backend.

## Territory Control

### Model

`TerritoryGame` stores the two players, scores, active player, start-selection flags, turn count,
status, and winner. `TerritoryCell` stores the fixed 5×5 board values and current ownership.
`TerritoryTurn` is the audit record for every action.

A board is generated once with values from 1 through 5. The server uses `secrets.randbelow()` for
both cell values and six-sided dice.

### Rules

1. A game has exactly 20 alternating turns.
2. Each team's first turn selects an unowned boundary cell. It creates the team's initial territory,
   awards zero points, and does not roll a die.
3. Later targets must be orthogonally adjacent to any cell owned by the acting team.
4. A team cannot target its own cell.
5. Disconnected owned cells still count as territory for adjacency.

For a neutral cell with value `v` and roll `r`:

- `r < v`: no capture; score change is `-(7 - v)`.
- `r == v`: capture; score change is `v - 1`.
- `r > v`: capture; score change is `v`.

For an opponent cell:

- `r >= v`: ownership transfers, attacker gains `v`, defender loses `v`.
- `r < v`: ownership stays unchanged; attacker loses `10 - v`.

After turn 20, the higher score wins; equal scores produce a draw. The transaction locks the game
and target cell so two requests cannot advance the same turn.

### Territory API

- `GET /api/events/territory-control/games/` — mentors see all matches; teams see only matches in
  which they participate.
- `POST /api/events/territory-control/games/` — mentor-only match creation. Body:
  `{"player_one": "alpha", "player_two": "beta"}`.
- `GET /api/events/territory-control/games/<id>/` — full current match state.
- `POST /api/events/territory-control/games/<id>/turns/` — take a turn with zero-based
  `{"row": 0, "column": 0}`. Client-supplied dice fields are rejected.

The response contains the nested board, both players and scores, active player, remaining turns,
winner/draw state, and the previous turn.

### Territory frontend behavior

The board highlights legal-looking targets for guidance, but the backend remains authoritative.
Running matches poll for updates. Dice actions play a timed rolling animation and synthesized sound
while the API request runs; the returned server result is revealed only when the animation lands.
The desktop board fits the available viewport, while tablet and mobile layouts stack naturally.

## Charity Bag

### Model

`CharityBagEvent` stores the participation window, lifecycle state, final totals, result, and
settlement timestamps. `CharityBagParticipation` stores one team's irreversible choice, amount,
deducted stake, final payout, and settlement timestamp.

Database constraints enforce:

- an end time after the start time;
- one instance per configured start time;
- one participation per team per event instance;
- a positive amount;
- a deducted stake equal to the submitted amount;
- a consistent finished/result state.

### Lifecycle

The states are:

1. `scheduled`
2. `active`
3. `resolving`
4. `finished`

`sync_charity_bag()` advances an instance according to server time. API list/detail reads synchronize
due instances, and `resolve_charity_bags` provides the periodic production entry point. Settlement
runs inside one transaction and locks the event, participation rows, and affected teams.

A finished event returns immediately if synchronization runs again. This makes resolution
idempotent: repeated jobs cannot apply payouts twice.

### Entry and settlement rules

During the active window, a team chooses `contribute` or `request` and an amount `y` satisfying:

```text
0 < y <= current team balance
```

The service locks the team row, deducts `y` immediately, and then persists the decision. The choice
cannot be modified.

At settlement:

```text
totalContributed = sum(contribute amounts)
totalRequested   = sum(request amounts)
```

If `totalRequested > totalContributed`, the charity fails:

- contributors receive `2 × y`;
- requesters receive nothing.

Otherwise the charity succeeds:

- requesters receive `2 × y`;
- contributors receive nothing.

Because `y` was already deducted, a winning team has a net gain of `y`; a losing team loses its
stake.

### Privacy

While an instance is active or resolving:

- totals and the result are returned as `null`;
- the shared `participations` list is empty;
- a team may see only its own entry through `my_participation`.

After settlement, final totals, the outcome, and the auditable participation list are exposed.
`can_participate` tells the current team whether the API will accept an entry.

### Charity Bag API

- `GET /api/events/charity-bag/instances/` — list instances with viewer-appropriate visibility.
- `POST /api/events/charity-bag/instances/` — mentor-only creation. Accepts `starts_at` and either
  `ends_at` or `duration_seconds`. Omitting the start opens an instance immediately; the default
  duration is used when no end/duration is supplied.
- `GET /api/events/charity-bag/instances/<id>/` — synchronized state for one instance.
- `POST /api/events/charity-bag/instances/<id>/participate/` — team-only entry. Example:
  `{"action": "contribute", "amount": 50}`.
- `POST /api/events/charity-bag/instances/<id>/resolve/` — mentor-only synchronization. It does not
  settle an event before its configured end time.

### Scheduling

Settings are environment-configurable:

```env
CHARITY_BAG_DURATION_SECONDS=300
CHARITY_BAG_SCHEDULE_TIMES=09:30,12:30
```

The requirements mention three daily executions but currently provide only two exact times. Add the
third time to `CHARITY_BAG_SCHEDULE_TIMES`; no domain code change is needed.

Create one day's instances with:

```bash
uv run manage.py schedule_charity_bags --date YYYY-MM-DD
```

The command is idempotent for the same date and configured start times. Run lifecycle synchronization
regularly from the deployment scheduler:

```bash
uv run manage.py resolve_charity_bags
```

A one-minute interval is sufficient for a five-minute event window. API reads are an additional
safety net, not a replacement for the production scheduler.

### Charity Bag frontend behavior

The page selects the active instance first, followed by resolving, scheduled, and recent finished
instances. It polls frequently during active/resolving states, shows a local one-second countdown,
and refreshes authoritative state when the timer reaches zero.

The contribution/request choice is irreversible and uses a confirmation dialog. Successful entry
invalidates the team query so the displayed Glorium balance refreshes. Active decisions stay sealed;
finished events show the totals and per-team payout ledger. Coin and outcome effects use generated
Web Audio tones, so sound files are not required.

## Continuing development

When changing an event:

1. Put rule changes and all writes in `events/services.py`.
2. Keep views thin and derive the acting team from `request.user.team`.
3. Lock every shared row before checking and changing it; lock team rows before balance mutations.
4. Keep payout/resolution functions idempotent.
5. Add database constraints for invariants that remain meaningful outside the API.
6. Preserve active-phase Charity Bag privacy in every new serializer field.
7. Add API paths only in `frontend/src/services/events.ts`, query behavior in
   `frontend/src/queries/events.ts`, and keys in `frontend/src/queries/keys.ts`.
8. Invalidate the team query after any event balance change.
9. Use existing shadcn-vue primitives, Persian RTL copy, self-hosted fonts, and the responsive mobile
   drawer.
10. Generate a migration, run the focused tests, then run the complete backend suite and frontend
    production build.

Relevant focused tests are:

```bash
uv run pytest tests/test_territory_event.py
uv run pytest tests/test_charity_bag_event.py
```

SQLite does not enforce `select_for_update()`. Concurrency confidence therefore depends on the row
locking design plus the repository's PostgreSQL CI/testing environment.
