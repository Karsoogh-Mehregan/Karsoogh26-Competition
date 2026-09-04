import type { Board } from '@/types/api'

// Board-scoped keys carry the contest, because the same URL returns
// different rows for a girls team and a boys team.
export const queryKeys = {
  me: () => ['me'] as const,
  teamsRoot: () => ['teams'] as const,
  teams: (board: Board) => ['teams', board] as const,
  submissions: () => ['submissions'] as const,
  submission: (id: number) => ['submissions', id] as const,
  // Prefix key: invalidating it matches every team's attempts list.
  attemptsRoot: () => ['attempts'] as const,
  attempts: (teamCode: string) => ['attempts', teamCode] as const,
  leaderboardRoot: () => ['leaderboard'] as const,
  leaderboard: (board: Board) => ['leaderboard', board] as const,
  territoryGames: () => ['events', 'territory-control', 'games'] as const,
  territoryGame: (gameId: number | 'none') =>
    ['events', 'territory-control', 'games', gameId] as const,
  charityBagsRoot: () => ['events', 'charity-bag', 'instances'] as const,
  charityBags: (board: Board) => ['events', 'charity-bag', 'instances', board] as const,
  charityBag: (eventId: number | 'none') =>
    ['events', 'charity-bag', 'instances', eventId] as const,
  centipedeGames: () => ['events', 'centipede', 'games'] as const,
  centipedeGame: (gameId: number | 'none') => ['events', 'centipede', 'games', gameId] as const,
  olympicsMatches: () => ['events', 'olympics', 'matches'] as const,
  olympicsMatch: (matchId: number | 'none') => ['events', 'olympics', 'matches', matchId] as const,
  auctionEventsRoot: () => ['events', 'limited-auction'] as const,
  auctionEvents: (board: Board) => ['events', 'limited-auction', board] as const,
  wheelEventsRoot: () => ['events', 'prize-wheel'] as const,
  wheelEvents: (board: Board) => ['events', 'prize-wheel', board] as const,
  pigEventsRoot: () => ['events', 'pig'] as const,
  pigEvents: (board: Board) => ['events', 'pig', board] as const,
  eventCatalog: () => ['events', 'catalog'] as const,
  matchmaking: () => ['events', 'matchmaking'] as const,
  gameState: () => ['game-state'] as const,
  gameSettings: () => ['game-settings'] as const,
  entrySheet: () => ['entry-sheet'] as const,
  mapDesignRoot: () => ['map-design'] as const,
  mapDesign: (board: Board) => ['map-design', board] as const,
  levels: () => ['levels'] as const,
  balanceEventsRoot: () => ['balance-events'] as const,
  balanceEvents: (teamCode: string) => ['balance-events', teamCode] as const,
  inbox: () => ['inbox'] as const,
  notification: (id: number) => ['notification', id] as const,
  // Prefix key: invalidating it matches the draft and sent lists at once.
  messagesRoot: () => ['messages'] as const,
  messages: (status: 'draft' | 'sent') => ['messages', status] as const,
  audienceOptions: () => ['audience-options'] as const,
  audiencePreview: (key: string) => ['audience-preview', key] as const,
  messageRecipients: (id: number) => ['message-recipients', id] as const,
  items: () => ['items'] as const,
  // Prefix key: invalidating it matches the board and the target table at once.
  duelsRoot: () => ['duels'] as const,
  duelBoard: () => ['duels', 'board'] as const,
  duelTargets: () => ['duels', 'targets'] as const,
  minesweeperRoot: () => ['minesweeper'] as const,
  minesweeperAttempt: (attemptId: number) => ['minesweeper', 'attempt', attemptId] as const,
}
