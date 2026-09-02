/**
 * The one clock the whole hall agrees on.
 *
 * Laptops in a contest hall disagree about the time — by minutes, sometimes by
 * hours. So nothing here trusts `Date.now()` on its own: every response carries
 * the server's `server_time`, we keep the difference, and every displayed
 * number is derived from `Date.now() + offset`. A team arguing that its timer
 * ran fast is then arguing with the server, not with its own clock.
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

function secondsBetween(fromMs: number, toMs: number): number {
  return Math.max(0, Math.round((toMs - fromMs) / 1000))
}

/** `H:MM:SS`, or `MM:SS` under an hour. Latin digits; Persian is done by Intl. */
export function formatClock(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds))
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = seconds % 60
  const mm = String(minutes).padStart(2, '0')
  const ss = String(rest).padStart(2, '0')
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`
}

const timeFormatter = new Intl.DateTimeFormat('fa-IR', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
  timeZone: 'Asia/Tehran',
})

export function useGameClock() {
  const meQuery = useMeQuery()
  const isAuthenticated = () => meQuery.data.value != null
  const stateQuery = useGameStateQuery(isAuthenticated)

  startTicking()
  onScopeDispose(stopTicking)

  // Re-anchor on every fetch: this corrects drift and any clock the user
  // changes mid-contest.
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

  /** Wall-clock time in Tehran, the time on the hall's wall. */
  const clockLabel = computed(() => timeFormatter.format(new Date(serverNow.value)))

  const startedAtMs = computed(() => {
    const value = state.value?.started_at
    return value ? Date.parse(value) : null
  })
  const endsAtMs = computed(() => {
    const value = state.value?.ends_at
    return value ? Date.parse(value) : null
  })

  /** Seconds since kick-off, or null before it. */
  const elapsedSeconds = computed(() =>
    startedAtMs.value === null ? null : secondsBetween(startedAtMs.value, serverNow.value),
  )

  /** Seconds until the planned finish, or null when none is set. */
  const remainingSeconds = computed(() =>
    endsAtMs.value === null ? null : secondsBetween(serverNow.value, endsAtMs.value),
  )

  const isOvertime = computed(() => remainingSeconds.value === 0 && endsAtMs.value !== null)
  const isEndingSoon = computed(
    () => remainingSeconds.value !== null && remainingSeconds.value > 0 && remainingSeconds.value <= 300,
  )

  return {
    state,
    loading: computed(() => stateQuery.isPending.value),
    clockLabel,
    elapsedSeconds,
    remainingSeconds,
    isOvertime,
    isEndingSoon,
  }
}
