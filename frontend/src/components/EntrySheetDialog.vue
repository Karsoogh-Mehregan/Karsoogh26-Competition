<script setup lang="ts">
import {
  CheckCircle2Icon,
  CircleAlertIcon,
  Loader2Icon,
  RefreshCwIcon,
  XCircleIcon,
} from '@lucide/vue'
import { computed, ref } from 'vue'
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
import { useEntry } from '@/composables/useEntry'
import type { EntryAttempt } from '@/types/api'

const {
  isOpen,
  close,
  sheet,
  questions,
  loading,
  answering,
  retrying,
  retriesLeft,
  error,
  answer,
  retry,
} = useEntry()

const open = computed({
  get: () => isOpen.value,
  set: (value: boolean) => {
    if (!value) close()
  },
})

const drafts = ref<Record<string, string>>({})
const pendingCode = ref<string | null>(null)

// Teams type Persian digits out of habit; the API wants an integer.
function toAsciiDigits(value: string): string {
  return value
    .replace(/[۰-۹]/g, (digit) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(digit)))
}

function parseAnswer(raw: string): number | null {
  const cleaned = toAsciiDigits(raw).trim()
  if (cleaned === '') return null
  const parsed = Number(cleaned)
  return Number.isInteger(parsed) ? parsed : null
}

function isAnswered(question: EntryAttempt): boolean {
  return question.answered_at !== null
}

async function onSubmit(question: EntryAttempt) {
  const parsed = parseAnswer(drafts.value[question.code] ?? '')
  if (parsed === null) {
    toast.error('پاسخ باید یک عدد صحیح باشد.')
    return
  }
  pendingCode.value = question.code
  const result = await answer(question.code, parsed)
  pendingCode.value = null

  if (result === null) {
    toast.error(error.value || 'ثبت پاسخ ناموفق بود.')
    return
  }
  if (result) {
    toast.success('پاسخ درست بود.')
  } else if (retriesLeft.value > 0) {
    toast.error('پاسخ نادرست بود. می‌توانید دوباره تلاش کنید.')
  } else {
    toast.error('پاسخ نادرست بود. فرصت دیگری باقی نمانده است.')
  }
}

function canRetry(question: EntryAttempt): boolean {
  return question.is_correct === false && retriesLeft.value > 0
}

async function onRetry(question: EntryAttempt) {
  pendingCode.value = question.code
  const ok = await retry(question.code)
  pendingCode.value = null
  if (ok) {
    // Drop the failed guess so the reopened box does not invite resubmitting it.
    const next = { ...drafts.value }
    delete next[question.code]
    drafts.value = next
    toast.success('می‌توانید دوباره به این سؤال پاسخ دهید.')
  } else {
    toast.error(error.value || 'باز کردن تلاش دوباره ناموفق بود.')
  }
}

