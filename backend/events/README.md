# Events

This document describes only the competition event subsystem. The Django app lives in
`backend/events/`; its Vue pages and client data layer live under `frontend/src/`.

The app currently contains seven independent events:

- **Territory Control** — a two-team, 20-turn board game.
- **Charity Bag** (مؤسسه خیریه) — a timed two-account minority game over team Glorium balances.
- **Centipede Game** — a two-player shared-pot game with four secret choices and up to four
  production rounds.
- **Gillympics / Olympics** — supervisor-operated physical matches with pluggable mini-games.
- **Limited Auction** — rank-seeded simultaneous two-team auctions with committed bids.
- **Prize Wheel** — a configurable, server-selected weighted prize event.
- **Pig** — a single-team dice risk game with an entry fee and cash-out decision.

All events reuse the existing `teams.Team` model and session authentication. Domain mutations
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
- `frontend/src/pages/SpecialGamesPage.vue` — shared responsive console for Auction, Wheel, and Pig.
- `frontend/src/services/events.ts` — all event API paths.
- `frontend/src/queries/events.ts` — TanStack Query polling, mutations, and cache updates.
- `frontend/src/queries/keys.ts` — event query keys.
- `frontend/src/types/api.ts` — event response and request types.
- `frontend/src/lib/gameAudio.ts` — synthesized dice, result, and coin sounds using the Web Audio
  API; there are no external sound assets.

The SPA routes are:

- `/events` — unified catalog, matchmaking, and mentor controls for every minigame.
- `/events/territory-control`
- `/events/charity-bag`
- `/events/centipede-game`
- `/events/coin-near-wall`
- `/events/marble-target`
- `/events/auction`
- `/events/prize-wheel`
- `/events/pig`

All event routes require an authenticated session. The sidebar exposes only the event catalog;
each minigame has its own page without a multi-game tab selector.

## Event catalog and matchmaking

`EventConfiguration` is the authoritative availability record for all eight event choices. Mentors
can enable or disable each event from the unified `/events` page or Django admin. Disabled events
remain readable for audit/history but every mutation is rejected server-side. Charity Bag and
Limited Auction also expose a configurable default duration; an explicit creation-time duration
still takes precedence.

The catalog's quick-start duration inputs are in minutes and are converted to seconds for the API.
Auction and Charity countdowns render every second locally rather than stepping with polling.
Disabled event cards and routes are hidden from players; mentors retain configuration access so
they can re-enable them.

Territory Control, Centipede, Coin Near the Wall, and Marble Target support team matchmaking.
Joining is idempotent while waiting. The second team atomically claims the oldest compatible ticket
and creates the match. Olympics matches remain in their operator-controlled created state so a
mentor still starts physical play and records the result. Marble scoring zones come from the event
configuration rather than the client.

A matched ticket remains the team's active match until the underlying game is finished. The team
can then dismiss it from the event catalog; dismissal hides only the active ticket, keeps the full
game and decision history for audit, and allows the team to join matchmaking again. The backend
rejects dismissal while the game is still running.

APIs:

- `GET /api/events/catalog/` — availability, timer, and capability metadata.
- `PATCH /api/events/catalog/<code>/` — mentor-only enable/disable and configuration update.
- `GET /api/events/matchmaking/` — the authenticated team's recent tickets.
- `POST /api/events/matchmaking/<code>/join/` and `/cancel/` — enter or leave a queue.
- `POST /api/events/matchmaking/<ticket-id>/dismiss/` — exit a finished match and free the team for
  another opponent.

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

The turn response is resolved atomically by the backend, while the client keeps the previous active
player visible until the dice animation reveals the server-generated result. Once both starting
positions exist, capturing a participant's last territory ends the match immediately and awards the
win to the attacker; the normal 20-turn score comparison remains the other finish condition.

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

The rules sheet calls it **مؤسسه خیریه**. It is a minority game over two accounts, not a
donation: teams put Glorium into the **mice** account (موش‌گیل‌ها) or the **lions** account
(شیرگیل‌ها), and the account holding *less* money at the close takes the other one.

### Model

`CharityBagEvent` stores the participation window, the freeze window, the minimum stake,
lifecycle state, final per-account totals, the winning side, and settlement timestamps.
`CharityBagParticipation` stores one team's irreversible side, amount, deducted stake, final
payout, and settlement timestamp.

Database constraints enforce:

- an end time after the start time;
- one instance per configured start time per board;
- one participation per team per event instance;
- a positive amount;
- a deducted stake equal to the submitted amount;
- a consistent finished/result state. `winning_side` stays null on a finished event when nobody
  won — a tie, or an account nobody joined.

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

During the active window, a team chooses `mice` or `lions` and an amount `y` satisfying:

```text
minimum_stake <= y <= current team balance
```

The service locks the team row, deducts `y` immediately, and then persists the decision. The choice
cannot be modified, and a team enters exactly once.

At settlement:

```text
totalMice  = sum(mice amounts)
totalLions = sum(lions amounts)
```

