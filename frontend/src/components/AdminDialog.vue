<script setup lang="ts">
import { CircleAlertIcon, Loader2Icon, RotateCcwIcon, TriangleAlertIcon } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
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
import { ApiError } from '@/lib/http'
import {
  useGameSettingsQuery,
  useRestartGameMutation,
  useUpdateGameSettingsMutation,
} from '@/queries/gameState'
import type { GameSettings, GameStatus } from '@/types/api'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'update:open', value: boolean): void }>()

const open = computed({
  get: () => props.open,
  set: (value: boolean) => emit('update:open', value),
})

const { data: settings, isPending } = useGameSettingsQuery(() => props.open)
const { mutateAsync: save, isPending: saving } = useUpdateGameSettingsMutation()
const { mutateAsync: restart, isPending: restarting } = useRestartGameMutation()

const STATUSES: { value: GameStatus; label: string; hint: string }[] = [
  { value: 'not_started', label: 'شروع نشده', hint: 'هیچ حرکتی پذیرفته نمی‌شود.' },
  { value: 'running', label: 'در حال اجرا', hint: 'تیم‌ها می‌توانند بازی کنند.' },
  { value: 'paused', label: 'متوقف', hint: 'حرکت‌ها موقتاً بسته است.' },
  { value: 'finished', label: 'تمام شده', hint: 'بازی بسته شد.' },
]

const ttl = ref('')
const balance = ref('')
const endsAt = ref('')