const progressLabel = computed(() => {
  if (!sheet.value) return ''
  return `${sheet.value.correct_count} از ${sheet.value.required_correct} پاسخ درست`
})
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="flex max-h-[85dvh] flex-col gap-4 sm:max-w-lg" dir="rtl">
      <DialogHeader class="text-start sm:text-start">
        <DialogTitle class="pe-6">سؤال‌های ورودی</DialogTitle>
        <DialogDescription as-child>
          <div class="flex flex-wrap items-center gap-2">
            <span>
              برای گرفتن خانهٔ شروع باید به اندازهٔ کافی پاسخ درست بدهید. پاسخ‌ها عدد صحیح
              هستند؛ اگر پاسخی نادرست بود می‌توانید دوباره به همان سؤال پاسخ دهید.
            </span>
            <Badge v-if="sheet" variant="secondary" class="tabular-nums">
              {{ progressLabel }}
            </Badge>
            <Badge v-if="sheet && sheet.retries_left > 0" variant="outline" class="gap-1">
              <RefreshCwIcon class="size-3" />
              <span class="tabular-nums">{{ sheet.retries_left }}</span>
              تلاش دوبارهٔ باقی‌مانده
            </Badge>
          </div>
        </DialogDescription>
      </DialogHeader>

      <div v-if="loading" class="flex flex-col gap-3">
        <Skeleton class="h-24 w-full" />
        <Skeleton class="h-24 w-full" />
      </div>

      <p v-else-if="error" class="text-destructive flex items-start gap-2 text-sm" role="alert">
        <CircleAlertIcon class="mt-0.5 size-4 shrink-0" />
        {{ error }}
      </p>

      <div v-else class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
        <div
          v-if="sheet?.can_claim_start"
          class="flex items-start gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm"
          role="status"
        >
          <CheckCircle2Icon class="mt-0.5 size-4 shrink-0 text-emerald-600" />
          <span v-if="sheet.qualified">
            برگهٔ ورودی را پاس کردید. حالا می‌توانید خانهٔ شروع خود را روی نقشه انتخاب کنید.
            <template v-if="sheet.draft_order">
              نوبت شما: {{ sheet.draft_order }}
            </template>
          </span>
          <span v-else>
            مهلت اولیه تمام شد، پس نقشه برای همهٔ تیم‌ها باز است.
          </span>
        </div>

        <div
          v-for="question in questions"
          :key="question.code"
          class="bg-muted/40 flex flex-col gap-2.5 rounded-md border p-3"
        >
          <div class="flex items-start justify-between gap-2">
            <span class="text-sm font-semibold">
              {{ question.position }}. {{ question.title }}
            </span>
            <Badge
              v-if="question.is_correct === true"
              class="shrink-0 gap-1 border-transparent bg-emerald-500 text-white"
            >
              <CheckCircle2Icon class="size-3" />
              درست
            </Badge>
            <Badge
              v-else-if="question.is_correct === false"
              variant="destructive"
              class="shrink-0 gap-1"
            >
              <XCircleIcon class="size-3" />
              نادرست
            </Badge>
          </div>

          <p class="text-sm leading-7 wrap-break-word whitespace-pre-wrap">{{ question.body }}</p>

          <div v-if="isAnswered(question)" class="flex items-center gap-2">
            <p class="text-muted-foreground text-xs tabular-nums">
              پاسخ شما: {{ question.answer }}
            </p>
            <Button
              v-if="canRetry(question)"
              class="ms-auto"
              variant="outline"
              size="sm"
              :disabled="retrying"
              :aria-busy="retrying && pendingCode === question.code"
              @click="onRetry(question)"
            >
              <Loader2Icon
                v-if="retrying && pendingCode === question.code"
                class="size-4 animate-spin"
              />
              <RefreshCwIcon v-else class="size-4" />
              تلاش دوباره
            </Button>
            <span
              v-else-if="question.is_correct === false"
              class="text-muted-foreground ms-auto text-xs"
            >
              فرصت تلاش دوباره باقی نمانده
            </span>
          </div>
          <div v-else class="flex items-end gap-2">
            <div class="flex flex-1 flex-col gap-1.5">
              <Label :for="`entry-${question.code}`" class="sr-only">پاسخ</Label>
              <Input
                :id="`entry-${question.code}`"
                v-model="drafts[question.code]"
                inputmode="numeric"
                autocomplete="off"
                class="tabular-nums"
                placeholder="یک عدد صحیح"
                :disabled="answering"
                @keydown.enter.prevent="onSubmit(question)"
              />
            </div>
            <Button
              :disabled="answering || !drafts[question.code]"
              :aria-busy="answering && pendingCode === question.code"
              @click="onSubmit(question)"
            >
              <Loader2Icon
                v-if="answering && pendingCode === question.code"
                class="size-4 animate-spin"
              />
              ثبت
            </Button>
          </div>
        </div>

        <p v-if="questions.length === 0" class="text-muted-foreground text-sm">
          سؤال ورودی‌ای برای این تیم ثبت نشده است.
        </p>
      </div>

      <DialogFooter class="flex-row gap-2 sm:justify-start">
        <DialogClose as-child>
          <Button variant="outline" class="flex-1">بستن</Button>
        </DialogClose>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
