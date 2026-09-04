<script setup lang="ts">
import {
  CheckCircle2Icon,
  Clock3Icon,
  CoinsIcon,
  HandHeartIcon,
  HeartHandshakeIcon,
  LockKeyholeIcon,
  PlusIcon,
  RefreshCwIcon,
  SparklesIcon,
} from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { formatBalance } from '@/lib/format'
import { playCoinDropSound, playResultSound } from '@/lib/gameAudio'
import { ApiError } from '@/lib/http'
import {
  useCharityBagQuery,
  useCharityBagsQuery,
  useCreateCharityBagMutation,
  useEnterCharityBagMutation,
} from '@/queries/events'
import type { CharityBagAction, CharityBagEvent } from '@/types/api'

const { me, actingTeam, isMentor } = useActing()
const enabled = () => me.value != null
const eventsQuery = useCharityBagsQuery(enabled)
const selectedEventId = ref<number | null>(null)
const eventQuery = useCharityBagQuery(selectedEventId, enabled)
const enterMutation = useEnterCharityBagMutation()
const createMutation = useCreateCharityBagMutation()
const selectedAction = ref<CharityBagAction>('contribute')
const amount = ref(0)
const confirmOpen = ref(false)
const now = ref(Date.now())
let clock: number | null = null

const events = computed(() => eventsQuery.data.value ?? [])

watch(
  events,
  (rows) => {
    if (!rows.length) {
      selectedEventId.value = null
      return
    }
    if (rows.some((event) => event.id === selectedEventId.value)) return
    selectedEventId.value =
      rows.find((event) => event.status === 'active')?.id ??
      rows.find((event) => event.status === 'resolving')?.id ??
      rows.find((event) => event.status === 'scheduled')?.id ??
      rows[0].id
  },
  { immediate: true },
)

const event = computed<CharityBagEvent | null>(
  () =>
    eventQuery.data.value ??
    events.value.find((item) => item.id === selectedEventId.value) ??
    null,
)
const balance = computed(() => actingTeam.value?.balance ?? 0)
const canSubmit = computed(
  () =>
    !!event.value?.can_participate &&
    !!actingTeam.value &&
    amount.value > 0 &&
    amount.value <= balance.value,
)
const loading = computed(
  () => eventsQuery.isPending.value || (selectedEventId.value != null && eventQuery.isPending.value),
)
const errorMessage = computed(() => {
  const error = eventQuery.error.value ?? eventsQuery.error.value
  if (error instanceof ApiError) return error.detail
  if (error instanceof Error) return error.message
  return ''
})
const secondsToStart = computed(() =>
  event.value ? Math.max(0, Math.ceil((new Date(event.value.starts_at).getTime() - now.value) / 1000)) : 0,
)
const secondsRemaining = computed(() =>
  event.value ? Math.max(0, Math.ceil((new Date(event.value.ends_at).getTime() - now.value) / 1000)) : 0,
)

onMounted(() => {
  clock = window.setInterval(() => {
    now.value = Date.now()
    if (event.value?.status === 'active' && secondsRemaining.value === 0) eventQuery.refetch()
  }, 1000)
})

onBeforeUnmount(() => {
  if (clock != null) window.clearInterval(clock)
})

function formatClock(seconds: number): string {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, '0')
  const rest = (seconds % 60).toString().padStart(2, '0')
  return `${minutes}:${rest}`
}

function chooseAmount(value: number): void {
  amount.value = Math.min(value, balance.value)
}

function actionLabel(action: CharityBagAction): string {
  return action === 'contribute' ? 'کمک کردم' : 'درخواست کردم'
}

async function submitChoice(): Promise<void> {
  if (!event.value || !canSubmit.value) return
  playCoinDropSound()
  try {
    await enterMutation.mutateAsync({
      eventId: event.value.id,
      action: selectedAction.value,
      amount: amount.value,
    })
    confirmOpen.value = false
    playResultSound(true)
    toast.success('تصمیم شما ثبت و مبلغ از موجودی کسر شد.')
  } catch (error) {
    toast.error(error instanceof ApiError ? error.detail : 'ثبت تصمیم انجام نشد.')
  }
}

