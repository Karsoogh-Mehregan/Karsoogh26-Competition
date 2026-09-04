Implement a new event called “Limited Auction”.

The event runs as several independent head-to-head auctions between teams.

The project already contains teams, ranking, Glorium balances, events, and competition infrastructure. Reuse the existing domain and infrastructure.

PAIRING

All teams participate.

Before the event starts, order teams according to the existing competition ranking.

Create pairs:

Rank 1 vs Rank 2
Rank 3 vs Rank 4
Rank 5 vs Rank 6
...

Each pair receives its own independent auction.

If the total number of teams is odd, the final unpaired team automatically receives the auction reward without participating in an auction.

Do not create a dummy opponent.

AUCTION REWARD

Each auction awards:

1000 Glorium

The opening bid is:

10 Glorium

The winner receives 1000 Glorium after the auction finishes.

AUCTION DURATION

Each auction has a fixed time limit.

Default:

10 minutes

Make this duration configurable.

Both auctions for all pairs may run concurrently if that matches the existing event infrastructure.

BIDDING

Only the two teams assigned to an auction may submit bids for that auction.

A new bid must:

- Be greater than the current highest bid.
- Be affordable using the team's currently available Glorium.
- Be submitted while the auction is ACTIVE.

The first valid bid must be at least 10 Glorium.

Use integer Glorium amounts only.

BID PAYMENT MODEL

Bids represent committed Glorium.

When a team places or increases its bid, reserve the amount necessary to bring its committed bid to the new value.

Example:

Team A bids 100.

100 Glorium is committed.

Later Team A increases its bid to 150.

Only an additional 50 Glorium must be committed.

Do not charge 100 + 150.

Each team's current bid therefore represents the total amount it has committed to the auction.

The backend must prevent the team from spending committed Glorium elsewhere.

AUCTION END

When the auction timer expires, determine the highest bidder.

The highest bidder:

- Wins the auction.
- Pays its final bid permanently.
- Receives 1000 Glorium.

The losing team:

- Does not receive the 1000 Glorium reward.
- Also loses its committed bid.
- Its committed Glorium is not returned.

Therefore both teams permanently pay their final submitted bid.

Example:

Team A final bid = 300
Team B final bid = 250

Team A wins.

Team A:
- loses 300 Glorium
- receives 1000 Glorium

Net event effect = +700 Glorium

Team B:
- loses 250 Glorium
- receives nothing

Net event effect = -250 Glorium

If only one team submits a valid bid before the timer expires, that team wins.

If neither team submits a bid, finish the auction without a winner and do not award the 1000 Glorium unless another explicit business rule already exists.

BID VISIBILITY

During the auction, both participating teams should be able to see:

- Current highest bid
- Whether they are currently leading
- Remaining time

They should not need to see the opponent's available total balance.

TIE / CONCURRENCY

Two bids may arrive almost simultaneously.

The backend must serialize bid processing.

A bid is valid only if it is greater than the currently accepted highest bid at the time its transaction is processed.

Do not allow two teams to become the highest bidder with the same amount.

Suggested auction statuses:

SCHEDULED
ACTIVE
FINISHED
CANCELLED

Store at minimum:

- Auction ID
- Event instance ID
- Team A
- Team B
- Start time
- End time
- Current highest bid
- Current highest bidder
- Final bid of each team
- Bid history
- Winner
- 1000 Glorium reward
- Settlement status

Every bid history entry should contain:

- Team
- Bid amount
- Timestamp
- Ordering/sequence information

SETTLEMENT

Auction settlement must be atomic and idempotent.

Running the settlement operation twice must never:

- Deduct bids twice.
- Award the 1000 Glorium twice.

ODD TEAM RULE

If ranking contains an odd number of teams:

- The lowest-ranked unpaired team receives 1000 Glorium automatically.
- It does not pay an auction bid.
- Record this as an automatic award so it remains auditable.

All ranking information used for pairing must be captured when the event starts so ranking changes during the 10-minute event cannot change existing pairs.