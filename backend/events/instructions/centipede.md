Implement a new two-player event called “Centipede Game”.

The project already contains teams, players, Glorium balances, event infrastructure, and the main competition flow. Reuse the existing domain models and conventions.

Game concept:

Two participants play against each other.

Before the game starts, determine who is Player 1 and Player 2 using rock-paper-scissors. If rock-paper-scissors is already handled outside the software, the backend may receive the finalized player ordering instead.

Initial rewards:

Player 1 reward = 50 Glorium
Player 2 reward = 200 Glorium

Only the active player makes a decision.

On their turn, the player chooses one of:

TAKE
CONTINUE

Initial state:

round = 1

player1Reward = 50
player2Reward = 200

activePlayer = Player 1

Turn behavior:

If the active player chooses TAKE:

- The game ends immediately.
- The active player receives their currently displayed reward.
- The other player receives 0 Glorium.
- Add the reward to the winner's existing Glorium balance.
- Mark the game as finished.

Example:

Initial rewards:

Player 1 = 50
Player 2 = 200

If Player 1 selects TAKE:

Player 1 receives 50 Glorium.
Player 2 receives 0 Glorium.

If the active player chooses CONTINUE:

- Do not give either player any reward yet.
- Pass the turn to the other player.

If both players consecutively choose CONTINUE during the current round:

- Double both reward values.
- Start a new round.
- Player 1 becomes the active player again.

Example:

Initial values:

Player 1 = 50
Player 2 = 200

Player 1 chooses CONTINUE.

Player 2 now chooses.

If Player 2 also chooses CONTINUE:

player1Reward = 100
player2Reward = 400

The next round begins.

Player 1 chooses first again.

If both players continue again:

player1Reward = 200
player2Reward = 800

Continue with the same rule.

Therefore the general rewards for round n are:

player1Reward = 50 × 2^(n - 1)

player2Reward = 200 × 2^(n - 1)

The game continues until one player chooses TAKE.

Important rule:

When someone chooses TAKE, they receive only their own currently displayed reward.

The other player's displayed reward is discarded and they receive nothing.

For example:

Current values:

Player 1 = 100
Player 2 = 400

If Player 2 selects TAKE:

Player 2 receives 400.
Player 1 receives 0.

Turn validation:

The backend must verify:

- The game is ACTIVE.
- The requesting participant belongs to this game.
- It is currently their turn.
- The submitted action is valid.
- A finished game cannot receive another action.
- A turn cannot be processed more than once.

State should contain at minimum:

- Game ID
- Player 1
- Player 2
- Current round
- Current Player 1 reward
- Current Player 2 reward
- Current active player
- Previous actions
- Game status
- Winner / player who selected TAKE
- Final reward paid to each player

Suggested statuses:

WAITING_FOR_PLAYERS
ACTIVE
FINISHED

Suggested action enum:

TAKE
CONTINUE

Store every decision so the full sequence can be inspected later.

Example history:

Round 1:
Player 1 -> CONTINUE
Player 2 -> CONTINUE

Round 2:
Player 1 -> CONTINUE
Player 2 -> TAKE

Result:
Player 1 receives 0.
Player 2 receives 400.

Use the project's existing Glorium balance mechanism when giving rewards.

The reward settlement must be atomic and idempotent. Repeating the finishing request must never pay the reward twice.

Do not allow the frontend to directly modify balances or reward values. The backend calculates the current rewards from the game state.

There is no fixed number of rounds according to the current game definition. The game ends only when one player chooses TAKE.

This physical event requires two human participants to operate.