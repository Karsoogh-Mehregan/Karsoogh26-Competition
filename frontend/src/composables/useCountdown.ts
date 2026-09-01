import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'

export function useCountdown(secondsSource: Ref<number | undefined | null>) {
  const remaining = ref(0)
  let timer: ReturnType<typeof setInterval> | null = null

  function stopTimer() {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  watch(
    secondsSource,
    (seconds) => {
      stopTimer()
      if (seconds == null) {
        remaining.value = 0
        return
      }
      remaining.value = seconds
      timer = setInterval(() => {
        remaining.value = Math.max(0, remaining.value - 1)
        if (remaining.value === 0) stopTimer()
      }, 1000)
    },
    { immediate: true },
  )

  onBeforeUnmount(stopTimer)

  const expired = computed(() => remaining.value <= 0 && secondsSource.value != null)
  const urgent = computed(() => !expired.value && remaining.value <= 60)

  const timerClass = computed(() => {
    if (expired.value) return 'bg-destructive text-white border-transparent'
    if (urgent.value) return 'bg-destructive/10 text-destructive border-destructive/30'
    return 'bg-muted text-muted-foreground border-transparent'
  })

  return { remaining, expired, urgent, timerClass }
}
