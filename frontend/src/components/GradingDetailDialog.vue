<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/lib/http'
import { useGradeSubmissionMutation, useSubmissionQuery } from '@/queries/game'

const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'webp'])

const props = defineProps<{
  submissionId: number
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  graded: []
}>()

const detailQuery = useSubmissionQuery(() => props.submissionId)
const gradeMutation = useGradeSubmissionMutation()

const gradeInput = ref<string | number>('')
const actionError = ref('')

const detail = computed(() => detailQuery.data.value ?? null)
const alreadyGraded = computed(() => detail.value?.grade != null)

watch(
  () => detail.value?.grade,
  (grade) => {
    gradeInput.value = grade == null ? '' : String(grade)
  },
  { immediate: true },
)

function toAsciiDigits(value: string | number): string {
  return String(value)
    .replace(/[۰-۹]/g, (digit) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(digit)))
}

function sameOriginApiUrl(url: string | null): string | null {
  if (!url) return null
  try {
    const parsed = new URL(url, window.location.origin)
    if (parsed.pathname.startsWith('/api/')) {
      return `${parsed.pathname}${parsed.search}`
    }
  } catch {
    return url
  }
  return url
}

const fileUrl = computed(() => {
  if (detail.value?.file_url) {
    return sameOriginApiUrl(detail.value.file_url)
  }
  return null
})

const fileExt = computed(() => {
  const name = detail.value?.file_name ?? ''
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : ''
})

const fileKind = computed(() => {
  if (!fileUrl.value) return 'none' as const
  if (IMAGE_EXTS.has(fileExt.value)) return 'image' as const
  if (fileExt.value === 'pdf') return 'pdf' as const
  return 'other' as const
})

const loading = computed(() => detailQuery.isPending.value)
const loadError = computed(() => detailQuery.error.value)
const saving = computed(() => gradeMutation.isPending.value)

const dialogOpen = computed({
  get: () => props.open,
  set: (value: boolean) => emit('update:open', value),
})

async function submitGrade() {
  actionError.value = ''
  const raw = toAsciiDigits(gradeInput.value).trim()
  const parsed = Number(raw)
  if (raw === '' || !Number.isInteger(parsed) || parsed < 0 || parsed > 100) {
    actionError.value = 'نمره باید عدد صحیح بین ۰ و ۱۰۰ باشد.'
    toast.error(actionError.value)
    return
  }
  try {
    await gradeMutation.mutateAsync({ submissionId: props.submissionId, grade: parsed })
    toast.success(`نمره ${parsed} ثبت شد`)
    emit('graded')
  } catch (err) {
    actionError.value = err instanceof ApiError ? err.detail : 'ثبت نمره ناموفق بود.'
    toast.error(actionError.value)
  }
}
</script>

<template>
  <Dialog v-model:open="dialogOpen">
    <DialogContent
      class="flex h-[92vh] max-h-[92vh] w-[min(96vw,72rem)] max-w-[min(96vw,72rem)] flex-col gap-4 overflow-hidden p-6 sm:max-w-[min(96vw,72rem)]"
      dir="rtl"
    >
      <DialogHeader class="shrink-0">
        <DialogTitle>
          بررسی پاسخ {{ detail ? detail.id : submissionId }}
        </DialogTitle>
        <DialogDescription v-if="detail">
          {{ detail.team_name }} ·
          <span dir="ltr">{{ detail.question.code }}</span>
          · خانه {{ detail.node_code }}
        </DialogDescription>
        <DialogDescription v-else>
          در حال بارگذاری پاسخ…
        </DialogDescription>
      </DialogHeader>

      <div v-if="loading" class="flex min-h-0 flex-1 flex-col gap-3">
        <Skeleton class="h-8 w-2/3" />
        <Skeleton class="min-h-0 w-full flex-1" />
      </div>

      <p v-else-if="loadError" class="text-destructive text-sm">
        بارگذاری این پاسخ ناموفق بود.
      </p>

      <div v-else-if="detail" class="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
        <p class="text-muted-foreground shrink-0 text-sm">
          سؤال
          <span class="text-foreground font-semibold" dir="ltr">{{ detail.question.code }}</span>
        </p>

        <section class="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
          <div class="flex shrink-0 items-center justify-between gap-3">
            <h3 class="text-sm font-semibold">پاسخ تیم</h3>
            <a
              v-if="fileUrl"
              :href="fileUrl"
              target="_blank"
              rel="noopener noreferrer"
              class="text-primary shrink-0 text-sm underline-offset-4 hover:underline"
              dir="ltr"
            >
              باز کردن فایل{{ detail.file_name ? ` (${detail.file_name})` : '' }}
            </a>
          </div>
          <div class="min-h-0 flex-1 overflow-y-auto">
            <p
              v-if="detail.body"
              class="rounded-md border p-3 text-sm leading-7 whitespace-pre-wrap"
            >
              {{ detail.body }}
            </p>
            <img
              v-if="fileKind === 'image' && fileUrl"
              :src="fileUrl"
              :alt="detail.file_name ?? 'پاسخ تصویری'"
              class="max-h-full w-full rounded-md border object-contain"
            >
            <iframe
              v-else-if="fileKind === 'pdf' && fileUrl"
              :src="fileUrl"
              title="پیش‌نمایش PDF"
              class="h-full min-h-[50vh] w-full rounded-md border bg-muted"
            />
          </div>
        </section>
      </div>

      <form class="shrink-0" @submit.prevent="submitGrade" @click.stop>
        <DialogFooter class="flex-col items-stretch gap-3 sm:flex-col">
          <div class="flex flex-col gap-1.5">
            <Label for="grade-input">نمره (۰ تا ۱۰۰)</Label>
            <div class="flex gap-2">
              <Input
                id="grade-input"
                v-model="gradeInput"
                type="number"
                min="0"
                max="100"
                step="1"
                class="flex-1"
                :disabled="alreadyGraded || saving"
              />
              <Button type="submit" :disabled="alreadyGraded || saving">
                {{ alreadyGraded ? 'ثبت‌شده' : saving ? 'در حال ثبت…' : 'ثبت نمره' }}
              </Button>
            </div>
            <p v-if="actionError" class="text-destructive text-sm" role="alert">
              {{ actionError }}
            </p>
            <p v-if="alreadyGraded" class="text-muted-foreground text-xs">
              نمره {{ detail?.grade }} قبلاً ثبت شده و قابل تغییر نیست.
            </p>
          </div>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
