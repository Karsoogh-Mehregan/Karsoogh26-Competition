Implement a new single-player event called “Pig Dice Game”.

The project already contains teams, Glorium balances, events, and competition infrastructure. Reuse the existing architecture, balance management, transaction system, and event conventions.

GAME CONCEPT

A participant pays an entry fee of 200 Glorium and starts a risk-based dice game.

The game maintains a temporary pot belonging only to that game session.

Initial state:

entryFee = 200 Glorium
pot = 0
status = ACTIVE

When starting the game:

- Verify that the team has at least 200 Glorium.
- Deduct exactly 200 Glorium from the team's balance.
- Create the game with pot = 0.
- The entry fee is never returned directly.

Only one participant is involved in each game session.

DICE ROLL

The participant may repeatedly choose to roll a standard six-sided die.

The backend must generate the dice result.

The frontend must never provide or control the dice value.

For every roll:

If dice == 1:

- The player loses the entire temporary pot.
- pot becomes 0.
- The game immediately ends.
- The player receives no payout.

If dice is between 2 and 6:

addedAmount = dice × 10 Glorium

Add this amount to the temporary pot.

Examples:

dice = 2 -> +20 Glorium
dice = 3 -> +30 Glorium
dice = 4 -> +40 Glorium
dice = 5 -> +50 Glorium
dice = 6 -> +60 Glorium

After a successful roll, the player may choose between:

ROLL_AGAIN
CASH_OUT

CASH OUT

At any point after at least one successful roll, the participant may choose CASH_OUT.

When CASH_OUT is selected:

- Stop the game immediately.
- Credit the current pot to the team's Glorium balance.
- Mark the game as FINISHED_CASHED_OUT.
- No further rolls are allowed.

Example:

Initial balance = 1000

Entry fee:
1000 - 200 = 800

Roll 4:
pot = 40

Roll 6:
pot = 100

Player cashes out:

Final balance = 900

The participant therefore has a net result of -100 Glorium compared with their initial balance.

MAXIMUM POT

Introduce a configurable maximum pot to prevent unlimited rewards.

Use a configuration field such as:

maxPot

Do not hardcode the value in domain logic.

If a successful roll would cause:

pot >= maxPot

then cap the pot at maxPot and automatically cash out the participant.

Example with maxPot = 500:

Current pot = 470
Dice = 5
Calculated pot = 520

Actual pot = 500

Automatically finish the game and pay 500 Glorium.

GAME STATES

Suggested statuses:

ACTIVE
FINISHED_CASHED_OUT
FINISHED_ROLLED_ONE
FINISHED_MAX_POT

SUPPORTED ACTIONS

ROLL
CASH_OUT

VALIDATION

The backend must verify:

- The participant belongs to the game.
- The game is ACTIVE.
- The entry fee was successfully deducted.
- CASH_OUT cannot happen when pot = 0.
- No action can occur after the game finishes.
- A roll request cannot be processed twice.
- Final payouts cannot happen twice.

Store at minimum:

- Game ID
- Team/player
- Entry fee
- Current pot
- Maximum pot
- Number of rolls
- Every dice result
- Amount added by every roll
- Current game status
- Final payout
- Start timestamp
- Finish timestamp

Use atomic balance operations for both the entry fee and final payout.

The event requires one human operator physically supervising the participant, but all dice results and game state should remain authoritative on the backend if the digital system performs the roll.