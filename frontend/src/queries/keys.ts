export const queryKeys = {
  me: () => ['me'] as const,
  teams: () => ['teams'] as const,
  submissions: () => ['submissions'] as const,
  // Prefix key: invalidating it matches every team's attempts list.
  attemptsRoot: () => ['attempts'] as const,
  attempts: (teamCode: string) => ['attempts', teamCode] as const,
  leaderboard: () => ['leaderboard'] as const,
  gameState: () => ['game-state'] as const,
  gameSettings: () => ['game-settings'] as const,
  entrySheet: () => ['entry-sheet'] as const,
  inbox: () => ['inbox'] as const,
  // Prefix key: invalidating it matches the draft and sent lists at once.
  messagesRoot: () => ['messages'] as const,
  messages: (status: 'draft' | 'sent') => ['messages', status] as const,
  audienceOptions: () => ['audience-options'] as const,
  audiencePreview: (key: string) => ['audience-preview', key] as const,
}
