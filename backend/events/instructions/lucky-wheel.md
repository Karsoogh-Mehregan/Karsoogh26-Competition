Implement a new event called “Prize Wheel”.

This is a single-team-at-a-time event operated by one human event supervisor.

The event consists of a configurable prize wheel containing Glorium rewards, merchandise rewards, and a Grand Prize.

The project already contains teams, Glorium balances, event infrastructure, and competition state. Follow existing project conventions.

SPIN COST

Each spin costs a configurable amount of Glorium.

Default:

spinCost = 10 Glorium

Before accepting a spin:

- Verify that the team has enough Glorium.
- Atomically deduct the spin cost.
- Generate the result on the backend.
- Store the result.
- Apply the prize.

The frontend must never choose or provide the resulting wheel segment.

PRIZE TYPES

Support at least:

GLORIUM
MERCHANDISE
GRAND_PRIZE

Each wheel segment should be configurable.

Example configuration:

GLORIUM -> 20
GLORIUM -> 50
MERCHANDISE -> Chocolate
MERCHANDISE -> Special Sticker
GRAND_PRIZE -> configured grand prize

Do not hardcode these example prizes into domain logic.

Each prize configuration should define:

- Prize ID
- Prize type
- Display name
- Value/reward data
- Weight/probability
- Availability
- Optional stock

GLORIUM PRIZE

When a team receives a Glorium prize:

- Credit the configured amount to its Glorium balance.
- Store the payout.

MERCHANDISE PRIZE

When a merchandise prize is selected:

- Record that the team won the item.
- Mark the item as pending physical delivery or delivered according to the existing operator workflow.
- Reduce stock if the prize has limited inventory.

Do not substitute Glorium automatically for unavailable merchandise unless explicitly configured.

GRAND PRIZE

The event continues until the Grand Prize is won.

When a spin lands on GRAND_PRIZE:

- Award the configured Grand Prize.
- Record the winning team.
- Mark the Grand Prize as claimed.
- Close the event.
- Reject future spins for this event instance.

The system must guarantee that the Grand Prize cannot be awarded twice.

If multiple spin requests arrive concurrently near the end of the event, process them atomically.

EVENT ECONOMY

Track the total amount of Glorium collected from spins.

For example:

spinCost = 10
127 completed spins

totalCollected = 1270 Glorium

This value should be available to administrators for event reporting.

Do not use the collected amount to dynamically change prize probabilities unless explicitly configured.

WHEEL CONFIGURATION

The probability system must be configurable rather than implemented using duplicated wheel entries.

For example:

Prize A: weight 40
Prize B: weight 30
Prize C: weight 20
Grand Prize: weight 1

The backend should perform weighted random selection using the configured weights.

Use an appropriate secure/server-side random generator according to the project's existing conventions.

EVENT STATE

Suggested statuses:

SCHEDULED
ACTIVE
GRAND_PRIZE_CLAIMED
FINISHED

A spin should contain:

- Spin ID
- Event ID
- Team
- Spin cost
- Timestamp
- Selected prize ID
- Prize type
- Glorium payout if applicable
- Merchandise delivery status if applicable

The event state should expose:

- Whether spins are currently available
- Spin cost
- Available prize descriptions
- Whether the Grand Prize remains available
- The current team's previous wins if appropriate
- Remaining merchandise stock if organizers want this visible

Do not expose internal probability weights to normal participants unless explicitly required.

OPERATOR FUNCTIONALITY

Because the event requires one human operator, provide an operator/admin flow for:

- Starting the event.
- Stopping/cancelling the event.
- Viewing spin results.
- Marking physical merchandise as delivered.
- Viewing remaining merchandise stock.
- Viewing total Glorium collected.
- Viewing the Grand Prize winner.

If merchandise such as stickers or chocolate is unavailable, organizers must be able to configure the wheel with only Glorium and other available rewards without requiring code changes.

SETTLEMENT AND CONCURRENCY

Every spin must be atomic.

A successful request must perform exactly once:

1. Deduct spin cost.
2. Determine result.
3. Store result.
4. Apply prize.

A retried request must not charge the team twice or generate a different prize.

Use an idempotency mechanism or the project's existing equivalent for spin requests.