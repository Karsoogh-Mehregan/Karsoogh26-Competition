export const queryKeys = {
  me: () => ['me'] as const,
  teams: () => ['teams'] as const,
  submissions: () => ['submissions'] as const,
  occupancyQuestion: () => ['occupancy-question'] as const,
  leaderboard: () => ['leaderboard'] as const,
  territoryGames: () => ['events', 'territory-control', 'games'] as const,
  territoryGame: (gameId: number | 'none') =>
    ['events', 'territory-control', 'games', gameId] as const,
  charityBags: () => ['events', 'charity-bag', 'instances'] as const,
  charityBag: (eventId: number | 'none') =>
    ['events', 'charity-bag', 'instances', eventId] as const,
  centipedeGames: () => ['events', 'centipede', 'games'] as const,
  centipedeGame: (gameId: number | 'none') => ['events', 'centipede', 'games', gameId] as const,
}
