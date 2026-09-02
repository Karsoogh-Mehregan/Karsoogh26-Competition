<script setup lang="ts">
import { computed } from 'vue'
import QuestionAttemptCard from '@/components/QuestionAttemptCard.vue'
import { Skeleton } from '@/components/ui/skeleton'
import { useAttempts } from '@/composables/useAttempts'

const { questionAttempts, loading, error } = useAttempts()

const hasAttempts = computed(() => questionAttempts.value.length > 0)
</script>

<template>
  <div class="h-full overflow-y-auto p-6">
    <div class="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <header>
        <h1 class="text-lg font-bold">حل سؤال</h1>
        <p class="text-muted-foreground mt-1 text-sm">
          سؤال‌های رزروشدهٔ تیم شما. مهلت ارسال روی هر سؤال شمارش معکوس می‌شود.
        </p>
      </header>

      <p v-if="error" class="text-destructive text-sm">{{ error }}</p>

      <div v-if="loading" class="flex flex-col gap-3">
        <Skeleton class="h-48 w-full" />
        <Skeleton class="h-48 w-full" />
      </div>

      <p v-else-if="!hasAttempts" class="text-muted-foreground text-sm">
        سؤال بازی ندارید. از نقشه یک خانه رزرو کنید.
      </p>

      <div v-else class="flex flex-col gap-4">
        <QuestionAttemptCard
          v-for="attempt in questionAttempts"
          :key="attempt.id"
          :attempt="attempt"
        />
      </div>
    </div>
  </div>
</template>
