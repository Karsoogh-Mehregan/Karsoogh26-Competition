import { ref } from 'vue'

// Transport-level, like http.ts's module-scoped csrfToken. Queries import this
// to fall back to polling while the stream is down; importing the composable
// instead would invert the layering.
export const streamConnected = ref(false)

/**
 * The last «وقت اضافه» announcement off the stream, or null before the first.
 *
 * A fresh object every time, never a count or a boolean: two grants of the same
 * ten minutes must both raise a toast, and identity is what makes the watcher
 * fire on the second one.
 *
 * It lives here beside `streamConnected` for the same layering reason — the
 * transport writes it, a composable reads it, and neither imports the other.
 */
export interface TimeExtensionFrame {
  minutes: number
  durationMinutes: number
  resumed: boolean
}

export const lastTimeExtension = ref<TimeExtensionFrame | null>(null)

/**
 * Mute the next extension toast on *this* client for a few seconds.
 *
 * The organiser who pressed the button gets the mutation's own toast, and their
 * frame comes back to them on the stream like everyone else's. Excluding the
 * author from their own fan-out is the rule the notifications app applies at
 * send time; a stream frame cannot be addressed that way, so it is dropped on
 * receipt instead. Per-client, not per-role — a second game god still sees it.
 *
 * Here rather than in the composable so `queries/` can set it without importing
 * upward through the layering.
 */
const SUPPRESS_MS = 5_000
let suppressUntil = 0

export function suppressNextTimeExtensionToast(): void {
  suppressUntil = Date.now() + SUPPRESS_MS
}

/** True once, and only while the mute is still fresh. */
export function consumeTimeExtensionSuppression(): boolean {
  if (Date.now() >= suppressUntil) return false
  suppressUntil = 0
  return true
}
