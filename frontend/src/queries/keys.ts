export const queryKeys = {
  me: () => ['me'] as const,
  teams: () => ['teams'] as const,
  submissions: () => ['submissions'] as const,
  attempts: (teamCode: string) => ['attempts', teamCode] as const,
  // Prefix key: invalidating it matches every team's attempts list.
  allAttempts: () => ['attempts'] as const,
  leaderboard: () => ['leaderboard'] as const,
  gameState: () => ['game-state'] as const,
  gameSettings: () => ['game-settings'] as const,
}