The account with the **smaller** total wins and shares out the losing account in proportion to each
winner's share of its own account. A winner is also refunded its stake; a loser keeps nothing:

```text
payout(winner) = y + y * (losingTotal + absentFines) * multiplier / winningTotal
multiplier     = 2 when the lions win, 1 when the mice win
```

The lions' extra multiple is paid by the charity fund, exactly as the rules sheet describes. Integer
division floors the share, so the fund never pays out more than the stated formula.

Taking part is compulsory. At settlement, every team on the event's board that submitted nothing is
fined `minimum_stake` — capped at the balance it actually holds — and the fines are poured into the
**losing** account, so the winners share them out with the rest of the prize. The fines land after
the winner is known, so they never decide which account was the smaller one; `absent_penalty_total`
records what was collected. A `minimum_stake` of 0 means no fine.

Two settlements name no winner and refund every stake instead: equal totals, and an account nobody
joined (a prize with no one to collect it would otherwise burn the other account's money). Neither
fines the absent teams — there would be nobody to hand the money to.

### Privacy and the freeze window

Running account totals are public during the event — deciding against them *is* the game — but the
last `freeze_seconds` (180 by default) of the window freeze what players see: totals then count only
entries submitted before `freeze_at`, so a late entry cannot be read off the board. Individual
choices stay hidden throughout:

- the shared `participations` list is empty until the event is finished;
- a team sees only its own entry through `my_participation`;
- `totals_frozen` tells the SPA whether the displayed totals are live or frozen.

After settlement, final totals, the winning side, and the auditable participation list are exposed.
`can_participate` tells the current team whether the API will accept an entry.

### Charity Bag API

- `GET /api/events/charity-bag/instances/` — list instances with viewer-appropriate visibility.
- `POST /api/events/charity-bag/instances/` — mentor-only creation. Accepts `starts_at`, either
  `ends_at` or `duration_seconds`, and optional `minimum_stake`/`freeze_seconds`. Omitting the start
  opens an instance immediately; the configured defaults are used for anything not supplied
  (`EventConfiguration.settings` first, then the environment).
- `GET /api/events/charity-bag/instances/<id>/` — synchronized state for one instance.
- `POST /api/events/charity-bag/instances/<id>/participate/` — team-only entry. Example:
  `{"side": "mice", "amount": 50}`.
- `POST /api/events/charity-bag/instances/<id>/resolve/` — mentor-only synchronization. It does not
  settle an event before its configured end time.

### Scheduling

Settings are environment-configurable:

```env
CHARITY_BAG_DURATION_SECONDS=600
CHARITY_BAG_SCHEDULE_TIMES=14:30,15:30,17:30
CHARITY_BAG_FREEZE_SECONDS=180
CHARITY_BAG_MINIMUM_STAKE=0
```

Create one day's instances with:

```bash
uv run manage.py schedule_charity_bags --date YYYY-MM-DD
```

The command is idempotent for the same date and configured start times. Run lifecycle synchronization
regularly from the deployment scheduler:

```bash
uv run manage.py resolve_charity_bags
```

A one-minute interval is sufficient for a ten-minute event window. API reads are an additional
safety net, not a replacement for the production scheduler.

### Charity Bag frontend behavior

The page selects the active instance first, followed by resolving, scheduled, and recent finished
instances. It polls frequently during active/resolving states, shows a local one-second countdown,
and refreshes authoritative state when the timer reaches zero.

A mentor sets the round's length and its minimum stake in the header of the charity page (and on the
hub card) before opening it, so the number a team must meet is chosen per round rather than only in
`EventConfiguration`. The hub seeds its field from `EventConfiguration.settings.minimum_stake`.

The account choice is irreversible and uses a confirmation dialog. Successful entry invalidates the
team query so the displayed Glorium balance refreshes. Both account totals are on screen the whole
time, with a freeze notice in the closing minutes; individual decisions stay sealed, and finished
events show the winning account and the per-team payout ledger. Coin and outcome effects use generated
Web Audio tones, so sound files are not required.

## Centipede Game

New matches use shared-pot rules (`rules_version=2`). Each team pays **100 Glorium**
when a match is created; both balances are locked in primary-key order and charged in
one transaction. If either cannot afford entry, no game is created and neither is charged.
Matchmaking uses this same service. Entry is charged on matching, not while waiting.

### Choices and payouts

The pot starts at 200. Either player may submit first. Both choices are committed and
hidden until the round resolves; there is no active-player ordering or RPS requirement.

- Both `produce`: add **200 total**, advance the round, pay nothing.
- Both `steal`: finish, both receive zero.
- One `steal`: takes the whole pot unless the opponent chose `preserve`; then the
  thief gets four-fifths and the preserving player gets one-fifth.
- Without a thief: `split` receives half, `preserve` receives one-fifth, and
  `produce` receives zero. Unallocated money is not paid to either team.
- Every combination except two producers finishes the match.
- Four successful production rounds reach a pot of **1000**. The match remains active
  in decision round 5, but `produce` is rejected; both must choose another action.

