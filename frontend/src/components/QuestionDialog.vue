<script setup lang="ts">
import { CircleAlertIcon, Loader2Icon, PaperclipIcon } from '@lucide/vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { formatDuration } from '@/lib/format'
import { ApiError } from '@/lib/http'
import { useOccupancyQuestionQuery, useSubmitAnswerMutation } from '@/queries/occupancies'

const props = defineProps<{ occupancyId: number | null }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const occupancyId = computed(() => props.occupancyId)
const { data, isPending, error: questionError } = useOccupancyQuestionQuery(occupancyId)
const { mutateAsync: submitAnswerAsync, isPending: submitting } = useSubmitAnswerMutation()

const open = computed({
  get: () => props.occupancyId !== null,
  set: (value) => {
    if (!value) emit('close')
  },
})

const body = ref('')
const file = ref<File | null>(null)
const remaining = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

function stopTimer() {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

watch(
  () => data.value?.remaining_seconds,
  (seconds) => {
    stopTimer()
    if (seconds == null) return
    remaining.value = seconds
    timer = setInterval(() => {
      remaining.value = Math.max(0, remaining.value - 1)
      if (remaining.value === 0) stopTimer()
    }, 1000)
  },
  { immediate: true },
)

watch(
  () => props.occupancyId,
  () => {
    body.value = ''
    file.value = null
  },
)

onBeforeUnmount(stopTimer)

const expired = computed(() => remaining.value <= 0)
const urgent = computed(() => !expired.value && remaining.value <= 60)

const timerClass = computed(() => {
  if (expired.value) return 'bg-destructive text-white border-transparent'
  if (urgent.value) return 'bg-destructive/10 text-destructive border-destructive/30'
  return 'bg-muted text-muted-foreground border-transparent'
})

function onFileChange(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

const canSubmit = computed(() => {
  if (!data.value || expired.value) return false
  if (data.value.question.answer_type === 'file') return !!file.value
  return body.value.trim() !== ''
})

async function onSubmit() {
  if (props.occupancyId === null) return
  try {
    await submitAnswerAsync({
      occupancyId: props.occupancyId,
      payload: { body: body.value, file: file.value },
    })
    toast.success('پاسخ ثبت شد. منتظر نمره‌دهی باشید.')
    emit('close')
  } catch (err) {
    toast.error(err instanceof ApiError ? err.detail : 'ثبت پاسخ ناموفق بود.')
    if (err instanceof ApiError && err.status === 409) {
      emit('close')
    }
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="flex max-h-[85dvh] flex-col gap-4 sm:max-w-lg" dir="rtl">
      <DialogHeader class="text-start sm:text-start">
        <DialogTitle class="pe-6">{{ data?.question.title ?? 'سؤال' }}</DialogTitle>
        <DialogDescription v-if="data" as-child>
          <div class="flex items-center gap-2">
            <span>زمان باقی‌مانده</span>
            <Badge
              role="timer"
              aria-live="off"
              class="tabular-nums"
              :class="timerClass"
            >
              {{ expired ? 'پایان یافت' : formatDuration(remaining) }}
            </Badge>
          </div>
        </DialogDescription>
        <DialogDescription v-else>در حال دریافت سؤال…</DialogDescription>
      </DialogHeader>

      <div v-if="isPending" class="flex flex-col gap-2">
        <Skeleton class="h-4 w-2/3" />
        <Skeleton class="h-4 w-full" />
        <Skeleton class="h-20 w-full" />
      </div>

      <p
        v-else-if="questionError"
        class="text-destructive flex items-start gap-2 text-sm"
        role="alert"
      >
        <CircleAlertIcon class="mt-0.5 size-4 shrink-0" />
        {{ questionError instanceof ApiError ? questionError.detail : 'خطا در دریافت سؤال.' }}
      </p>

      <div v-else-if="data" class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
        <p class="text-sm leading-7 wrap-break-word whitespace-pre-wrap">
          {{ data.question.body }}
        </p>

        <Button
          v-if="data.question.attachment_url"
          as-child
          variant="outline"
          size="sm"
          class="w-fit"
        >
          <a :href="data.question.attachment_url" target="_blank" rel="noopener noreferrer">
            <PaperclipIcon class="size-4" />
            پیوست سؤال
          </a>
        </Button>

        <div v-if="data.question.answer_type === 'file'" class="flex flex-col gap-1.5">
          <Label for="answer-file">فایل پاسخ</Label>
          <!-- Native input: shadcn's Input binds v-model, which is invalid on a file input. -->
          <input
            id="answer-file"
            type="file"
            class="border-input file:text-foreground focus-visible:border-ring focus-visible:ring-ring/50 dark:bg-input/30 w-full cursor-pointer rounded-md border bg-transparent px-3 py-1.5 text-sm shadow-xs transition-[color,box-shadow] outline-none file:me-3 file:cursor-pointer file:border-0 file:bg-transparent file:text-sm file:font-medium focus-visible:ring-3 disabled:pointer-events-none disabled:opacity-50"
            :disabled="expired || submitting"
            @change="onFileChange"
          >
          <p v-if="file" class="text-muted-foreground truncate text-xs">{{ file.name }}</p>
        </div>
        <div v-else-if="data.question.answer_type === 'numeric'" class="flex flex-col gap-1.5">
          <Label for="answer-numeric">پاسخ</Label>
          <Input
            id="answer-numeric"
            v-model="body"
            type="number"
            inputmode="decimal"
            class="tabular-nums"
            :disabled="expired || submitting"
          />
        </div>
        <div v-else class="flex flex-col gap-1.5">
          <Label for="answer-text">پاسخ</Label>
          <Textarea
            id="answer-text"
            v-model="body"
            rows="4"
            :disabled="expired || submitting"
          />
        </div>

        <p v-if="expired" class="text-destructive flex items-center gap-2 text-sm" role="alert">
          <CircleAlertIcon class="size-4 shrink-0" />
          زمان پاسخ به پایان رسیده است.
        </p>
      </div>

      <DialogFooter class="flex-row gap-2 sm:justify-start">
        <Button
          class="flex-1"
          :disabled="!canSubmit || submitting"
          :aria-busy="submitting"
          @click="onSubmit"
        >
          <Loader2Icon v-if="submitting" class="size-4 animate-spin" />
          {{ submitting ? 'در حال ثبت…' : 'ثبت پاسخ' }}
        </Button>
        <DialogClose as-child>
          <Button variant="outline" :disabled="submitting">انصراف</Button>
        </DialogClose>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
