<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
const maxGrade = computed(() => detail.value?.question.max_grade ?? 100)

watch(
  () => [props.submissionId, detail.value?.grade] as const,
  ([, grade]) => {
    gradeInput.value = grade == null ? '' : String(grade)
    actionError.value = ''
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
  if (raw === '' || !Number.isInteger(parsed) || parsed < 0 || parsed > maxGrade.value) {
    actionError.value = `نمره باید عدد صحیح بین ۰ و ${maxGrade.value} باشد.`
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
      class="flex h-[96vh] max-h-[96vh] w-[min(98vw,96rem)] max-w-[min(98vw,96rem)] flex-col gap-2 overflow-hidden p-4 sm:max-w-[min(98vw,96rem)]"
      dir="rtl"
    >
      <DialogHeader class="shrink-0 space-y-1 pe-8">
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

      <div v-if="loading" class="flex min-h-0 flex-1 flex-col gap-3 md:flex-row">
        <Skeleton class="min-h-0 w-full flex-1" />
        <Skeleton class="h-40 w-full shrink-0 md:h-auto md:w-64" />
      </div>

      <p v-else-if="loadError" class="text-destructive text-sm">
        بارگذاری این پاسخ ناموفق بود.
      </p>

      <div
        v-else-if="detail"
        class="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden md:flex-row"
      >
        <!-- In RTL, first column sits on the right: answer preview -->
        <section class="flex min-h-0 min-w-0 flex-1 flex-col gap-1.5 overflow-hidden">
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
          <div class="bg-muted/30 min-h-0 flex-1 overflow-y-auto rounded-md border">
            <p
              v-if="detail.body"
              class="p-3 text-sm leading-7 whitespace-pre-wrap"
            >
              {{ detail.body }}
            </p>
            <img
              v-if="fileKind === 'image' && fileUrl"
              :src="fileUrl"
              :alt="detail.file_name ?? 'پاسخ تصویری'"
              class="h-full max-h-full w-full object-contain"
            >
            <iframe
              v-else-if="fileKind === 'pdf' && fileUrl"
              :src="fileUrl"
              title="پیش‌نمایش PDF"
              class="h-full min-h-[50vh] w-full bg-muted md:min-h-full"
            />
          </div>
        </section>

        <!-- Left sidebar: question meta + grade -->
        <aside
          class="border-border flex w-full shrink-0 flex-col gap-4 border-t pt-3 md:w-64 md:border-t-0 md:border-s md:ps-3 md:pt-0"
        >
          <p class="text-muted-foreground text-sm">
            سؤال
            <span class="text-foreground font-semibold" dir="ltr">{{ detail.question.code }}</span>
          </p>

          <form class="flex flex-col gap-3" @submit.prevent="submitGrade" @click.stop>
            <div class="flex flex-col gap-1.5">
              <Label for="grade-input">نمره (۰ تا {{ maxGrade }})</Label>
              <Input
                id="grade-input"
                v-model="gradeInput"
                type="number"
                min="0"
                :max="maxGrade"
                step="1"
                :disabled="alreadyGraded || saving"
              />
            </div>
            <Button type="submit" class="w-full" :disabled="alreadyGraded || saving">
              {{ alreadyGraded ? 'ثبت‌شده' : saving ? 'در حال ثبت…' : 'ثبت نمره' }}
            </Button>
            <p v-if="actionError" class="text-destructive text-sm" role="alert">
              {{ actionError }}
            </p>
            <p v-if="alreadyGraded" class="text-muted-foreground text-xs">
              نمره {{ detail.grade }} قبلاً ثبت شده و قابل تغییر نیست.
            </p>
          </form>
        </aside>
      </div>
    </DialogContent>
  </Dialog>
</template>
