import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'

function secondsUntil(iso: string | null | undefined): number {
  if (!iso) return 0
  const end = Date.parse(iso)
  if (Number.isNaN(end)) return 0
  return Math.max(0, Math.floor((end - Date.now()) / 1000))
}

export function useCountdown(expiresAt: Ref<string | null | undefined>) {
  const remaining = ref(0)
  let timer: ReturnType<typeof setInterval> | null = null

  function stopTimer() {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  function tick() {
    remaining.value = secondsUntil(expiresAt.value)
    if (remaining.value === 0) stopTimer()
  }

  watch(
    expiresAt,
    (value) => {
      stopTimer()
      tick()
      if (!value || remaining.value === 0) return
      timer = setInterval(tick, 1000)
    },
    { immediate: true },
  )

  onBeforeUnmount(stopTimer)

  const expired = computed(() => remaining.value <= 0 && !!expiresAt.value)
  const urgent = computed(() => !expired.value && remaining.value <= 60)

  const timerClass = computed(() => {
    if (expired.value) return 'bg-destructive text-white border-transparent'
    if (urgent.value) return 'bg-destructive/10 text-destructive border-destructive/30'
    return 'bg-muted text-muted-foreground border-transparent'
  })

  return { remaining, expired, urgent, timerClass }
}
