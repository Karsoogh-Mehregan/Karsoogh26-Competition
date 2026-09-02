# Events

This document describes only the competition event subsystem. The Django app lives in
`backend/events/`; its Vue pages and client data layer live under `frontend/src/`.

The app currently contains four independent events:

- **Territory Control** — a two-team, 20-turn board game.
- **Charity Bag** — a timed, shared risk/reward event using team Glorium balances.
- **Centipede Game** — a two-player, alternating risk/reward game with an unbounded number of
  rounds.
- **Gillympics / Olympics** — supervisor-operated physical matches with pluggable mini-games.

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
- `permissions.py` — Territory Control and Centipede participant access.
- `admin.py` — staff inspection of matches, cells, turns, Charity Bag instances, entries, and
  Centipede decisions.
- `management/commands/` — Charity Bag scheduling and lifecycle resolution.
- `migrations/` — both event schemas.

### Frontend

- `frontend/src/pages/TerritoryEventPage.vue`
- `frontend/src/components/territory/TerritoryBoard.vue`
- `frontend/src/pages/CharityBagPage.vue`
- `frontend/src/pages/CentipedeGamePage.vue`
- `frontend/src/pages/OlympicsPage.vue`
- `frontend/src/services/events.ts` — all event API paths.
- `frontend/src/queries/events.ts` — TanStack Query polling, mutations, and cache updates.
- `frontend/src/queries/keys.ts` — event query keys.
- `frontend/src/types/api.ts` — event response and request types.
- `frontend/src/lib/gameAudio.ts` — synthesized dice, result, and coin sounds using the Web Audio
  API; there are no external sound assets.

The SPA routes are:

- `/events/territory-control`
- `/events/charity-bag`
- `/events/centipede-game`
- `/events/olympics`

Both routes require an authenticated session. Navigation is exposed through `InfoPanel.vue`.

## Authentication and authority

Each team signs in through its shared `accounts.User`; `User.team` identifies the authoritative
team. Client-selected team state is never accepted as permission to act.

- Team accounts may play only as their own team.
- Mentors may create Territory matches and Charity Bag instances.
- Mentors may create Centipede matches after the physical rock-paper-scissors ordering is known.
- Mentors can inspect Territory matches but cannot take a team's turn.
- Mentors cannot participate in Charity Bag unless they are using a real team account.
- Mentors can inspect Centipede matches but cannot decide for a player.
- Mentors are the only users who can create, start, and record Gillympics results; participating
  teams may inspect their own matches.
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

## Centipede Game

### Model and lifecycle

`CentipedeGame` stores the ordered players, round, both displayed rewards, active player, action
count, lifecycle status, winner, final payouts, and finish timestamp. `CentipedeDecision` is the
immutable audit row for every choice, including its global sequence, round, actor, action, and the
reward visible to that actor at that moment.

The available statuses are `waiting_for_players`, `active`, and `finished`. The current creation API
receives both already-ordered players and therefore creates an active match immediately. The waiting
status is retained for a future registration or software-based rock-paper-scissors flow.

Database constraints enforce distinct participants, positive round/reward values, participant-only
active players and winners, consistent finished state, and final payouts that agree with the winner.
Each player can have at most one decision in a round, and every sequence number is unique per game.

### Rules

The physical rock-paper-scissors result determines player order before match creation. Player 1
always starts each round.

```text
round n player 1 reward = 50  × 2^(n - 1)
round n player 2 reward = 200 × 2^(n - 1)
```

- `TAKE` ends the game immediately. Only the acting player's displayed reward is added to their
  existing team balance; the other displayed reward is discarded.
- `CONTINUE` from player 1 passes the turn to player 2 without paying anything.
- `CONTINUE` from player 2 completes the round, doubles both rewards, increments the round, and
  returns the turn to player 1.
- There is no fixed final round. The match ends only with `TAKE`.

`play_centipede_action()` locks the game row before validating status, membership, and turn order.
Settlement locks the winner's team row and updates the balance in the same transaction as the game
finish and decision record. A retry after completion is rejected before any balance write, so the
reward cannot be paid twice. Reward and balance fields are never accepted from the client.

### Centipede API

