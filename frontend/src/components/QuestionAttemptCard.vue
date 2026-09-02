<script setup lang="ts">
import { CircleAlertIcon, Loader2Icon, PaperclipIcon } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useCountdown } from '@/composables/useCountdown'
import { formatDuration } from '@/lib/format'
import { ApiError } from '@/lib/http'
import { useSubmitAnswerMutation } from '@/queries/occupancies'
import type { ActiveAttempt } from '@/types/api'

const props = defineProps<{ attempt: ActiveAttempt }>()

const { mutateAsync: submitAnswerAsync, isPending: submitting } = useSubmitAnswerMutation()

const body = ref('')
const file = ref<File | null>(null)

const remainingSeconds = computed(() => props.attempt.remaining_seconds)
const { remaining, expired, timerClass } = useCountdown(remainingSeconds)

watch(
  () => props.attempt.id,
  () => {
    body.value = ''
    file.value = null
  },
)

const question = computed(() => props.attempt.question)
const canAnswer = computed(
  () => props.attempt.status === 'open' && !expired.value && question.value != null,
)

function onFileChange(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

const canSubmit = computed(() => {
  if (!canAnswer.value || !question.value) return false
  if (question.value.answer_type === 'file') return !!file.value
  return body.value.trim() !== ''
})

async function onSubmit() {
  try {
    await submitAnswerAsync({
      occupancyId: props.attempt.id,
      payload: { body: body.value, file: file.value },
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
  <Card v-if="question" class="gap-4">
    <CardHeader class="gap-2">
      <CardTitle class="text-base leading-7">{{ question.title }}</CardTitle>
      <div class="flex flex-wrap items-center gap-2 text-sm">
        <span class="text-muted-foreground">{{ attempt.node_name }}</span>
        <Badge variant="outline" class="font-normal">{{ attempt.level }}</Badge>
        <Badge
          v-if="attempt.status === 'open'"
          role="timer"
          aria-live="off"
          class="tabular-nums"
          :class="timerClass"
        >
          {{ expired ? 'پایان یافت' : formatDuration(remaining) }}
        </Badge>
      </div>
    </CardHeader>

    <CardContent class="flex flex-col gap-4">
      <p class="text-sm leading-7 wrap-break-word whitespace-pre-wrap">
        {{ question.body }}
      </p>

      <Button
        v-if="question.attachment_url"
        as-child
        variant="outline"
        size="sm"
        class="w-fit"
      >
        <a :href="question.attachment_url" target="_blank" rel="noopener noreferrer">
          <PaperclipIcon class="size-4" />
          پیوست سؤال
        </a>
      </Button>

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
        v-else-if="attempt.status === 'expired' || expired"
        class="text-destructive flex items-center gap-2 text-sm"
        role="alert"
      >
        <CircleAlertIcon class="size-4 shrink-0" />
        زمان پاسخ به پایان رسیده است. منتظر آزادسازی توسط منتور باشید.
      </p>

      <template v-else-if="canAnswer">
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
          <Label :for="`answer-numeric-${attempt.id}`">پاسخ</Label>
          <Input
            :id="`answer-numeric-${attempt.id}`"
            v-model="body"
            type="number"
            inputmode="decimal"
            class="tabular-nums"
            :disabled="submitting"
          />
        </div>
        <div v-else class="flex flex-col gap-1.5">
          <Label :for="`answer-text-${attempt.id}`">پاسخ</Label>
          <Textarea
            :id="`answer-text-${attempt.id}`"
            v-model="body"
            rows="4"
            :disabled="submitting"
          />
        </div>
      </template>
    </CardContent>

    <CardFooter v-if="canAnswer">
      <Button
        class="w-full"
        :disabled="!canSubmit || submitting"
        :aria-busy="submitting"
        @click="onSubmit"
      >
        <Loader2Icon v-if="submitting" class="size-4 animate-spin" />
        {{ submitting ? 'در حال ثبت…' : 'ثبت پاسخ' }}
      </Button>
    </CardFooter>
  </Card>
</template>
