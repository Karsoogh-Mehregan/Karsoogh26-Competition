<script setup lang="ts">
import { SearchIcon } from '@lucide/vue'
import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { useSubmissions } from '@/composables/useSubmissions'
import type { SubmissionRow } from '@/types/api'

const { me } = useActing()
const { submissions, loading, error, submitting, grade } = useSubmissions()

const grades = ref<Record<number, string>>({})
const search = ref('')

function toAsciiDigits(value: string): string {
  return value
    .replace(/[۰-۹]/g, (digit) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(digit)))
}

const filteredSubmissions = computed(() => {
  const query = toAsciiDigits(search.value).trim()
  if (!query) return submissions.value
  return submissions.value.filter((row) => String(row.id).includes(query))
})

function gradeValue(row: SubmissionRow): string {
  return grades.value[row.id] ?? ''
}

function setGradeValue(id: number, value: string) {
  grades.value = { ...grades.value, [id]: value }
}

async function submitGrade(row: SubmissionRow) {
  const raw = gradeValue(row).trim()
  const parsed = Number(raw)
  if (raw === '' || !Number.isInteger(parsed) || parsed < 0 || parsed > 100) {
    toast.error('نمره باید عدد صحیح بین ۰ و ۱۰۰ باشد.')
    return
  }
  const ok = await grade(row.id, parsed)
  if (ok) {
    toast.success(`نمره ${parsed} برای سؤال ${row.question_id} ثبت شد`)
    const next = { ...grades.value }
    delete next[row.id]
    grades.value = next
  } else if (error.value) {
    toast.error(error.value)
  }
}
</script>

<template>
  <div class="h-full overflow-y-auto p-6">
    <div class="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <header>
        <h1 class="text-lg font-bold">نمره‌دهی</h1>
        <p class="text-muted-foreground mt-1 text-sm">
          هر submission یک سؤال، تیم و خانه دارد. نمره را وارد کنید و ثبت کنید.
        </p>
      </header>

      <p v-if="error" class="text-destructive text-sm">{{ error }}</p>

      <p v-if="!me" class="text-muted-foreground text-sm">برای دیدن submissionها وارد شوید.</p>

      <div v-else-if="loading" class="flex flex-col gap-3">
        <Skeleton class="h-40 w-full" />
        <Skeleton class="h-40 w-full" />
      </div>

      <template v-else>
        <div class="relative">
          <Label for="submission-search" class="sr-only">جستجوی submission</Label>
          <SearchIcon
            class="text-muted-foreground pointer-events-none absolute top-1/2 start-3 size-4 -translate-y-1/2"
          />
          <Input
            id="submission-search"
            v-model="search"
            type="search"
            inputmode="numeric"
            autocomplete="off"
            class="ps-9"
            placeholder="جستجو با شماره submission"
          />
        </div>

        <p v-if="submissions.length === 0" class="text-muted-foreground text-sm">
          submissionی برای نمره‌دهی نیست.
        </p>

        <p v-else-if="filteredSubmissions.length === 0" class="text-muted-foreground text-sm">
          submission پیدا نشد.
        </p>

        <div v-else class="flex flex-col gap-4">
          <Card v-for="row in filteredSubmissions" :key="row.id">
            <CardHeader>
              <CardTitle>submission {{ row.id }}</CardTitle>
            </CardHeader>
            <CardContent class="flex flex-col gap-3 text-sm">
              <p class="overflow-x-auto whitespace-nowrap">
                آیدی سؤال: <span class="font-semibold">  {{ row.question_id }}  </span>
                آیدی تیم: <span class="font-semibold">  {{ row.team_id }}  </span>
                آیدی نود: <span class="font-semibold">  {{ row.node_code }}  </span>
              </p>
              <div class="flex flex-col gap-1.5">
                <Label :for="`grade-${row.id}`">نمره</Label>
                <Input
                  :id="`grade-${row.id}`"
                  type="number"
                  min="0"
                  max="100"
                  :model-value="gradeValue(row)"
                  :disabled="submitting"
                  @update:model-value="setGradeValue(row.id, String($event))"
                />
              </div>
            </CardContent>
            <CardFooter>
              <Button class="w-full" :disabled="submitting" @click="submitGrade(row)">
                ثبت
              </Button>
            </CardFooter>
          </Card>
        </div>
      </template>
    </div>
  </div>
</template>
