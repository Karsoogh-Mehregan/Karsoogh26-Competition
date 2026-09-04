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

const questionAttachmentUrl = computed(() =>
  sameOriginApiUrl(detail.value?.question.attachment_url ?? null),
)

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
      class="flex max-h-[90vh] max-w-4xl flex-col overflow-y-auto sm:max-w-4xl"
      dir="rtl"
    >
      <DialogHeader>
        <DialogTitle>
          بررسی پاسخ {{ detail ? detail.id : submissionId }}
        </DialogTitle>
        <DialogDescription v-if="detail">
          {{ detail.team_name }} · {{ detail.question.code }} · خانه {{ detail.node_code }}
        </DialogDescription>
        <DialogDescription v-else>
          در حال بارگذاری پاسخ…
        </DialogDescription>
      </DialogHeader>

      <div v-if="loading" class="flex flex-col gap-3">
        <Skeleton class="h-8 w-2/3" />
        <Skeleton class="h-40 w-full" />
      </div>

      <p v-else-if="loadError" class="text-destructive text-sm">
        بارگذاری این پاسخ ناموفق بود.
      </p>

      <div v-else-if="detail" class="flex flex-col gap-4">
        <section class="flex flex-col gap-1.5">
          <a
            v-if="questionAttachmentUrl"
            :href="questionAttachmentUrl"
            target="_blank"
            rel="noopener noreferrer"
            class="text-primary w-fit text-base font-semibold underline underline-offset-4"
          >
            سؤال {{ detail.question.code }}
          </a>
          <p v-else class="text-base font-semibold">
            سؤال {{ detail.question.code }}
          </p>
          <p v-if="!questionAttachmentUrl" class="text-muted-foreground text-xs">
            پیوست صورت سؤال ندارد
          </p>
          <p v-if="detail.question.answer_key" class="bg-muted rounded-md p-3 text-sm leading-7 whitespace-pre-wrap">
            <span class="text-muted-foreground font-medium">کلید:</span>
            {{ detail.question.answer_key }}
          </p>
        </section>

        <section class="flex flex-col gap-2">
          <h3 class="text-sm font-semibold">پاسخ تیم</h3>
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
            class="max-h-[70vh] w-full rounded-md border object-contain"
          >
          <iframe
            v-else-if="fileKind === 'pdf' && fileUrl"
            :src="fileUrl"
            title="پیش‌نمایش PDF"
            class="h-[70vh] w-full rounded-md border bg-muted"
          />
          <a
            v-if="fileUrl"
            :href="fileUrl"
            target="_blank"
            rel="noopener noreferrer"
            class="text-primary w-fit text-sm underline-offset-4 hover:underline"
          >
            باز کردن فایل{{ detail.file_name ? ` (${detail.file_name})` : '' }}
          </a>
        </section>
      </div>

      <form class="flex flex-col gap-3" @submit.prevent="submitGrade" @click.stop>
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
