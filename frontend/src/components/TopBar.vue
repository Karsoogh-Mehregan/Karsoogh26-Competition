<script setup lang="ts">
import { CheckIcon, ClockIcon, HourglassIcon, SettingsIcon, TimerIcon } from '@lucide/vue'
import { computed, ref } from 'vue'
import AdminDialog from '@/components/AdminDialog.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useActing } from '@/composables/useActing'
import { formatClock, useGameClock } from '@/composables/useGameClock'
import { useStage } from '@/composables/useStage'

const { me, isMentor } = useActing()
const { state, clockLabel, elapsedSeconds, remainingSeconds, isOvertime, isEndingSoon } =
  useGameClock()
const { title, hint, stepIndex, onPath, steps } = useStage()

const adminOpen = ref(false)

const STATUS_VARIANT: Record<string, string> = {
  running: 'border-transparent bg-emerald-500 text-white',
  paused: 'border-transparent bg-amber-500 text-amber-950',
  finished: 'border-transparent bg-slate-500 text-white',
  not_started: '',
}

const statusClass = computed(() => STATUS_VARIANT[state.value?.status ?? 'not_started'] ?? '')

const remainingClass = computed(() => {
  if (isOvertime.value) return 'text-destructive'
  if (isEndingSoon.value) return 'text-destructive'
  return ''
})

function stepState(index: number): 'done' | 'current' | 'todo' {
  if (!onPath.value) return 'todo'
  if (index < stepIndex.value) return 'done'
  if (index === stepIndex.value) return 'current'
  return 'todo'
}
</script>

<template>
  <header v-if="me" class="topbar glass-panel" dir="rtl">
    <!-- Stage: where this player is right now -->
    <div class="topbar-stage">
      <div class="topbar-stage-head">
        <span class="topbar-title">{{ title }}</span>
        <Badge v-if="state" :class="statusClass" class="shrink-0">
          {{ state.status_display }}
        </Badge>
      </div>
      <p class="topbar-hint">{{ hint }}</p>

      <ol v-if="onPath" class="topbar-steps" :aria-label="`مرحلهٔ فعلی: ${title}`">
        <li
          v-for="(step, index) in steps"
          :key="step.key"
          class="topbar-step"
          :class="`is-${stepState(index)}`"
          :aria-current="stepState(index) === 'current' ? 'step' : undefined"
        >
          <span class="topbar-step-dot">
            <CheckIcon v-if="stepState(index) === 'done'" class="size-2.5" />
          </span>
          <span class="topbar-step-label">{{ step.label }}</span>
        </li>
      </ol>
    </div>

    <!-- Clock: one time for the whole hall, taken from the server -->
    <div class="topbar-clock" role="group" aria-label="زمان">
      <div class="topbar-time">
        <ClockIcon class="size-4 shrink-0" aria-hidden="true" />
        <span class="topbar-time-value tabular-nums">{{ clockLabel }}</span>
      </div>
      <div class="topbar-timers">
        <span v-if="elapsedSeconds !== null" class="topbar-timer" title="زمان سپری‌شده">
          <TimerIcon class="size-3.5 shrink-0" aria-hidden="true" />
          <span class="tabular-nums">{{ formatClock(elapsedSeconds) }}</span>
        </span>
        <span
          v-if="remainingSeconds !== null"
          class="topbar-timer"
          :class="remainingClass"
          title="زمان باقی‌مانده"
        >
          <HourglassIcon class="size-3.5 shrink-0" aria-hidden="true" />
          <span class="tabular-nums">
            {{ isOvertime ? 'پایان زمان' : formatClock(remainingSeconds) }}
          </span>
        </span>
      </div>
    </div>

    <!-- Admin: mentors only -->
    <Button
      v-if="isMentor"
      variant="outline"
      size="sm"
      class="topbar-admin"
      @click="adminOpen = true"
    >
      <SettingsIcon class="size-4" />
      کنترل بازی
    </Button>

    <AdminDialog v-if="isMentor" v-model:open="adminOpen" />
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  padding: 0.5rem 1rem;
  border-radius: 0;
  border-inline: 0;
  border-block-start: 0;
}

.topbar-stage {
  display: flex;
  min-width: 0;
  flex: 1 1 16rem;
  flex-direction: column;
  gap: 0.15rem;
}
.topbar-stage-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.topbar-title {
  font-size: 0.9375rem;
  font-weight: 700;
}
.topbar-hint {
  margin: 0;
  color: var(--muted-foreground);
  font-size: 0.75rem;
}

.topbar-steps {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
  margin: 0.3rem 0 0;
  padding: 0;
  list-style: none;
}
.topbar-step {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.6875rem;
  color: var(--muted-foreground);
}
.topbar-step-dot {
  display: grid;
  place-items: center;
  width: 0.9rem;
  height: 0.9rem;
  border-radius: 9999px;
  border: 1px solid var(--border);
  background: var(--background);
  color: #fff;
}
.topbar-step.is-done {
  color: var(--foreground);
}
.topbar-step.is-done .topbar-step-dot {
  border-color: transparent;
  background: var(--color-emerald-500, #10b981);
}
.topbar-step.is-current {
  color: var(--foreground);
  font-weight: 700;
}
.topbar-step.is-current .topbar-step-dot {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px color-mix(in oklab, var(--primary) 22%, transparent);
}

.topbar-clock {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding-inline: 0.75rem;
  border-inline: 1px solid color-mix(in oklab, var(--foreground) 10%, transparent);
}
.topbar-time {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--muted-foreground);
}
.topbar-time-value {
  font-size: 1.0625rem;
  font-weight: 700;
  color: var(--foreground);
  letter-spacing: 0.01em;
}
.topbar-timers {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}
.topbar-timer {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.75rem;
  color: var(--muted-foreground);
}

.topbar-admin {
  flex-shrink: 0;
}

/* Shed the prose first, the steps only when there is really no room: the
   stage is the reason this bar exists. */
@media (max-width: 900px) {
  .topbar {
    gap: 0.5rem 0.75rem;
  }
  .topbar-hint {
    display: none;
  }
  .topbar-clock {
    border-inline: 0;
    padding-inline: 0;
  }
}

@media (max-width: 620px) {
  .topbar-steps {
    display: none;
  }
  .topbar-admin span {
    display: none;
  }
}
</style>
