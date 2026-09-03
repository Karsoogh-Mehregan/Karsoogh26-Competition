const numberFormatter = new Intl.NumberFormat('fa-IR')

export function formatBalance(value: number | null | undefined): string {
  if (value == null) return '—'
  return numberFormatter.format(value)
}

export function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds))
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

export function formatSignedBalance(value: number): string {
  const formatted = numberFormatter.format(Math.abs(value))
  if (value > 0) return `+${formatted}`
  if (value < 0) return `−${formatted}`
  return formatted
}

const relativeFormatter = new Intl.RelativeTimeFormat('fa-IR', { numeric: 'auto' })

const RELATIVE_STEPS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['second', 60],
  ['minute', 60],
  ['hour', 24],
  ['day', 7],
  ['week', 4.35],
  ['month', 12],
]

/**
 * "۳ دقیقه پیش". Coarsens as it ages, the way a mail client does.
 *
 * Anything within the last few seconds reads as "الان": a card that appears
 * saying "0 seconds ago" looks broken, and the exact second is never the point.
 */
export function formatRelativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'

  let delta = (then - now) / 1000
  if (Math.abs(delta) < 45) return 'همین حالا'

  for (const [unit, span] of RELATIVE_STEPS) {
    if (Math.abs(delta) < span) {
      return relativeFormatter.format(Math.round(delta), unit)
    }
    delta /= span
  }
  return relativeFormatter.format(Math.round(delta), 'year')
}
