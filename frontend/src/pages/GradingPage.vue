<script setup lang="ts">
import { CheckIcon, ChevronsUpDownIcon, SearchIcon, XIcon } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GradingDetailDialog from '@/components/GradingDetailDialog.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Combobox,
  ComboboxAnchor,
  ComboboxEmpty,
  ComboboxGroup,
  ComboboxInput,
  ComboboxItem,
  ComboboxItemIndicator,
  ComboboxList,
  ComboboxTrigger,
  ComboboxViewport,
} from '@/components/ui/combobox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { useSubmissions } from '@/composables/useSubmissions'
import type { SubmissionRow } from '@/types/api'

const ALL_QUESTIONS = '__all__'

const route = useRoute()
const router = useRouter()
const { me } = useActing()
const { submissions, loading, error } = useSubmissions()

const idSearch = ref('')

function toAsciiDigits(value: string): string {
  return value
    .replace(/[۰-۹]/g, (digit) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(digit)))
}

/** Survives refresh: /grading?question=<code> */
const questionFilter = computed(() => {
  const raw = route.query.question
  const value = Array.isArray(raw) ? raw[0] : raw
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
})

const questionOptions = computed(() => {
  const counts = new Map<string, number>()
  for (const row of submissions.value) {
    counts.set(row.question_code, (counts.get(row.question_code) ?? 0) + 1)
  }
  return [...counts.entries()]
    .map(([code, count]) => ({ code, count }))
    .sort((a, b) => a.code.localeCompare(b.code, 'en'))
})

const selectedQuestionValue = computed({
  get: () => questionFilter.value ?? ALL_QUESTIONS,
  set: (value: string) => {
    setQuestionFilter(value === ALL_QUESTIONS ? null : value)
  },
})

const selectedQuestionLabel = computed(() => {
  if (!questionFilter.value) {
    return `همه سؤالات (${submissions.value.length})`
  }
  const match = questionOptions.value.find((option) => option.code === questionFilter.value)
  const count = match?.count ?? 0
  return `${questionFilter.value} (${count})`
})

const byQuestion = computed(() => {
  const code = questionFilter.value
  if (!code) return submissions.value
  return submissions.value.filter((row) => row.question_code === code)
})

const filteredSubmissions = computed(() => {
  const query = toAsciiDigits(idSearch.value).trim()
  if (!query) return byQuestion.value
  return byQuestion.value.filter((row) => String(row.id).includes(query))
})

const visibleCount = computed(() => filteredSubmissions.value.length)

const countLabel = computed(() => {
  const n = visibleCount.value
  if (questionFilter.value) {
    return `${n} پاسخ برای ${questionFilter.value}`
  }
  return `${n} پاسخ`
})

const selectedId = computed(() => {
  const raw = route.params.id
  const value = Array.isArray(raw) ? raw[0] : raw
  if (!value) return null
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
})

function gradingQuery() {
  const query: Record<string, string> = {}
  if (questionFilter.value) query.question = questionFilter.value
  return query
}

function setQuestionFilter(code: string | null) {
  const query = { ...route.query } as Record<string, string | string[] | undefined>
  if (code) query.question = code
  else delete query.question

  if (selectedId.value != null) {
    void router.replace({
      name: 'grading',
      params: { id: String(selectedId.value) },
      query,
    })
    return
  }
  void router.replace({ name: 'grading', query })
}

const dialogOpen = computed({
  get: () => selectedId.value != null,
  set: (open) => {
    if (!open) void router.push({ name: 'grading', query: gradingQuery() })
  },
})

function closeDialog() {
  void router.push({ name: 'grading', query: gradingQuery() })
}

function rowTo(row: SubmissionRow) {
  return {
    name: 'grading' as const,
    params: { id: String(row.id) },
    query: gradingQuery(),
  }
}
</script>