async function createNow(): Promise<void> {
  try {
    const created = await createMutation.mutateAsync({ duration_seconds: 300 })
    selectedEventId.value = created.id
    toast.success('یک کیسه خیریه پنج‌دقیقه‌ای باز شد.')
  } catch (error) {
    toast.error(error instanceof ApiError ? error.detail : 'ساخت رویداد انجام نشد.')
  }
}
</script>

<template>
  <div class="charity-page h-full overflow-y-auto" dir="rtl">
    <div class="mx-auto flex min-h-full w-full max-w-6xl flex-col gap-4 p-3 sm:p-5">
      <header class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <div class="charity-emblem"><HandHeartIcon class="size-6" /></div>
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-xl font-black sm:text-2xl">کیسه خیریه</h1>
              <Badge variant="secondary" class="gap-1"><SparklesIcon class="size-3" /> تصمیم پنهان</Badge>
            </div>
            <p class="text-muted-foreground mt-1 text-xs sm:text-sm">
              کمک می‌کنی یا درخواست می‌دهی؟ نتیجه فقط پس از بسته‌شدن کیسه روشن می‌شود.
            </p>
          </div>
        </div>
        <div class="flex gap-2">
          <Button variant="outline" size="sm" @click="eventsQuery.refetch()">
            <RefreshCwIcon class="size-4" :class="eventsQuery.isFetching.value && 'animate-spin'" />
            تازه‌سازی
          </Button>
          <Button v-if="isMentor" size="sm" :disabled="createMutation.isPending.value" @click="createNow">
            <PlusIcon class="size-4" /> کیسه پنج‌دقیقه‌ای
          </Button>
        </div>
      </header>

      <nav v-if="events.length > 1" class="flex gap-2 overflow-x-auto pb-1" aria-label="انتخاب نوبت رویداد">
        <Button
          v-for="item in events"
          :key="item.id"
          size="sm"
          class="shrink-0"
          :variant="item.id === selectedEventId ? 'default' : 'outline'"
          @click="selectedEventId = item.id"
        >
          نوبت {{ item.id }} · {{ new Date(item.starts_at).toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' }) }}
        </Button>
      </nav>

      <div v-if="loading" class="grid flex-1 gap-4 lg:grid-cols-[1fr_22rem]">
        <Skeleton class="min-h-96 rounded-3xl" />
        <Skeleton class="min-h-72 rounded-3xl" />
      </div>

      <Card v-else-if="errorMessage" class="border-destructive/30 bg-destructive/5 mx-auto w-full max-w-lg">
        <CardContent class="text-center text-sm">{{ errorMessage }}</CardContent>
      </Card>

      <Card v-else-if="!event" class="mx-auto w-full max-w-lg border-dashed text-center">
        <CardContent class="flex flex-col items-center gap-3">
          <HandHeartIcon class="text-muted-foreground size-10" />
          <strong>هنوز کیسه‌ای زمان‌بندی نشده است</strong>
          <Button v-if="isMentor" @click="createNow"><PlusIcon class="size-4" /> باز کردن کیسه</Button>
        </CardContent>
      </Card>

      <template v-else>
        <section class="event-status" :data-status="event.status">
          <div>
            <Badge variant="outline">
              {{ event.status === 'active' ? 'در حال جمع‌آوری' : event.status === 'scheduled' ? 'در انتظار شروع' : event.status === 'resolving' ? 'در حال محاسبه' : 'نتیجه نهایی' }}
            </Badge>
            <p class="mt-2 text-xs opacity-75">نوبت شماره {{ event.id }}</p>
          </div>
          <div class="countdown" aria-live="polite">
            <Clock3Icon class="size-5" />
            <div>
              <strong>{{ formatClock(event.status === 'scheduled' ? secondsToStart : secondsRemaining) }}</strong>
              <span>{{ event.status === 'scheduled' ? 'تا شروع' : event.status === 'active' ? 'تا بسته‌شدن' : 'زمان پایان یافته' }}</span>
            </div>
          </div>
          <div class="privacy-note">
            <LockKeyholeIcon class="size-4" />
            انتخاب‌ها تا پایان پنهان‌اند
          </div>
        </section>

        <section v-if="event.status === 'active' && !event.my_participation" class="grid flex-1 gap-4 lg:grid-cols-[1fr_21rem]">
          <div class="choice-grid">
            <button
              type="button"
              class="choice-card contribute"
              :class="selectedAction === 'contribute' && 'is-selected'"
              @click="selectedAction = 'contribute'"
            >
              <HeartHandshakeIcon class="size-9" />
              <strong>به کیسه کمک می‌کنم</strong>
              <span>اگر درخواست‌ها بیشتر از کمک‌ها باشند، دو برابر مبلغ برمی‌گردد.</span>
            </button>
            <button
              type="button"
              class="choice-card request"
              :class="selectedAction === 'request' && 'is-selected'"
              @click="selectedAction = 'request'"
            >
              <CoinsIcon class="size-9" />
              <strong>از کیسه درخواست می‌کنم</strong>
              <span>اگر کمک‌ها درخواست‌ها را پوشش دهند، دو برابر مبلغ دریافت می‌کنید.</span>
            </button>
          </div>

          <Card class="entry-card gap-4">
            <CardHeader>
              <CardTitle class="text-base">مبلغ تصمیم</CardTitle>
              <p class="text-muted-foreground text-xs">موجودی شما: {{ formatBalance(balance) }}</p>
            </CardHeader>
            <CardContent class="flex flex-col gap-4">
              <div class="relative">
                <Input v-model.number="amount" type="number" min="1" :max="balance" class="h-14 ps-14 text-xl font-black" />
                <span class="text-muted-foreground absolute top-1/2 start-3 -translate-y-1/2 text-xs">گلوریوم</span>
              </div>
              <div class="grid grid-cols-4 gap-1.5">
                <Button v-for="value in [25, 50, 100]" :key="value" variant="outline" size="sm" @click="chooseAmount(value)">{{ value }}</Button>
                <Button variant="outline" size="sm" @click="chooseAmount(balance)">همه</Button>
              </div>
              <p class="text-muted-foreground text-xs leading-6">این مبلغ همان لحظه کسر می‌شود و تصمیم قابل تغییر نیست.</p>
              <Button class="h-11" :disabled="!canSubmit" @click="confirmOpen = true">
                ثبت {{ selectedAction === 'contribute' ? 'کمک' : 'درخواست' }}
              </Button>
            </CardContent>
          </Card>
        </section>

        <Card v-else-if="event.my_participation && event.status !== 'finished'" class="sealed-card mx-auto w-full max-w-2xl text-center">
          <CardContent class="flex flex-col items-center gap-4 py-10">
            <div class="sealed-icon"><CheckCircle2Icon class="size-9" /></div>
            <div>
              <h2 class="text-xl font-black">تصمیم شما داخل کیسه است</h2>
              <p class="text-muted-foreground mt-2 text-sm">
                {{ actionLabel(event.my_participation.action) }} · {{ formatBalance(event.my_participation.amount) }} گلوریوم
              </p>
            </div>
            <Badge variant="secondary"><LockKeyholeIcon class="size-3" /> نتیجه پس از پایان نمایش داده می‌شود</Badge>
          </CardContent>
        </Card>

        <Card v-else-if="event.status === 'scheduled'" class="mx-auto w-full max-w-2xl text-center">
          <CardContent class="py-12">
            <Clock3Icon class="text-muted-foreground mx-auto size-10" />
            <h2 class="mt-4 text-xl font-black">کیسه هنوز باز نشده است</h2>
            <p class="text-muted-foreground mt-2 text-sm">در زمان شروع، هر تیم فقط یک تصمیم ثبت می‌کند.</p>
          </CardContent>
        </Card>

        <Card v-else-if="event.status === 'resolving'" class="resolving-card mx-auto w-full max-w-2xl text-center">
          <CardContent class="py-12">
            <div class="coin-loader"><CoinsIcon class="size-9" /></div>
            <h2 class="mt-5 text-xl font-black">کیسه در حال شمارش است…</h2>
          </CardContent>
        </Card>

        <section v-else class="result-grid">
          <Card class="result-hero" :class="event.charity_succeeded ? 'is-success' : 'is-failed'">
            <CardContent class="relative flex flex-col items-center gap-4 overflow-hidden py-9 text-center">
              <span v-for="coin in 12" :key="coin" class="result-coin" :style="{ '--coin': coin }" />
              <div class="result-icon"><HandHeartIcon class="size-10" /></div>
              <div>
                <Badge>{{ event.charity_succeeded ? 'خیریه موفق شد' : 'خیریه شکست خورد' }}</Badge>
                <h2 class="mt-3 text-2xl font-black">
                  {{ event.charity_succeeded ? 'درخواست‌کنندگان برنده شدند' : 'کمک‌کنندگان برنده شدند' }}
                </h2>
              </div>
              <div class="totals">
                <div><span>مجموع کمک</span><strong>{{ formatBalance(event.total_contributed) }}</strong></div>
                <div><span>مجموع درخواست</span><strong>{{ formatBalance(event.total_requested) }}</strong></div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle class="text-base">کارنامه تیم‌ها</CardTitle></CardHeader>
            <CardContent>
              <ul class="result-list">
                <li v-for="entry in event.participations" :key="entry.team.code">
                  <div><strong>{{ entry.team.name }}</strong><span>{{ actionLabel(entry.action) }} · {{ formatBalance(entry.amount) }}</span></div>
                  <Badge :variant="entry.final_payout ? 'secondary' : 'outline'">{{ entry.final_payout ? `دریافت ${formatBalance(entry.final_payout)}` : 'بدون پرداخت' }}</Badge>
                </li>
              </ul>
            </CardContent>
          </Card>
        </section>
      </template>
    </div>

    <Dialog v-model:open="confirmOpen">
      <DialogContent class="sm:max-w-md" dir="rtl">
        <DialogHeader>
          <DialogTitle>تصمیم نهایی است</DialogTitle>
          <DialogDescription>
            {{ formatBalance(amount) }} گلوریوم همین حالا از موجودی تیم کسر می‌شود.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter class="gap-2 sm:justify-start">
          <Button :disabled="enterMutation.isPending.value" @click="submitChoice">تأیید و ثبت</Button>
          <Button variant="outline" @click="confirmOpen = false">بازگشت</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped>
.charity-page { background: radial-gradient(circle at 15% 10%, rgb(16 185 129 / 10%), transparent 28rem), radial-gradient(circle at 90% 90%, rgb(245 158 11 / 9%), transparent 24rem), var(--background); }
.charity-emblem { display:grid; width:3rem; height:3rem; place-items:center; border-radius:1rem; background:linear-gradient(145deg,#047857,#10b981); color:white; box-shadow:0 14px 28px -16px rgb(5 150 105 / 90%); }
.event-status { display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:1rem; padding:.8rem 1rem; border:1px solid rgb(5 150 105 / 20%); border-radius:1.2rem; background:color-mix(in oklab,var(--card) 94%,#d1fae5 6%); }
.countdown { display:flex; align-items:center; gap:.65rem; padding:.55rem .9rem; border-radius:1rem; background:#064e3b; color:white; }
.countdown div { display:flex; flex-direction:column; }
.countdown strong { font-family:var(--font-secondary); font-size:1.4rem; line-height:1; letter-spacing:.08em; }
.countdown span { margin-top:.2rem; font-size:.58rem; opacity:.7; }
.privacy-note { display:flex; justify-self:end; align-items:center; gap:.4rem; color:#047857; font-size:.72rem; font-weight:700; }
.choice-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:1rem; }
.choice-card { display:flex; min-height:18rem; flex-direction:column; align-items:flex-start; justify-content:flex-end; gap:.8rem; padding:1.4rem; border:2px solid var(--border); border-radius:1.5rem; text-align:start; transition:transform 180ms ease,border-color 180ms ease,box-shadow 180ms ease; }
.choice-card strong { font-size:1.15rem; }
.choice-card span { max-width:24rem; color:var(--muted-foreground); font-size:.75rem; line-height:1.8; }
.choice-card.contribute { background:linear-gradient(145deg,#ecfdf5,#fff 60%); color:#047857; }
.choice-card.request { background:linear-gradient(145deg,#fff7ed,#fff 60%); color:#c2410c; }
.choice-card:hover { transform:translateY(-3px); }
.choice-card.is-selected { border-color:currentColor; box-shadow:0 0 0 3px color-mix(in oklab,currentColor 13%,transparent),0 24px 44px -34px currentColor; }
.entry-card { background:color-mix(in oklab,var(--card) 96%,#ecfdf5 4%); }
.sealed-card { border-color:rgb(5 150 105 / 24%); background:linear-gradient(160deg,#ecfdf5,#fff 60%); }
.sealed-icon,.result-icon { display:grid; width:5rem; height:5rem; place-items:center; border-radius:1.5rem; background:#047857; color:white; box-shadow:0 18px 34px -20px rgb(4 120 87 / 90%); }
.coin-loader { display:grid; width:5rem; height:5rem; margin-inline:auto; place-items:center; border:1px solid #f59e0b; border-radius:999px; background:#fef3c7; color:#b45309; animation:coin-spin 1s ease-in-out infinite; }
.result-grid { display:grid; gap:1rem; grid-template-columns:minmax(0,1.25fr) minmax(18rem,.75fr); }
.result-hero { border-color:rgb(5 150 105 / 25%); background:linear-gradient(145deg,#ecfdf5,#fff 68%); }
.result-hero.is-failed { border-color:rgb(245 158 11 / 30%); background:linear-gradient(145deg,#fff7ed,#fff 68%); }
.totals { display:grid; width:min(100%,28rem); grid-template-columns:1fr 1fr; gap:.7rem; }
.totals div { display:flex; flex-direction:column; gap:.25rem; padding:.8rem; border:1px solid rgb(5 150 105 / 18%); border-radius:.8rem; background:rgb(255 255 255 / 72%); }
.totals span,.result-list span { color:var(--muted-foreground); font-size:.7rem; }
.totals strong { font-family:var(--font-secondary); font-size:1.15rem; }
.result-list { display:flex; flex-direction:column; gap:.55rem; }
.result-list li { display:flex; align-items:center; justify-content:space-between; gap:.8rem; padding:.65rem .75rem; border-radius:.75rem; background:var(--muted); }
.result-list li div { display:flex; min-width:0; flex-direction:column; gap:.2rem; }
.result-coin { position:absolute; top:-1rem; left:calc(var(--coin) * 8% - 5%); width:.55rem; height:.55rem; border-radius:999px; background:#f59e0b; animation:coin-rain 1.8s calc(var(--coin) * -90ms) ease-in infinite; opacity:.65; }
@keyframes coin-spin { 50% { transform:rotateY(180deg) scale(1.08); } }
@keyframes coin-rain { from { transform:translateY(-1rem) rotate(0); } to { transform:translateY(22rem) rotate(520deg); } }
@media (max-width:800px) { .event-status { grid-template-columns:1fr auto; } .privacy-note { grid-column:1/-1; justify-self:start; } .result-grid { grid-template-columns:1fr; } }
@media (max-width:640px) { .choice-grid { grid-template-columns:1fr; } .choice-card { min-height:12rem; } .event-status { grid-template-columns:1fr; } .countdown,.privacy-note { justify-self:stretch; justify-content:center; } }
@media (prefers-reduced-motion:reduce) { .choice-card,.coin-loader,.result-coin { animation:none; transition:none; } }
</style>