/** `datetime-local` wants a naive local string, not an ISO instant. */
function toLocalInput(iso: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`
}

watch(
  settings,
  (value) => {
    if (!value) return
    ttl.value = String(value.attempt_ttl_minutes)
    balance.value = String(value.initial_balance)
    endsAt.value = toLocalInput(value.ends_at)
  },
  { immediate: true },
)

function toAsciiDigits(value: string): string {
  return value
    .replace(/[۰-۹]/g, (digit) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(digit)))
}

function parseCount(raw: string): number | null {
  const cleaned = toAsciiDigits(raw).trim()
  if (cleaned === '') return null
  const parsed = Number(cleaned)
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null
}

async function apply(changes: Partial<GameSettings>, message: string) {
  try {
    await save(changes)
    toast.success(message)
  } catch (error) {
    toast.error(error instanceof ApiError ? error.detail : 'ثبت تغییر ناموفق بود.')
  }
}

function setStatus(status: GameStatus) {
  if (settings.value?.status === status) return
  const label = STATUSES.find((item) => item.value === status)?.label ?? status
  apply({ status }, `وضعیت بازی: ${label}`)
}

function toggleLeaderboard() {
  const next = !settings.value?.leaderboard_public
  apply(
    { leaderboard_public: next },
    next ? 'جدول امتیازات برای تیم‌ها باز شد' : 'جدول امتیازات پنهان شد',
  )
}

function saveNumbers() {
  const ttlValue = parseCount(ttl.value)
  const balanceValue = parseCount(balance.value)
  if (ttlValue === null || ttlValue < 1) {
    toast.error('مهلت پاسخ باید عددی صحیح و دست‌کم ۱ دقیقه باشد.')
    return
  }
  if (balanceValue === null) {
    toast.error('موجودی اولیه باید عددی صحیح باشد.')
    return
  }
  apply(
    { attempt_ttl_minutes: ttlValue, initial_balance: balanceValue },
    'تنظیمات ذخیره شد',
  )
}

// Two deliberate steps: a restart deletes every move of the contest, and this
// dialog is one click away from the header.
const confirmingRestart = ref(false)

async function doRestart() {
  try {
    const result = await restart()
    confirmingRestart.value = false
    toast.success(
      `بازی بازنشانی شد — ${result.occupancies} خانه و ${result.submissions} پاسخ حذف شد.`,
    )
  } catch (error) {
    toast.error(error instanceof ApiError ? error.detail : 'بازنشانی بازی ناموفق بود.')
  }
}

function saveEndsAt() {
  if (endsAt.value === '') {
    apply({ ends_at: null }, 'زمان پایان حذف شد')
    return
  }
  const parsed = new Date(endsAt.value)
  if (Number.isNaN(parsed.getTime())) {
    toast.error('زمان پایان معتبر نیست.')
    return
  }
  apply({ ends_at: parsed.toISOString() }, 'زمان پایان ثبت شد')
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="flex max-h-[85dvh] flex-col gap-4 sm:max-w-md" dir="rtl">
      <DialogHeader class="text-start sm:text-start">
        <DialogTitle class="pe-6">کنترل بازی</DialogTitle>
        <DialogDescription>
          وضعیت بازی و چند تنظیم اصلی. تغییرها بلافاصله برای همهٔ تیم‌ها اعمال می‌شود.
        </DialogDescription>
      </DialogHeader>

      <p v-if="isPending" class="text-muted-foreground flex items-center gap-2 text-sm">
        <Loader2Icon class="size-4 animate-spin" />
        در حال دریافت تنظیمات…
      </p>

      <div v-else-if="settings" class="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto">
        <section class="flex flex-col gap-2">
          <h3 class="text-sm font-semibold">وضعیت بازی</h3>
          <div class="grid grid-cols-2 gap-2">
            <Button
              v-for="option in STATUSES"
              :key="option.value"
              :variant="settings.status === option.value ? 'default' : 'outline'"
              :disabled="saving"
              class="justify-start"
              @click="setStatus(option.value)"
            >
              {{ option.label }}
            </Button>
          </div>
          <p class="text-muted-foreground text-xs">
            {{ STATUSES.find((option) => option.value === settings?.status)?.hint }}
          </p>
        </section>

        <section class="flex items-center justify-between gap-3 rounded-md border p-3">
          <div class="flex flex-col gap-0.5">
            <span class="text-sm font-medium">جدول امتیازات</span>
            <span class="text-muted-foreground text-xs">
              وقتی باز باشد، تیم‌ها هم رتبه‌ها را می‌بینند.
            </span>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <Badge :variant="settings.leaderboard_public ? 'default' : 'secondary'">
              {{ settings.leaderboard_public ? 'باز' : 'پنهان' }}
            </Badge>
            <Button size="sm" variant="outline" :disabled="saving" @click="toggleLeaderboard">
              {{ settings.leaderboard_public ? 'پنهان کن' : 'باز کن' }}
            </Button>
          </div>
        </section>

        <section class="flex flex-col gap-2">
          <Label for="admin-ends-at">زمان پایان بازی</Label>
          <div class="flex items-center gap-2">
            <Input
              id="admin-ends-at"
              v-model="endsAt"
              type="datetime-local"
              class="flex-1"
              :disabled="saving"
            />
            <Button size="sm" variant="outline" :disabled="saving" @click="saveEndsAt">ثبت</Button>
          </div>
          <p class="text-muted-foreground text-xs">
            شمارش معکوس بالای صفحه از این زمان می‌آید. خالی بگذارید تا حذف شود.
          </p>
        </section>

        <section class="flex flex-col gap-3">
          <div class="flex flex-col gap-1.5">
            <Label for="admin-ttl">مهلت پاسخ هر سؤال (دقیقه)</Label>
            <Input
              id="admin-ttl"
              v-model="ttl"
              inputmode="numeric"
              class="tabular-nums"
              :disabled="saving"
            />
          </div>
          <div class="flex flex-col gap-1.5">
            <Label for="admin-balance">موجودی اولیهٔ تیم‌ها</Label>
            <Input
              id="admin-balance"
              v-model="balance"
              inputmode="numeric"
              class="tabular-nums"
              :disabled="saving"
            />
            <p class="text-muted-foreground text-xs">
              فقط روی تیم‌هایی اثر دارد که بعد از این ساخته یا شارژ شوند.
            </p>
          </div>
          <Button variant="secondary" :disabled="saving" @click="saveNumbers">
            <Loader2Icon v-if="saving" class="size-4 animate-spin" />
            ذخیرهٔ تنظیمات
          </Button>
        </section>
      </div>

      <p v-else class="text-destructive flex items-start gap-2 text-sm" role="alert">
        <CircleAlertIcon class="mt-0.5 size-4 shrink-0" />
        دریافت تنظیمات ناموفق بود.
      </p>

      <section
        v-if="settings"
        class="border-destructive/30 bg-destructive/5 flex flex-col gap-2 rounded-md border p-3"
      >
        <div class="flex items-start gap-2">
          <TriangleAlertIcon class="text-destructive mt-0.5 size-4 shrink-0" />
          <div class="flex flex-col gap-0.5">
            <span class="text-sm font-semibold">بازنشانی بازی</span>
            <span class="text-muted-foreground text-xs">
              همهٔ خانه‌ها، پاسخ‌ها و رنگ تیم‌ها پاک می‌شود و موجودی‌ها به مقدار اولیه
              برمی‌گردد. نقشه و بانک سؤال دست‌نخورده می‌ماند. این کار برگشت‌پذیر نیست.
            </span>
          </div>
        </div>

        <div v-if="!confirmingRestart" class="flex justify-end">
          <Button variant="outline" size="sm" :disabled="restarting" @click="confirmingRestart = true">
            <RotateCcwIcon class="size-4" />
            بازنشانی بازی
          </Button>
        </div>
        <div v-else class="flex items-center justify-end gap-2">
          <span class="text-destructive me-auto text-xs font-medium">مطمئنید؟</span>
          <Button
            variant="outline"
            size="sm"
            :disabled="restarting"
            @click="confirmingRestart = false"
          >
            انصراف
          </Button>
          <Button variant="destructive" size="sm" :disabled="restarting" @click="doRestart">
            <Loader2Icon v-if="restarting" class="size-4 animate-spin" />
            بله، پاک کن
          </Button>
        </div>
      </section>

      <DialogFooter class="flex-row gap-2 sm:justify-start">
        <DialogClose as-child>
          <Button variant="outline" class="flex-1">بستن</Button>
        </DialogClose>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