<template>
  <div class="h-full overflow-y-auto p-6">
    <div class="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <header class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 class="text-lg font-bold">نمره‌دهی</h1>
          <p class="text-muted-foreground mt-1 text-sm">
            روی هر پاسخ کلیک کنید تا جواب تیم و فیلد نمره باز شود.
          </p>
        </div>
        <Badge
          v-if="me && !loading"
          variant="secondary"
          class="rounded-md px-3 py-1 text-sm tabular-nums"
        >
          {{ countLabel }}
        </Badge>
      </header>

      <p v-if="error" class="text-destructive text-sm">{{ error }}</p>

      <p v-if="!me" class="text-muted-foreground text-sm">برای دیدن پاسخ‌ها وارد شوید.</p>

      <div v-else-if="loading" class="flex flex-col gap-3">
        <Skeleton class="h-10 w-full" />
        <Skeleton class="h-28 w-full" />
        <Skeleton class="h-28 w-full" />
      </div>

      <template v-else>
        <section class="flex flex-col gap-2">
          <div class="flex items-center justify-between gap-2">
            <Label class="text-muted-foreground text-xs font-medium">فیلتر کد سؤال</Label>
            <Button
              v-if="questionFilter"
              type="button"
              variant="ghost"
              size="xs"
              class="text-muted-foreground h-7 gap-1"
              @click="setQuestionFilter(null)"
            >
              <XIcon class="size-3.5" />
              پاک کردن فیلتر
            </Button>
          </div>

          <Combobox v-model="selectedQuestionValue">
            <ComboboxAnchor as-child class="w-full">
              <ComboboxTrigger as-child>
                <Button
                  type="button"
                  variant="outline"
                  class="h-10 w-full justify-between font-normal"
                  dir="rtl"
                >
                  <span class="truncate" :dir="questionFilter ? 'ltr' : 'rtl'">
                    {{ selectedQuestionLabel }}
                  </span>
                  <ChevronsUpDownIcon class="size-4 shrink-0 opacity-50" />
                </Button>
              </ComboboxTrigger>
            </ComboboxAnchor>

            <ComboboxList
              class="w-[var(--reka-combobox-trigger-width)]"
              align="start"
            >
              <ComboboxInput placeholder="جستجوی کد سؤال…" />
              <ComboboxViewport class="max-h-64">
                <ComboboxEmpty>سؤالی پیدا نشد.</ComboboxEmpty>
                <ComboboxGroup>
                  <ComboboxItem :value="ALL_QUESTIONS" class="gap-2">
                    <span class="flex-1 text-start">همه سؤالات</span>
                    <span class="text-muted-foreground tabular-nums">{{ submissions.length }}</span>
                    <ComboboxItemIndicator>
                      <CheckIcon class="size-4" />
                    </ComboboxItemIndicator>
                  </ComboboxItem>
                  <ComboboxItem
                    v-for="option in questionOptions"
                    :key="option.code"
                    :value="option.code"
                    class="gap-2"
                    dir="ltr"
                  >
                    <span class="flex-1 text-start font-medium">{{ option.code }}</span>
                    <span class="text-muted-foreground tabular-nums">{{ option.count }}</span>
                    <ComboboxItemIndicator>
                      <CheckIcon class="size-4" />
                    </ComboboxItemIndicator>
                  </ComboboxItem>
                </ComboboxGroup>
              </ComboboxViewport>
            </ComboboxList>
          </Combobox>
        </section>

        <div class="relative">
          <Label for="submission-search" class="sr-only">جستجوی شماره پاسخ</Label>
          <SearchIcon
            class="text-muted-foreground pointer-events-none absolute top-1/2 start-3 size-4 -translate-y-1/2"
          />
          <Input
            id="submission-search"
            v-model="idSearch"
            type="search"
            inputmode="numeric"
            autocomplete="off"
            class="ps-9"
            placeholder="جستجو با شماره پاسخ"
          />
        </div>

        <p v-if="submissions.length === 0" class="text-muted-foreground text-sm">
          پاسخی برای نمره‌دهی نیست.
        </p>

        <p v-else-if="filteredSubmissions.length === 0" class="text-muted-foreground text-sm">
          پاسخی با این فیلتر پیدا نشد.
        </p>

        <div v-else class="flex flex-col gap-3">
          <RouterLink
            v-for="row in filteredSubmissions"
            :key="row.id"
            :to="rowTo(row)"
            class="block rounded-xl focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none"
          >
            <Card class="transition-colors hover:bg-accent/40">
              <CardHeader>
                <CardTitle class="text-base">پاسخ {{ row.id }}</CardTitle>
              </CardHeader>
              <CardContent class="text-muted-foreground text-sm">
                {{ row.team_name }} ·
                <span dir="ltr">{{ row.question_code }}</span>
                · خانه {{ row.node_code }}
              </CardContent>
            </Card>
          </RouterLink>
        </div>
      </template>
    </div>
  </div>

  <GradingDetailDialog
    v-if="selectedId != null"
    :submission-id="selectedId"
    v-model:open="dialogOpen"
    @graded="closeDialog"
  />
</template>
