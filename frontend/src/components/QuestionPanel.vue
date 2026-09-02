<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import QuestionAttemptCard from '@/components/QuestionAttemptCard.vue'
import { useAttempts } from '@/composables/useAttempts'
import { formatDuration } from '@/lib/format'
import type { ActiveAttempt, AttemptStatus } from '@/types/api'

const { questionAttempts, selected, loading, error, select } = useAttempts()

const STATUS_LABEL: Record<AttemptStatus, string> = {
  no_question: 'بدون سؤال',
  open: 'در انتظار پاسخ',
  answered: 'منتظر نمره',
  expired: 'زمان تمام شد',
  graded: 'نمره‌دهی شد',
}

function statusLabel(attempt: ActiveAttempt): string {
  return STATUS_LABEL[attempt.status]
}

function isSelected(attempt: ActiveAttempt): boolean {
  return selected.value?.id === attempt.id
}

const hasAttempts = computed(() => questionAttempts.value.length > 0)
</script>

<template>
  <section class="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden border-b pb-4">
    <header>
      <h2 class="text-sm font-semibold">سؤال‌های باز</h2>
      <p class="text-muted-foreground mt-0.5 text-xs">
        سؤال‌های فعال تیم شما با زمان باقی‌مانده
      </p>
    </header>

    <p v-if="error" class="text-destructive text-sm">{{ error }}</p>

    <div v-if="loading" class="flex flex-col gap-2">
      <Skeleton class="h-10 w-full" />
      <Skeleton class="h-10 w-full" />
      <Skeleton class="h-32 w-full" />
    </div>

    <p v-else-if="!hasAttempts" class="text-muted-foreground text-sm">
      سؤال بازی ندارید. از نقشه یک خانه رزرو کنید.
    </p>

    <template v-else>
      <ul class="flex max-h-36 shrink-0 flex-col gap-1.5 overflow-y-auto">
        <li v-for="attempt in questionAttempts" :key="attempt.id">
          <Button
            class="h-auto w-full items-start justify-between py-2.5 whitespace-normal"
            :variant="isSelected(attempt) ? 'default' : 'outline'"
            @click="select(attempt.id)"
          >
            <span class="flex min-w-0 flex-col items-start gap-0.5 text-start">
              <span class="text-sm font-medium">{{ attempt.node_name }}</span>
              <span class="text-xs opacity-80">{{ attempt.node_code }}</span>
            </span>
            <span class="flex shrink-0 flex-col items-end gap-1">
              <Badge variant="secondary" class="font-normal">
                {{ statusLabel(attempt) }}
              </Badge>
              <Badge
                v-if="attempt.status === 'open' && attempt.remaining_seconds > 0"
                variant="outline"
                class="tabular-nums font-normal"
              >
                {{ formatDuration(attempt.remaining_seconds) }}
              </Badge>
            </span>
          </Button>
        </li>
      </ul>

      <div class="min-h-0 flex-1 overflow-y-auto">
        <QuestionAttemptCard v-if="selected" :attempt="selected" />
      </div>
    </template>
  </section>
</template>
