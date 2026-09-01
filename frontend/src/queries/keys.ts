export const queryKeys = {
  me: () => ['me'] as const,
  teams: () => ['teams'] as const,
  submissions: () => ['submissions'] as const,
  attempts: (teamCode: string) => ['attempts', teamCode] as const,
  leaderboard: () => ['leaderboard'] as const,
}