Payouts are gross distributions from the pot, not additional entry refunds.
The winner field is the sole higher-payout participant, or null for equal payouts.
Both final payout fields are authoritative, including split outcomes and zero/zero.

### State, security, and API

`CentipedeGame` records the rules version, pot, production count, decision round,
participants, status and final payouts. `CentipedeDecision` records every choice.
For version 2, its legacy-named `displayed_reward` audit field stores the pot at the
moment of submission. The legacy `current_reward` API field is zero in new matches.

- `GET /api/events/centipede/games/`: own games (all games for mentors).
- `POST /api/events/centipede/games/`: mentor creates and charges entry with
  `{"player_one":"alpha","player_two":"beta"}`.
- `GET /api/events/centipede/games/<id>/`: state, submitted flags, revealed history.
- `POST /api/events/centipede/games/<id>/actions/`:
  `{"action":"produce","round_number":1}` (or split/steal/preserve).

The server verifies membership, active status, exact round, valid action, production
cap and one decision per participant per round. A round number is mandatory, preventing
a delayed duplicate production request from entering the next round. Pending choices
are omitted from history on **all** API surfaces, including mentor responses;
only each player's `has_chosen` flag is public. Completed rounds reveal both choices.

Settlement holds the match lock and locks both team balances in stable order. Decisions,
payouts and finish state commit together; repeat finishing requests are rejected before
any payout. Admin game/decision records are read-only to prevent bypassing these services.
PostgreSQL concurrency coverage is marked `postgres_only`; SQLite cannot validate row locks.

### Compatibility and frontend

Migration 0009 marks existing games as version 1 without changing balances or decisions.
They retain the original TAKE/CONTINUE service and UI. New games default to version 2.
Do not retroactively charge existing matches or rewrite their histories.

The Persian RTL page uses the existing shadcn components and theme, with responsive
four-choice cards, an animated shared pot, four production indicators, confirmation,
locked/waiting states, per-player final payouts and revealed history. Each participant
uses their own account/device. A finished match returns to the event hub for dismissal
and another matchmaking entry.

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
- `POST /api/events/olympics/matches/<id>/player-run/` — a participant submits their own run with
  `round_number` and either `best_distance` or `attempts`. Identity comes from the session, not an
  editable team field. Runs are immutable; identical retries are safe and stale rounds are rejected.
- `POST /api/events/olympics/matches/<id>/results/` — mentor-only immutable result submission. A
  stable `request_id` UUID is required for retry safety.

### Gillympics frontend behavior

Each participant plays their own run on their own logged-in device. The local touch arena uses a
fixed 600-by-600 simulation coordinate system, independent of display size. It derives launch
velocity from the drag gesture, resolves collisions between that player's pieces and fall-off,
and restricts pre-launch movement to the bottom quarter. Coin mode has a rebound wall; Marble
mode has open edges and configurable scoring rings. Separate devices do not share a live physics
board: their completed runs are stored as `OlympicsPlayerRun` and shown to both participants and
the supervisor. These are participant-reported outcomes, not server-simulated trajectories.
Once both runs arrive, the match waits for supervisor confirmation. The result dialog is prefilled
with their submitted results; confirmation uses the existing server validation and auditing.
Tiebreak runs use a new round number, leaving prior submissions intact. No Glorium is paid.

## Limited Auction

Creating an `AuctionEvent` snapshots the current Glorium ranking and pairs ranks 1–2, 3–4, and so
on. An unpaired final team receives the configured reward automatically. A bid must be an affordable
integer above both the opening and current highest bid. Raising your own bid deducts only the
difference; every commitment remains spent. Locked, idempotent settlement pays the leading team
once, while a pair with no bids has no winner.

The `/api/events/limited-auction/` endpoints let mentors create and resolve events and let teams bid
on their own pair using a stable `request_id`.

## Prize Wheel

`WheelPrize` records configurable type, label, weight, stock, availability, and metadata. A spin
locks the event, team, and eligible prizes, charges once, and uses `secrets.randbelow()` for weighted
selection. Glorium is credited immediately, merchandise waits for operator delivery, and claiming
the one grand prize closes the event. Prize weights are hidden from ordinary team responses.

The `/api/events/prize-wheel/` endpoints provide mentor create/start/stop/delivery operations and
team spins. Request UUIDs make a retried spin return the original outcome without another charge.

## Pig

A mentor creates a `PigEvent` with a configurable maximum pot. Starting a game atomically charges
the 200 Glorium entry. Each server-generated d6 roll is audited: 1 ends with no payout; 2–6 add ten
times the face value. Cash-out requires a positive pot, while reaching the cap pays the cap and ends
automatically. Action UUIDs, row locks, and terminal states prevent duplicate rolls or payouts.

The `/api/events/pig/` endpoints cover event creation/finish, team game start, and `roll` or
`cash_out`. Frontend dice animation is presentational and reveals only the server result.

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
uv run pytest tests/test_arcade_events.py
```

SQLite does not enforce `select_for_update()`. Concurrency confidence therefore depends on the row
locking design plus the repository's PostgreSQL CI/testing environment.
