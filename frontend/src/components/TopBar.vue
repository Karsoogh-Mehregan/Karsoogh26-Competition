<script setup lang="ts">
import { CheckIcon, PauseIcon, SettingsIcon } from '@lucide/vue'
import { computed, ref } from 'vue'
import AdminDialog from '@/components/AdminDialog.vue'
import { Button } from '@/components/ui/button'
import { useActing } from '@/composables/useActing'
import { formatClock, useGameClock } from '@/composables/useGameClock'
import { useStage } from '@/composables/useStage'

const { me, isGameGod } = useActing()
const { state, status, isRunning, elapsedSeconds, remainingSeconds, isOvertime, isEndingSoon } =
  useGameClock()
const { title, hint, stepIndex, onPath, steps } = useStage()

const adminOpen = ref(false)

// The status dot carries the game state on its own, so the timers do not have
// to explain themselves twice.
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

function stepState(index: number): 'done' | 'current' | 'todo' {
  if (!onPath.value) return 'todo'
  if (index < stepIndex.value) return 'done'
  if (index === stepIndex.value) return 'current'
  return 'todo'
}
</script>

<template>
  <header v-if="me" class="topbar" dir="rtl">
    <!-- Where this player is right now -->
    <div class="stage">
      <div class="stage-head">
        <span class="status-dot" :class="statusTone" aria-hidden="true" />
        <span class="stage-title">{{ title }}</span>
        <span class="stage-status" :class="statusTone">{{ state?.status_display ?? '—' }}</span>
      </div>
      <p class="stage-hint">{{ hint }}</p>
    </div>

    <ol v-if="onPath" class="steps" :aria-label="`مرحلهٔ فعلی: ${title}`">
      <li
        v-for="(step, index) in steps"
        :key="step.key"
        class="step"
        :class="`is-${stepState(index)}`"
        :aria-current="stepState(index) === 'current' ? 'step' : undefined"
      >
        <span class="step-dot">
          <CheckIcon v-if="stepState(index) === 'done'" class="size-2.5" />
          <span v-else class="step-num">{{ index + 1 }}</span>
        </span>
        <span class="step-label">{{ step.label }}</span>
      </li>
    </ol>

    <!-- Timers. Labelled, because two bare numbers side by side mean nothing. -->
    <div class="timers" :class="{ 'is-frozen': !isRunning }">
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

/* ---- stage ---- */
.stage {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.1rem;
}
.stage-head {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}
.stage-title {
  font-size: 0.9375rem;
  font-weight: 700;
  white-space: nowrap;
}
.stage-status {
  font-size: 0.6875rem;
  font-weight: 600;
  white-space: nowrap;
}
.stage-hint {
  margin: 0;
  color: var(--muted-foreground);
  font-size: 0.75rem;
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
.stage-status.is-running {
  color: #047857;
}
.stage-status.is-paused {
  color: #b45309;
}
.stage-status.is-finished,
.stage-status.is-idle {
  color: var(--muted-foreground);
}

/* ---- steps ---- */
.steps {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
  min-width: 0;
  overflow-x: auto;
}
.step {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  white-space: nowrap;
  font-size: 0.75rem;
  color: var(--muted-foreground);
}
.step-dot {
  display: grid;
  place-items: center;
  width: 1.15rem;
  height: 1.15rem;
  flex-shrink: 0;
  border-radius: 9999px;
  border: 1px solid var(--border);
  background: var(--background);
  font-size: 0.625rem;
  font-weight: 700;
  line-height: 1;
}
.step-num {
  color: var(--muted-foreground);
}
.step.is-done {
  color: var(--foreground);
}
.step.is-done .step-dot {
  border-color: transparent;
  background: #10b981;
  color: #fff;
}
.step.is-current {
  color: var(--foreground);
  font-weight: 700;
}
.step.is-current .step-dot {
  border-color: var(--primary);
  background: var(--primary);
  color: var(--primary-foreground);
}
.step.is-current .step-num {
  color: inherit;
}

/* ---- timers ---- */
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

@media (max-width: 1100px) {
  .stage-hint {
    display: none;
  }
}

@media (max-width: 860px) {
  .steps {
    order: 3;
    width: 100%;
    gap: 0.6rem;
  }
  .timers {
    order: 2;
  }
}

@media (max-width: 520px) {
  .steps {
    display: none;
  }
  .admin-label {
    display: none;
  }
}
</style>
