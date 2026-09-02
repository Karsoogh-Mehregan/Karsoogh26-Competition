const numberFormatter = new Intl.NumberFormat('fa-IR')

export function formatBalance(value: number | null | undefined): string {
  if (value == null) return '—'
  return numberFormatter.format(value)
}

export function formatSignedBalance(delta: number): string {
  const formatted = formatBalance(Math.abs(delta))
  if (delta > 0) return `+${formatted}`
  if (delta < 0) return `−${formatted}`
  return formatted
}

export function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds))
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}
