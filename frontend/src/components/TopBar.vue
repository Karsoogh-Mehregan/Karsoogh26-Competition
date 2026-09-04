<script setup lang="ts">
import { PauseIcon, SettingsIcon } from '@lucide/vue'
import { computed, ref } from 'vue'
import AdminDialog from '@/components/AdminDialog.vue'
import AppNav from '@/components/AppNav.vue'
import NotificationBell from '@/components/NotificationBell.vue'
import { Button } from '@/components/ui/button'
import { useActing } from '@/composables/useActing'
import { formatClock, useGameClock } from '@/composables/useGameClock'

const { me, isGameGod } = useActing()
const { status, isRunning, elapsedSeconds, remainingSeconds, isOvertime, isEndingSoon } =
  useGameClock()

const adminOpen = ref(false)

const STATUS_TONE: Record<string, string> = {
  running: 'is-running',
  paused: 'is-paused',
  finished: 'is-finished',
  not_started: 'is-idle',
}
const statusTone = computed(() => STATUS_TONE[status.value] ?? 'is-idle')

const elapsedLabel = computed(() =>
  elapsedSeconds.value === null ? '—' : formatClock(elapsedSeconds.value),
)
const remainingLabel = computed(() => {
  if (remainingSeconds.value === null) return null
  return isOvertime.value ? 'پایان' : formatClock(remainingSeconds.value)
})
</script>

<template>
  <header v-if="me" class="topbar" dir="rtl">
    <AppNav />

    <div class="timers" :class="{ 'is-frozen': !isRunning }">
      <span class="status-dot" :class="statusTone" aria-hidden="true" />
      <div class="timer">
        <span class="timer-label">زمان بازی</span>
        <span class="timer-value tabular-nums">{{ elapsedLabel }}</span>
      </div>
      <span v-if="remainingLabel" class="timer-sep" aria-hidden="true" />
      <div
        v-if="remainingLabel"
        class="timer"
        :class="{ 'is-urgent': isEndingSoon || isOvertime }"
      >
        <span class="timer-label">تا پایان</span>
        <span class="timer-value tabular-nums">{{ remainingLabel }}</span>
      </div>
      <span v-if="!isRunning" class="timer-frozen">
        <PauseIcon class="size-3" aria-hidden="true" />
        متوقف
      </span>
    </div>

    <NotificationBell />

    <Button
      v-if="isGameGod"
      variant="outline"
      size="sm"
      class="admin-button"
      @click="adminOpen = true"
    >
      <SettingsIcon class="size-4" />
      <span class="admin-label">کنترل بازی</span>
    </Button>

    <AdminDialog v-if="isGameGod" v-model:open="adminOpen" />
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: 0.75rem 1.25rem;
  flex-wrap: wrap;
  padding: 0.55rem 1rem;
  border-block-end: 1px solid var(--border);
  background: var(--card);
}

.status-dot {
  width: 0.5rem;
  height: 0.5rem;
  flex-shrink: 0;
  border-radius: 9999px;
  background: var(--muted-foreground);
}
.status-dot.is-running {
  background: #10b981;
  box-shadow: 0 0 0 3px color-mix(in oklab, #10b981 22%, transparent);
}
.status-dot.is-paused {
  background: #f59e0b;
}
.status-dot.is-finished {
  background: #64748b;
}

.timers {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  margin-inline-start: auto;
  padding: 0.25rem 0.7rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--background);
  transition: opacity 0.2s ease;
}
.timers.is-frozen {
  opacity: 0.72;
}
.timer {
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 1.15;
}
.timer-label {
  font-size: 0.625rem;
  font-weight: 600;
  color: var(--muted-foreground);
}
.timer-value {
  font-size: 1.0625rem;
  font-weight: 700;
  letter-spacing: 0.01em;
}
.timer.is-urgent .timer-value,
.timer.is-urgent .timer-label {
  color: var(--destructive);
}
.timer-sep {
  width: 1px;
  align-self: stretch;
  margin-block: 0.15rem;
  background: var(--border);
}
.timer-frozen {
  display: flex;
  align-items: center;
  gap: 0.2rem;
  font-size: 0.625rem;
  font-weight: 600;
  color: var(--muted-foreground);
}

.admin-button {
  flex-shrink: 0;
}

@media (max-width: 860px) {
  .timers {
    order: 2;
  }
}

@media (max-width: 520px) {
  .admin-label {
    display: none;
  }
}
</style>
