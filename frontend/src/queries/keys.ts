export const queryKeys = {
  me: () => ['me'] as const,
  teams: () => ['teams'] as const,
  submissions: () => ['submissions'] as const,
  attemptsRoot: () => ['attempts'] as const,
  attempts: (teamCode: string) => ['attempts', teamCode] as const,
  leaderboard: () => ['leaderboard'] as const,
  entrySheet: () => ['entry-sheet'] as const,
  levels: () => ['levels'] as const,
  balanceEventsRoot: () => ['balance-events'] as const,
  balanceEvents: (teamCode: string) => ['balance-events', teamCode] as const,
}
