import { readonly } from 'vue'
import { openBoardStream } from '@/lib/eventSource'
import { streamConnected } from '@/lib/boardStreamState'
import { queryClient } from '@/lib/queryClient'
import { queryKeys } from '@/queries/keys'
import type { GameState, Me } from '@/types/api'

const MIN_INTERVAL_MS = 1800
const JITTER_MS = 600

type QueryKey = readonly unknown[]

function viewerSeesFrozenLeaderboard(): boolean {
  const me = queryClient.getQueryData<Me | null>(queryKeys.me())
  const state = queryClient.getQueryData<GameState>(queryKeys.gameState())
  return me?.team != null && state?.leaderboard_frozen === true
}

const BOARD = [queryKeys.teamsRoot()]
const ROUTES: Record<string, () => QueryKey[]> = {
  'board.spawn.claimed': () => BOARD,
  'board.node.claimed': () => [queryKeys.teamsRoot(), queryKeys.balanceEventsRoot()],
  'board.released': () => [queryKeys.teamsRoot(), queryKeys.attemptsRoot()],
  // A grade moves balances. Frozen players keep their snapshot; organisers
  // still need the live list.
  'board.graded': () => {
    const keys: QueryKey[] = [queryKeys.teamsRoot(), queryKeys.balanceEventsRoot()]
    if (!viewerSeesFrozenLeaderboard()) keys.push(queryKeys.leaderboardRoot())
    return keys
  },
  'question.assigned': () => [queryKeys.attemptsRoot()],
  'mentor.submission.created': () => [queryKeys.submissions()],
  // Freeze (or thaw) rides on this frame; competing teams must re-read ranks.
  'game.state': () => [
    queryKeys.gameState(),
    queryKeys.gameSettings(),
    queryKeys.leaderboardRoot(),
  ],
  // The frame is a hint, as ever: the inbox itself is refetched, and
  // useNotifications decides whether that counts as news worth a toast.
  'notification.created': () => [queryKeys.inbox()],
  // A Designer repainted something; every open map is stale.
  'map.design': () => [queryKeys.mapDesignRoot()],
  // A won Minesweeper toll expands reach; holdings themselves did not change.
  'minesweeper.cleared': () => BOARD,
  // Addressed to the two teams and the judge only — see `game.sse._visible_to`.
  // A resolved duel also emits the public board frames above, so this one only
  // has to refresh the duel page itself.
  'duel.updated': () => [queryKeys.duelsRoot()],
}

const RESYNC_KEYS: QueryKey[] = [
  queryKeys.teamsRoot(),
  queryKeys.leaderboardRoot(),
  queryKeys.submissions(),
  queryKeys.gameState(),
  queryKeys.attemptsRoot(),
  queryKeys.inbox(),
  queryKeys.mapDesignRoot(),
  queryKeys.duelsRoot(),
]

function createBoardStream() {
  const pending = new Map<string, QueryKey>()
  let timer: ReturnType<typeof setTimeout> | null = null
  let lastFlush = 0
  let close: (() => void) | null = null

  function invalidate(keys: QueryKey[]) {
    for (const queryKey of keys) {
      queryClient.invalidateQueries({ queryKey })
    }
  }

  function flush() {
    timer = null
    lastFlush = Date.now()
    const keys = [...pending.values()]
    pending.clear()
    invalidate(keys)
  }

  function schedule(keys: QueryKey[]) {
    for (const key of keys) {
      pending.set(key.join('/'), key)
    }
    if (timer !== null) return
    const wait = Math.max(0, MIN_INTERVAL_MS - (Date.now() - lastFlush)) + Math.random() * JITTER_MS
    timer = setTimeout(flush, wait)
  }

  function onEvent(eventType: string) {
    if (eventType === 'resync') {
      pending.clear()
      if (timer !== null) {
        clearTimeout(timer)
        timer = null
      }
      lastFlush = Date.now()
      invalidate(RESYNC_KEYS)
      return
    }
    const route = ROUTES[eventType]
    if (route) schedule(route())
  }

  function start() {
    if (close !== null) return
    close = openBoardStream({
      onEvent,
      onOpen: () => {
        streamConnected.value = true
      },
      onError: () => {
        streamConnected.value = false
      },
    })
  }

  function stop() {
    close?.()
    close = null
    streamConnected.value = false
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
    pending.clear()
  }

  return { connected: readonly(streamConnected), start, stop }
}

let singleton: ReturnType<typeof createBoardStream> | null = null

export function useBoardStream() {
  singleton ??= createBoardStream()
  return singleton
}
