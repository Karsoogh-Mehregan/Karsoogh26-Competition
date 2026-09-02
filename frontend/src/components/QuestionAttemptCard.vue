<script setup lang="ts">
import { CircleCheckIcon, CircleXIcon, HourglassIcon, Loader2Icon, PaperclipIcon, TimerIcon } from '@lucide/vue'
import { useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { useCountdown } from '@/composables/useCountdown'
import { formatDuration } from '@/lib/format'
import { ApiError } from '@/lib/http'
import { queryKeys } from '@/queries/keys'
import { useSubmitAnswerMutation } from '@/queries/occupancies'
import type { ActiveAttempt } from '@/types/api'

const props = defineProps<{ attempt: ActiveAttempt }>()

const queryClient = useQueryClient()
const { mutateAsync: submitAnswerAsync, isPending: submitting } = useSubmitAnswerMutation()

const body = ref('')
const file = ref<File | null>(null)

const expiresAt = computed(() => props.attempt.expires_at ?? props.attempt.question?.expires_at)
const { remaining, expired, timerClass } = useCountdown(expiresAt)

watch(
  () => props.attempt.id,
  () => {
    body.value = ''
    file.value = null
  },
)

watch(expired, (isExpired) => {
  if (!isExpired) return
  if (props.attempt.status !== 'open') return
  void queryClient.invalidateQueries({ queryKey: queryKeys.attemptsRoot() })
  void queryClient.invalidateQueries({ queryKey: queryKeys.teams() })
})

const question = computed(() => props.attempt.question)
const timedOut = computed(
  () => props.attempt.status === 'expired' || (props.attempt.status === 'open' && expired.value),
)
const canAnswer = computed(
  () => props.attempt.status === 'open' && !expired.value && question.value != null,
)

const answerText = computed(() => String(body.value ?? '').trim())

const statusIcon = computed(() => {
  if (props.attempt.status === 'graded') {
    if ((props.attempt.grade ?? 0) === 0) {
      return { name: 'fail' as const, label: 'نمره صفر' }
    }
    return { name: 'pass' as const, label: 'نمره‌دهی شد' }
  }
  if (timedOut.value) {
    return { name: 'fail' as const, label: 'زمان تمام شد' }
  }
  if (props.attempt.status === 'answered') {
    return { name: 'hourglass' as const, label: 'منتظر نمره' }
  }
  if (props.attempt.status === 'open') {
    return { name: 'timer' as const, label: 'در حال پاسخ' }
  }
  return null
})

function onFileChange(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

function onBodyInput(event: Event) {
  body.value = (event.target as HTMLInputElement | HTMLTextAreaElement).value
}

const canSubmit = computed(() => {
  if (!canAnswer.value || !question.value) return false
  if (question.value.answer_type === 'file') return !!file.value
  return answerText.value !== ''
})

async function onSubmit() {
  if (!canSubmit.value || !question.value) {
    toast.error('پاسخ را وارد کنید.')
    return
  }
  try {
    await submitAnswerAsync({
      occupancyId: props.attempt.id,
      payload: {
        body: question.value.answer_type === 'file' ? undefined : answerText.value,
        file: file.value,
      },
    })
    toast.success('پاسخ ثبت شد. منتظر نمره‌دهی باشید.')
    body.value = ''
    file.value = null
  } catch (err) {
    toast.error(err instanceof ApiError ? err.detail : 'ثبت پاسخ ناموفق بود.')
  }
}
</script>

<template>
  <Card v-if="question" class="relative gap-4">
    <Badge
      v-if="attempt.status === 'open' && !timedOut"
      role="timer"
      aria-live="off"
      class="absolute top-4 start-4 z-10 tabular-nums"
      :class="timerClass"
    >
      {{ formatDuration(remaining) }}
    </Badge>

    <span
      v-if="statusIcon"
      class="absolute top-4 end-4 z-10"
      :aria-label="statusIcon.label"
      :title="statusIcon.label"
    >
      <CircleCheckIcon
        v-if="statusIcon.name === 'pass'"
        class="size-6 text-green-600"
      />
      <CircleXIcon
        v-else-if="statusIcon.name === 'fail'"
        class="size-6 text-red-600"
      />
      <TimerIcon
        v-else-if="statusIcon.name === 'timer'"
        class="size-6 text-yellow-500"
      />
      <HourglassIcon
        v-else-if="statusIcon.name === 'hourglass'"
        class="size-6 text-yellow-500"
      />
    </span>

    <CardHeader class="gap-2 pt-12">
      <CardTitle class="text-base font-bold leading-7">{{ question.title }}</CardTitle>
      <div class="flex flex-wrap items-center gap-2 text-sm">
        <span class="text-muted-foreground">{{ attempt.node_name }}</span>
        <Badge variant="outline" class="font-normal">{{ attempt.level }}</Badge>
      </div>
    </CardHeader>

    <CardContent class="flex flex-col gap-4">
      <p class="text-sm leading-7 wrap-break-word whitespace-pre-wrap">
        {{ question.body }}
      </p>

      <div v-if="question.attachment_url" class="flex flex-col gap-1.5">
        <p class="text-sm font-medium">فایل‌های مربوطه</p>
        <a
          :href="question.attachment_url"
          target="_blank"
          rel="noopener noreferrer"
          class="text-primary inline-flex items-center gap-1.5 text-sm underline-offset-4 hover:underline"
        >
          <PaperclipIcon class="size-4 shrink-0" />
          {{ question.attachment_url }}
        </a>
      </div>

      <p
        v-if="attempt.status === 'answered'"
        class="text-muted-foreground text-sm"
      >
        پاسخ ثبت شد. منتظر نمره‌دهی باشید.
      </p>

      <p
        v-else-if="attempt.status === 'graded'"
        class="text-muted-foreground text-sm"
      >
        نمره {{ attempt.grade }} ثبت شد.
      </p>

      <p
        v-else-if="timedOut"
        class="text-destructive text-sm"
        role="alert"
      >
        تایم شما تموم شد
      </p>

      <form v-else-if="canAnswer" class="flex flex-col gap-4" @submit.prevent="onSubmit">
        <div v-if="question.answer_type === 'file'" class="flex flex-col gap-1.5">
          <Label :for="`answer-file-${attempt.id}`">فایل پاسخ</Label>
          <input
            :id="`answer-file-${attempt.id}`"
            type="file"
            class="border-input file:text-foreground focus-visible:border-ring focus-visible:ring-ring/50 dark:bg-input/30 w-full cursor-pointer rounded-md border bg-transparent px-3 py-1.5 text-sm shadow-xs transition-[color,box-shadow] outline-none file:me-3 file:cursor-pointer file:border-0 file:bg-transparent file:text-sm file:font-medium focus-visible:ring-3 disabled:pointer-events-none disabled:opacity-50"
            :disabled="submitting"
            @change="onFileChange"
          >
          <p v-if="file" class="text-muted-foreground truncate text-xs">{{ file.name }}</p>
        </div>
        <div v-else-if="question.answer_type === 'numeric'" class="flex flex-col gap-1.5">
          <Label :for="`answer-numeric-${attempt.id}`">پاسخ عددی</Label>
          <input
            :id="`answer-numeric-${attempt.id}`"
            :value="body"
            type="text"
            inputmode="decimal"
            class="border-input focus-visible:border-ring focus-visible:ring-ring/50 dark:bg-input/30 h-9 w-full rounded-md border bg-transparent px-3 py-1 text-base shadow-xs outline-none focus-visible:ring-3 disabled:opacity-50 md:text-sm tabular-nums"
            :disabled="submitting"
            @input="onBodyInput"
          >
        </div>
        <div v-else class="flex flex-col gap-1.5">
          <Label :for="`answer-text-${attempt.id}`">پاسخ متنی</Label>
          <textarea
            :id="`answer-text-${attempt.id}`"
            :value="body"
            rows="4"
            class="border-input placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 dark:bg-input/30 flex min-h-16 w-full rounded-md border bg-transparent px-3 py-2 text-base shadow-xs outline-none focus-visible:ring-3 disabled:opacity-50 md:text-sm"
            :disabled="submitting"
            @input="onBodyInput"
          />
        </div>
        <Button
          type="button"
          class="w-full"
          :disabled="!canSubmit || submitting"
          :aria-busy="submitting"
          @click="onSubmit"
        >
          <Loader2Icon v-if="submitting" class="size-4 animate-spin" />
          {{ submitting ? 'در حال ثبت…' : 'ثبت پاسخ' }}
        </Button>
      </form>
    </CardContent>
  </Card>
</template>
