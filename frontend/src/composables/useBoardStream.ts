import { readonly } from 'vue'
import { openBoardStream } from '@/lib/eventSource'
import { streamConnected } from '@/lib/boardStreamState'
import { queryClient } from '@/lib/queryClient'
import { queryKeys } from '@/queries/keys'
import type { GameState, Me } from '@/types/api'

const MIN_INTERVAL_MS = 1800
const JITTER_MS = 600

const HEARTBEAT = 'heartbeat'
const RESYNC = 'resync'

// The server sends a heartbeat every SSE_HEARTBEAT_SECONDS (15s). Silence for
// much longer than that means the connection is half-open — a state the browser
// does not report, because from its side the socket is still established.
const STALE_MS = 40_000
const WATCHDOG_MS = 5_000
const REOPEN_BASE_MS = 2_000
const REOPEN_MAX_MS = 30_000
// Wide on purpose: a restart fails every client's stream at the same instant,
// so the jitter is what stops the whole hall reconnecting in one burst.
const REOPEN_JITTER_MS = 5_000

type QueryKey = readonly unknown[]

function viewerSeesFrozenLeaderboard(): boolean {
  const me = queryClient.getQueryData<Me | null>(queryKeys.me())
  const state = queryClient.getQueryData<GameState>(queryKeys.gameState())
  return me?.team != null && state?.leaderboard_frozen === true
}

const BOARD = [queryKeys.teamsRoot()]
// Who owns which floor next door decides what is for sale, so every frame that
// moves a seat or a grade also stales the buyout table.
const BOARD_AND_BUYOUTS = [queryKeys.teamsRoot(), queryKeys.buyoutsRoot()]
const ROUTES: Record<string, () => QueryKey[]> = {
  'board.spawn.claimed': () => BOARD,
  'board.node.claimed': () => [...BOARD_AND_BUYOUTS, queryKeys.balanceEventsRoot()],
  'board.released': () => [...BOARD_AND_BUYOUTS, queryKeys.attemptsRoot()],
  'board.gelled': () => [...BOARD_AND_BUYOUTS, queryKeys.attemptsRoot(), queryKeys.mapDesignRoot()],
  // A grade moves balances. Frozen players keep their snapshot; organisers
  // still need the live list.
  'board.graded': () => {
    const keys: QueryKey[] = [...BOARD_AND_BUYOUTS, queryKeys.balanceEventsRoot()]
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
  'minesweeper.cleared': () => BOARD_AND_BUYOUTS,
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
  queryKeys.buyoutsRoot(),
]

// Subscribed types are derived from the routing table rather than listed a
// second time: an event with no `addEventListener` never fires, so a list that
// drifts from ROUTES drops those frames silently.
const STREAM_EVENTS = [...Object.keys(ROUTES), RESYNC, HEARTBEAT]

function createBoardStream() {
  const pending = new Map<string, QueryKey>()
  let timer: ReturnType<typeof setTimeout> | null = null
  let lastFlush = 0
  let close: (() => void) | null = null
  let running = false
  let watchdog: ReturnType<typeof setInterval> | null = null
  let reopenTimer: ReturnType<typeof setTimeout> | null = null
  let attempt = 0
  let lastSeenAt = 0

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
    // Any frame proves the stream is alive, the heartbeat included — it carries
    // no route and exists only to say so.
    lastSeenAt = Date.now()
    streamConnected.value = true
    if (eventType === HEARTBEAT) return

    if (eventType === RESYNC) {
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

  function open() {
    lastSeenAt = Date.now()
    close = openBoardStream({
      events: STREAM_EVENTS,
      onEvent,
      onOpen: () => {
        attempt = 0
        lastSeenAt = Date.now()
        streamConnected.value = true
      },
      onError: (closed) => {
        streamConnected.value = false
        if (closed) reopen()
      },
    })
  }

  function reopen() {
    if (!running || reopenTimer !== null) return
    close?.()
    close = null
    const wait =
      Math.min(REOPEN_MAX_MS, REOPEN_BASE_MS * 2 ** attempt) + Math.random() * REOPEN_JITTER_MS
    attempt += 1
    reopenTimer = setTimeout(() => {
      reopenTimer = null
      open()
    }, wait)
  }

  function checkLiveness() {
    if (!running || close === null || reopenTimer !== null) return
    if (Date.now() - lastSeenAt <= STALE_MS) return
    streamConnected.value = false
    attempt = 0
    reopen()
  }

  function start() {
    if (running) return
    running = true
    open()
    watchdog = setInterval(checkLiveness, WATCHDOG_MS)
    // Timers do not run while the device sleeps, so a tab coming back to the
    // foreground is checked at once rather than on the next tick.
    document.addEventListener('visibilitychange', onVisibility)
  }

  function onVisibility() {
    if (document.visibilityState === 'visible') checkLiveness()
  }

  function stop() {
    running = false
    document.removeEventListener('visibilitychange', onVisibility)
    if (watchdog !== null) {
      clearInterval(watchdog)
      watchdog = null
    }
    if (reopenTimer !== null) {
      clearTimeout(reopenTimer)
      reopenTimer = null
    }
    attempt = 0
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
