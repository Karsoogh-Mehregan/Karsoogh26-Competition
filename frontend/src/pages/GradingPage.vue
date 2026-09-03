<script setup lang="ts">
import { SearchIcon } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GradingDetailDialog from '@/components/GradingDetailDialog.vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { useSubmissions } from '@/composables/useSubmissions'
import type { SubmissionRow } from '@/types/api'

const route = useRoute()
const router = useRouter()
const { me } = useActing()
const { submissions, loading, error } = useSubmissions()

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

const selectedId = computed(() => {
  const raw = route.params.id
  const value = Array.isArray(raw) ? raw[0] : raw
  if (!value) return null
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
})

const dialogOpen = computed({
  get: () => selectedId.value != null,
  set: (open) => {
    if (!open) void router.push('/grading')
  },
})

function closeDialog() {
  void router.push('/grading')
}

function rowTo(row: SubmissionRow) {
  return { name: 'grading' as const, params: { id: String(row.id) } }
}
</script>

<template>
  <div class="h-full overflow-y-auto p-6">
    <div class="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <header>
        <h1 class="text-lg font-bold">نمره‌دهی</h1>
        <p class="text-muted-foreground mt-1 text-sm">
          روی هر پاسخ کلیک کنید تا صورت سؤال، جواب تیم و فیلد نمره باز شود.
        </p>
      </header>

      <p v-if="error" class="text-destructive text-sm">{{ error }}</p>

      <p v-if="!me" class="text-muted-foreground text-sm">برای دیدن پاسخ‌ها وارد شوید.</p>

      <div v-else-if="loading" class="flex flex-col gap-3">
        <Skeleton class="h-28 w-full" />
        <Skeleton class="h-28 w-full" />
      </div>

      <template v-else>
        <div class="relative">
          <Label for="submission-search" class="sr-only">جستجوی پاسخ</Label>
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
            placeholder="جستجو با شماره پاسخ"
          />
        </div>

        <p v-if="submissions.length === 0" class="text-muted-foreground text-sm">
          پاسخی برای نمره‌دهی نیست.
        </p>

        <p v-else-if="filteredSubmissions.length === 0" class="text-muted-foreground text-sm">
          پاسخ پیدا نشد.
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
                {{ row.team_name }} · {{ row.question_title }} · خانه {{ row.node_code }}
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
