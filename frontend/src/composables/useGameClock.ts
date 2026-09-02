/**
 * The two timers the whole hall agrees on.
 *
 * Two things this deliberately does not do:
 *
 * 1. It does not trust `Date.now()` on its own. Laptops in a contest hall
 *    disagree about the time, sometimes by hours, so every response carries the
 *    server's `server_time`, we keep the difference, and everything is derived
 *    from `Date.now() + offset`.
 * 2. It does not measure wall time since kick-off. Elapsed is *running* time:
 *    the server banks each running stretch into `accumulated_seconds` and only
 *    sets `running_since` while the game is actually running. Pausing therefore
 *    freezes both timers here with no extra logic, and a restart zeroes them.
 */
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useMeQuery } from '@/queries/auth'
import { useGameStateQuery } from '@/queries/gameState'
import type { GameState } from '@/types/api'

const TICK_MS = 1000

/** Offset in ms to add to the local clock to get the server's. */
const offset = ref(0)
const now = ref(Date.now())

let tickers = 0
let timer: ReturnType<typeof setInterval> | null = null

function startTicking() {
  tickers += 1
  if (timer !== null) return
  timer = setInterval(() => {
    now.value = Date.now()
  }, TICK_MS)
}

function stopTicking() {
  tickers = Math.max(0, tickers - 1)
  if (tickers === 0 && timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

/** `H:MM:SS`, or `MM:SS` under an hour. */
export function formatClock(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds))
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = seconds % 60
  const mm = String(minutes).padStart(2, '0')
  const ss = String(rest).padStart(2, '0')
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`
}

export function useGameClock() {
  const meQuery = useMeQuery()
  const isAuthenticated = () => meQuery.data.value != null
  const stateQuery = useGameStateQuery(isAuthenticated)

  startTicking()
  onScopeDispose(stopTicking)

  // Re-anchor on every fetch: corrects drift and any clock the user changes.
  watch(
    () => stateQuery.data.value?.server_time,
    (serverTime) => {
      if (!serverTime) return
      const parsed = Date.parse(serverTime)
      if (Number.isNaN(parsed)) return
      offset.value = parsed - Date.now()
      now.value = Date.now()
    },
    { immediate: true },
  )

  const state = computed<GameState | null>(() => stateQuery.data.value ?? null)
  const serverNow = computed(() => now.value + offset.value)

  const isRunning = computed(() => state.value?.is_running ?? false)
  const status = computed(() => state.value?.status ?? 'not_started')
  const hasStarted = computed(() => state.value?.started_at != null)

  /**
   * Running seconds so far. The live stretch is only added while the game is
   * running, so this stops on its own the moment an admin pauses.
   */
  const elapsedSeconds = computed<number | null>(() => {
    const current = state.value
    if (!current || current.started_at === null) return null

    let total = current.accumulated_seconds
    if (current.is_running && current.running_since) {
      const since = Date.parse(current.running_since)
      if (!Number.isNaN(since)) {
        total += Math.max(0, Math.round((serverNow.value - since) / 1000))
      }
    }
    return total
  })

  /** Time left of the allotted duration, or null when no limit is set. */
  const remainingSeconds = computed<number | null>(() => {
    const total = state.value?.duration_seconds ?? 0
    if (total === 0) return null
    return Math.max(0, total - (elapsedSeconds.value ?? 0))
  })

  const isOvertime = computed(() => remainingSeconds.value === 0)
  const isEndingSoon = computed(
    () =>
      isRunning.value &&
      remainingSeconds.value !== null &&
      remainingSeconds.value > 0 &&
      remainingSeconds.value <= 300,
  )

  return {
    state,
    status,
    isRunning,
    hasStarted,
    loading: computed(() => stateQuery.isPending.value),
    elapsedSeconds,
    remainingSeconds,
    isOvertime,
    isEndingSoon,
  }
}
