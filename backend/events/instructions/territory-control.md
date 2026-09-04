Implement a new backend event for a two-player, turn-based territory-control dice game.

The project already contains the main game, teams, players, and the existing backend/frontend architecture. Follow the current project conventions and architecture instead of introducing a separate game framework.

Game rules:

The game is played on a randomly generated 5×5 grid.

Each cell contains a random integer from 1 to 5. This value remains fixed for the entire game.

Two players participate.

The game contains exactly 20 turns. Players alternate turns, so each player receives exactly 10 turns.

Starting position:

On a player's first turn, they must choose one cell on the outer boundary of the 5×5 grid as their starting cell.

The player starts with 0 points.

The selected starting cell becomes owned by that player.

Each player's owned cells must form a connected territory.

After the starting turn, the player may target any cell that is orthogonally adjacent to their currently owned territory. Diagonal adjacency does not count.

A player cannot normally target an unrelated cell elsewhere on the board.

There are two possible actions:

1. Capture an unowned cell.
2. Attack a cell owned by the opponent.

Capturing an unowned cell:

Suppose the targeted cell has value x, where x is between 1 and 5.

Roll a standard six-sided die.

If roll < x:
- The capture fails.
- The cell remains unowned.
- The player loses 7 - x points.

If roll == x:
- The capture succeeds.
- The player gains ownership of the cell.
- The player gains x - 1 points.

If roll > x:
- The capture succeeds.
- The player gains ownership of the cell.
- The player gains x points.

The scoring values are intentionally designed so that attempting neutral cells has approximately balanced expected value.

Attacking an opponent's cell:

A player may target an opponent-owned cell if that cell is orthogonally adjacent to the attacker's current territory.

Suppose the attacked cell has value x.

Roll a standard six-sided die.

If roll >= x:
- The attack succeeds.
- Ownership of the cell transfers to the attacker.
- The attacker gains x points.
- The defender loses x points.

If roll < x:
- The attack fails.
- Ownership remains unchanged.
- The attacker loses 10 - x points.
- The defender's score does not change.

Attacking is therefore intentionally riskier than capturing neutral territory. It can be used both to increase the attacker's score and reduce the opponent's score.

Territory rules:

Each cell can have one of three ownership states:
- Unowned
- Player 1
- Player 2

Players may only target cells adjacent to at least one cell they currently own.

When a cell changes ownership because of an attack, do not automatically transfer any neighboring cells.

A player's territory does not need to remain connected after losing a cell. Existing disconnected cells remain owned by that player and may still be considered part of their territory for determining valid adjacent moves.

Turn flow:

For each turn:

1. Verify that the game has not ended.
2. Verify that it is the requesting player's turn.
3. If this is the player's first turn, require them to choose an unowned boundary cell as their starting position.
4. Otherwise, require them to choose a valid adjacent target.
5. Determine whether the target is neutral or enemy-owned.
6. Roll a six-sided die on the backend.
7. Apply the corresponding capture or attack rules.
8. Update ownership and scores.
9. Store the result of the turn.
10. Switch the active player.
11. Increase the total number of completed turns.

The backend must generate the dice roll. The frontend must never be allowed to provide or control the roll result.

Game ending:

The game ends immediately after 20 completed turns.

Each player will therefore normally have played 10 turns.

The player with the higher score wins.

If both players have equal scores, the game ends as a draw.

The game state should contain enough information for the frontend to render the entire game, including at minimum:

- The 5×5 board.
- The fixed numeric value of every cell.
- The owner of every cell.
- Both players.
- Both scores.
- Current active player.
- Number of completed turns.
- Number of turns remaining.
- Whether each player has selected their starting position.
- Current game status.
- Winner when the game is finished.
- Previous turn result.

Each completed turn should expose enough information to explain what happened, including:

- Acting player.
- Target cell.
- Target cell value.
- Action type, neutral capture or opponent attack.
- Dice result.
- Success or failure.
- Score change for the attacker.
- Score change for the defender when applicable.
- Ownership change.

Treat all game rules and validation as backend domain logic. The frontend should only display state and send player decisions.

Use the existing project's domain model, event conventions, team/player identifiers, persistence approach, error-handling style, and API conventions. Do not duplicate concepts that already exist in the project.