- `GET /api/events/centipede/games/` — mentors see all games; teams see only their own games.
- `POST /api/events/centipede/games/` — mentor-only creation with finalized order. Body:
  `{"player_one": "alpha", "player_two": "beta"}`.
- `GET /api/events/centipede/games/<id>/` — current rewards, active player, result, and full history.
- `POST /api/events/centipede/games/<id>/actions/` — active participant only. Body is exactly
  `{"action": "take"}` or `{"action": "continue"}`; unknown or client-calculated reward fields are
  rejected.

### Centipede frontend behavior

The Persian RTL page presents both live rewards, active-player highlighting, an animated route,
round state, confirmation before `TAKE`, and a complete reverse-chronological decision history. An
active match polls for the other physical participant's move. The layout uses the same project
cards, typography, colors, responsive drawer, and generated Web Audio effects as the other events;
it stacks the action and history panels on smaller screens.

Mentor creation explicitly records Player 1 and Player 2 after the external rock-paper-scissors
result. Team users can see the game but action controls appear only for the currently active player.

## Gillympics / Olympics

### Scope and model

Gillympics records human-supervised physical games; it does not simulate coin or marble movement.
`OlympicsMatch` is the reusable match shell for two ordered teams, a mini-game type, lifecycle
status, optional scoring-zone configuration, winner, and start/finish timestamps.
`OlympicsResult` is the immutable audit record for each main or tiebreak round. It stores the
operator, an idempotency UUID, round number, normalized attempts, totals or best distances, outcome,
and timestamp.

Supported mini-games are:

- `coin_near_wall` — each side throws three coins; the nearer best coin wins.
- `marble_target` — each side plays four marbles; the higher configured-zone total wins.

The available lifecycle values are `created`, `active`, `waiting_for_result`, `tiebreak`, and
`finished`. Current operator flow uses `created` → `active` → either `tiebreak` or `finished`;
`waiting_for_result` is retained for integrations where physical play and result collection are
separate stations.

### Coin Near the Wall

The supervisor may record only the winner, or may additionally enter both closest distances for
auditing. When both distances are present, the backend calculates the nearer side and rejects a
conflicting declared winner. Exactly equal distances must be recorded as a tie and move the match
to `tiebreak`; there is no random winner.

### Marble Target

Scoring zones are configured per match as `{code, label, score}` records. The backend requires four
attempts per side in the main round, resolves zone codes or configured raw scores, and calculates
both totals. Zero represents a miss. A higher total finishes the match; equal totals create a
tiebreak. Tiebreak rounds accept equal, nonzero attempt counts for both sides, allowing the physical
operator's chosen sudden-death format. Further ties remain in `tiebreak`.

### Safety and authority

Only a mentor/operator can create, start, or record a result. The service locks the match before
checking state and assigning the next round. Finished matches reject new results. Retrying the same
`request_id` returns the already-processed match without creating another result. Winners must be
match participants, and server-calculated marble winners cannot be overridden.

Gillympics never imports the Glorium balance mechanism and never writes team balances. Physical
results remain separate from the main competition economy until an explicit reward specification
is added.

### Gillympics API

- `GET /api/events/olympics/matches/` — mentors see all matches; teams see only their own.
- `POST /api/events/olympics/matches/` — mentor-only creation with `mini_game`, `player_one`,
  `player_two`, and configurable `scoring_zones` for Marble Target.
- `GET /api/events/olympics/matches/<id>/` — current state and complete result history.
- `POST /api/events/olympics/matches/<id>/start/` — mentor-only, single-use start.
- `POST /api/events/olympics/matches/<id>/results/` — mentor-only immutable result submission. A
  stable `request_id` UUID is required for retry safety.

### Gillympics frontend behavior

The responsive Persian operator console creates either mini-game, selects the two teams, configures
marble zones, starts physical play, records coin winners/distances or each marble's zone, and shows
live server-calculated totals. Ties change the primary action into tiebreak recording. The side log
shows every round and the operator username. Team accounts receive the same read-only match view.

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
uv run pytest tests/test_centipede_event.py
uv run pytest tests/test_olympics_event.py
```

SQLite does not enforce `select_for_update()`. Concurrency confidence therefore depends on the row
locking design plus the repository's PostgreSQL CI/testing environment.
