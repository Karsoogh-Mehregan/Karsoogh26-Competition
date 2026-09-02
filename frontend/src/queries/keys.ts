export const queryKeys = {
  me: () => ['me'] as const,
  teams: () => ['teams'] as const,
  submissions: () => ['submissions'] as const,
  attemptsRoot: () => ['attempts'] as const,
  attempts: (teamCode: string) => ['attempts', teamCode] as const,
  leaderboard: () => ['leaderboard'] as const,
  entrySheet: () => ['entry-sheet'] as const,
  minesweeperRoot: () => ['minesweeper'] as const,
  minesweeperGame: (gameId: number) => ['minesweeper', gameId] as const,
}
