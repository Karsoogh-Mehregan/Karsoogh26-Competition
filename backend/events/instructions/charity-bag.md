Implement a new backend event called “Charity Bag”.

The project already contains teams, team balances using the existing Glorium currency, the main game flow, and existing event infrastructure. Follow the current backend architecture, domain conventions, persistence model, scheduling approach, and API patterns. Do not introduce duplicate concepts if equivalents already exist.

Event concept:

A virtual shared bag is created for a limited period.

Every team may participate once during the active period by choosing one of two actions:

1. Contribute Glorium to the charity.
2. Request Glorium from the charity.

Each team chooses an amount y.

Eligibility:

If a team currently owns x Glorium, it may choose an amount y such that:

0 < y <= x

This restriction applies to both contributing and requesting.

When the team submits its choice, y Glorium is immediately deducted from the team's balance.

This deduction acts as the team's stake in the event and must happen immediately when the action is accepted.

A team cannot modify its decision after submitting it unless the existing event architecture explicitly supports such behavior.

Each team may submit only one action per Charity Bag event instance.

The event remains open for a short period, approximately 5 to 10 minutes.

Prefer a configurable duration instead of hardcoding it. The intended default duration is 5 minutes.

At the end of the event, calculate:

totalContributed = sum of y for teams that selected CONTRIBUTE

totalRequested = sum of y for teams that selected REQUEST

The event then resolves into one of two outcomes.

Outcome 1: Charity failed

Condition:

totalRequested > totalContributed

In this case:

For teams that selected REQUEST:
- Their initially deducted y Glorium is lost.
- They receive nothing.

For teams that selected CONTRIBUTE:
- They receive 2 × y Glorium.
- Since y was already deducted when they entered the event, the settlement should credit 2 × y back to their balance.

Example:

A team has 100 Glorium.

It contributes 20.

Immediately after participating:
balance = 80

If the charity fails:
credit 40

Final balance = 120

Therefore, a successful contribution during a failed charity produces a net profit of +20.

Outcome 2: Charity succeeded

Condition:

totalRequested <= totalContributed

In this case:

For teams that selected REQUEST:
- They receive 2 × y Glorium.
- Since y was initially deducted, their net gain is +y.

For teams that selected CONTRIBUTE:
- Their initially deducted y Glorium is not returned.
- They receive nothing.

Example:

A team has 100 Glorium.

It requests 20.

Immediately after participating:
balance = 80

If the charity succeeds:
credit 40

Final balance = 120.

Event lifecycle:

The event should have states equivalent to:

SCHEDULED
ACTIVE
RESOLVING
FINISHED

When ACTIVE:
- Teams may submit their action.
- Validate their current balance.
- Deduct the selected amount immediately.
- Persist their decision.

When the participation window closes:
- Reject further participation.
- Resolve the event exactly once.
- Calculate totals.
- Determine success or failure.
- Apply all payouts.
- Persist the final outcome.

The settlement operation must be idempotent. Restarting the application or executing the resolution job twice must never result in duplicate payouts.

Concurrency must also be handled correctly. A team must never be able to spend the same Glorium simultaneously in multiple requests if its balance is insufficient.

Store enough information for auditing and frontend display, including:

- Event instance ID
- Event status
- Start time
- End time
- Remaining time while active
- Each participating team
- Team action: CONTRIBUTE or REQUEST
- Amount selected
- Amount initially deducted
- Final payout
- Total contributed amount
- Total requested amount
- Whether the charity succeeded
- Final settlement state

The frontend should be able to query the current event state and see whether participation is currently allowed.

Do not expose other teams' decisions or amounts while the event is ACTIVE if that information could influence later decisions. During the active phase, return only information that the current team is allowed to know.

After the event finishes, expose the final totals and result according to the project's existing event visibility conventions.

Scheduling:

This event is intended to run 3 times during the competition day.

Known scheduled times currently specified are:

- 09:30
- 12:30

The specification currently mentions three executions but provides only two exact start times. Keep the schedule configurable so the third execution time can be added without changing domain logic.

Each event instance must be independent. Participation in one instance must not affect whether a team can participate in later instances, except through the team's resulting Glorium balance.

Use the project's existing team balance mechanism for all deductions and payouts.

All validation, settlement calculations, timing rules, and balance changes must be authoritative on the backend.