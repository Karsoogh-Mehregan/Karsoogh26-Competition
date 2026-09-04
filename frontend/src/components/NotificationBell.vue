<script setup lang="ts">
/**
 * The bell in the top bar, and the red dot that is the whole point of it.
 *
 * Carries no state of its own: the count comes from the same query the panel
 * renders, so the dot and the list can never disagree.
 */
import { BellIcon } from '@lucide/vue'
import { computed } from 'vue'

import { Button } from '@/components/ui/button'
import { useNotifications } from '@/composables/useNotifications'

const { unread, hasUnread, toggle } = useNotifications()

// Past a point the exact number stops being information.
const badge = computed(() => (unread.value > 9 ? '۹+' : toPersian(unread.value)))

function toPersian(value: number): string {
  return String(value).replace(/\d/g, (digit) => '۰۱۲۳۴۵۶۷۸۹'[Number(digit)])
}

const label = computed(() =>
  hasUnread.value ? `پیام‌ها — ${unread.value} پیام خوانده‌نشده` : 'پیام‌ها',
)
</script>

<template>
  <Button
    variant="outline"
    size="icon"
    class="bell"
    :aria-label="label"
    :title="label"
    @click="toggle"
  >
    <BellIcon class="size-4" :class="{ 'bell-ring': hasUnread }" />
    <!-- aria-hidden: the count is already in the button's label, and a screen
         reader announcing it twice is worse than not seeing the dot. -->
    <span v-if="hasUnread" class="bell-dot" aria-hidden="true">{{ badge }}</span>
  </Button>
</template>

<style scoped>
.bell {
  position: relative;
  flex-shrink: 0;
}

.bell-dot {
  position: absolute;
  inset-block-start: -0.3rem;
  inset-inline-end: -0.3rem;
  display: grid;
  place-items: center;
  min-inline-size: 1.05rem;
  block-size: 1.05rem;
  padding-inline: 0.2rem;
  border-radius: 9999px;
  background: var(--destructive);
  color: #fff;
  font-size: 0.625rem;
  font-weight: 700;
  line-height: 1;
  box-shadow: 0 0 0 2px var(--card);
}

/* One nudge on arrival, not a standing animation — a bell that never stops
   moving is a bell people stop looking at. */
.bell-ring {
  animation: bell-nudge 1.1s ease-in-out 1;
  transform-origin: 50% 15%;
}

@keyframes bell-nudge {
  0%,
  100% {
    transform: rotate(0deg);
  }
  15% {
    transform: rotate(11deg);
  }
  30% {
    transform: rotate(-9deg);
  }
  45% {
    transform: rotate(6deg);
  }
  60% {
    transform: rotate(-4deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .bell-ring {
    animation: none;
  }
}
</style>
