Implement a new physical competition event tentatively called “Olympics” / “Gillympics”.

The software does not simulate the physical movement of coins or marbles. The physical game is performed by participants and a human event operator records the result in the backend.

The project already contains teams, participants, events, scores, and competition infrastructure. Follow existing architecture and event conventions.

This event can support multiple physical mini-games under the same event type.

Two currently defined mini-games are:

1. Coin Near the Wall
2. Marble Target

MINI-GAME 1: COIN NEAR THE WALL

Two players or teams compete against each other.

Each side receives 3 coins.

Players physically throw their coins toward a wall.

After both sides have thrown all 3 coins, determine each side's closest coin to the wall.

The side whose closest coin is nearer to the wall wins.

Only the nearest coin belonging to each participant matters for deciding the winner.

Example:

Team A distances:

30 cm
15 cm
8 cm

Best distance = 8 cm

Team B distances:

20 cm
9 cm
11 cm

Best distance = 9 cm

Team A wins because 8 cm is closer to the wall.

The backend does not need to calculate physical distance unless the event operator enters measurements.

At minimum, the operator must be able to submit:

- Participant/team A
- Participant/team B
- Winner

Optionally, support entering the best measured distance for each side for auditing.

If both closest coins have exactly the same distance, treat the game as a tie and require a replay/tiebreak instead of choosing a random winner.

MINI-GAME 2: MARBLE TARGET

Two players or teams compete against each other.

A target consisting of multiple scoring zones is physically drawn on the ground.

Each player receives 4 marbles.

Players alternate turns rolling one marble toward the target.

Each scoring zone has a predetermined score.

After all 8 marbles have been played:

- Calculate Player A's total score.
- Calculate Player B's total score.
- The participant with the higher score wins.

Example target scoring:

Outer area = 1 point
Next ring = 2 points
Next ring = 3 points
Center = 5 points

Do not hardcode these exact values unless they are already finalized in the project. Prefer configurable scoring zones so event organizers can define the scoring system.

For each marble, the operator can record the zone or score reached.

Example:

Player A:

Marble 1 -> 2
Marble 2 -> 5
Marble 3 -> 0
Marble 4 -> 3

Total = 10

Player B:

Marble 1 -> 1
Marble 2 -> 3
Marble 3 -> 3
Marble 4 -> 2

Total = 9

Player A wins.

Tie rule:

If both participants finish with the same total score, the game does not end.

A tiebreak round must be played.

For the tiebreak, both participants play again according to the event operator's physical rules until one participant achieves a higher result.

Do not randomly choose the winner.

GENERAL EVENT FLOW

Suggested states:

CREATED
ACTIVE
WAITING_FOR_RESULT
TIEBREAK
FINISHED

The event operator should be able to:

- Create/start a match.
- Select the mini-game type.
- Assign the participating players or teams.
- Record physical results.
- Declare or calculate the winner.
- Start a tiebreak if necessary.
- Finish the match.

Suggested mini-game enum:

COIN_NEAR_WALL
MARBLE_TARGET

The backend must prevent:

- Submitting results for a finished match.
- Declaring participants that are not part of the match.
- Declaring an invalid winner.
- Processing the same result twice.

Store enough information for auditing and frontend display:

- Match ID
- Mini-game type
- Participants
- Current status
- Recorded attempts/results
- Total scores where applicable
- Whether a tiebreak occurred
- Winner
- Start and finish timestamps

The event is primarily operated by one human event supervisor. The supervisor records what happens in the physical game.

Keep physical-game rules separate from the main game economy unless the existing specification defines a Glorium reward for winning. Do not invent a Glorium payout.

If the project's existing event system already contains generic physical match or tournament functionality, extend it instead of creating duplicate infrastructure.