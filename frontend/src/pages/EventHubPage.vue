<script setup lang="ts">
import {
  CircleOffIcon,
  LogOutIcon,
  Clock3Icon,
  DicesIcon,
  Gamepad2Icon,
  GavelIcon,
  GiftIcon,
  HandHeartIcon,
  MedalIcon,
  PlayIcon,
  RouteIcon,
  SearchIcon,
  SwordsIcon,
  TargetIcon,
  UsersIcon,
} from '@lucide/vue'
import { computed, markRaw, reactive, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { toast } from 'vue-sonner'
import { useBoard } from '@/composables/useBoard'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { ApiError } from '@/lib/http'
import {
  useCreateAuctionMutation,
  useCreateCharityBagMutation,
  useEventCatalogQuery,
  useMatchmakingMutation,
  useMatchmakingQuery,
  useUpdateEventConfigurationMutation,
} from '@/queries/events'
import type { EventCode, EventConfiguration, MatchmakingTicket } from '@/types/api'

const { me, isMentor, isPlayer } = useActing()
const { board } = useBoard()
const catalogQuery = useEventCatalogQuery(() => me.value != null)
const matchmakingQuery = useMatchmakingQuery(() => isPlayer.value)
const updateMutation = useUpdateEventConfigurationMutation()
const matchmakingMutation = useMatchmakingMutation()
const createAuctionMutation = useCreateAuctionMutation()
const createCharityMutation = useCreateCharityBagMutation()
const durationMinutes = reactive<Record<string, number>>({})

const catalog = computed(() => catalogQuery.data.value ?? [])
const tickets = computed(() => matchmakingQuery.data.value ?? [])

const cards = [
  { code: 'territory_control', title: 'نبرد قلمرو', subtitle: 'تصرف خانه‌ها در بیست نوبت', route: '/events/territory-control', icon: markRaw(SwordsIcon), tone: 'blue' },
  { code: 'charity_bag', title: 'کیسه خیریه', subtitle: 'انتخاب جمعی میان کمک و درخواست', route: '/events/charity-bag', icon: markRaw(HandHeartIcon), tone: 'emerald' },
  { code: 'centipede', title: 'بازی هزارپا', subtitle: 'ورودی ۱۰۰ · تولید، توافق، دزدی یا قناعت', route: '/events/centipede-game', icon: markRaw(RouteIcon), tone: 'orange' },
  { code: 'olympics_coin', title: 'سکه نزدیک دیوار', subtitle: 'نزدیک‌ترین پرتاب، برنده مسابقه', route: '/events/coin-near-wall', icon: markRaw(MedalIcon), tone: 'amber' },
  { code: 'olympics_marble', title: 'تیله هدف', subtitle: 'چهار تیله و مناطق امتیازی', route: '/events/marble-target', icon: markRaw(TargetIcon), tone: 'cyan' },
  { code: 'limited_auction', title: 'حراج محدود', subtitle: 'رقابت رتبه‌های نزدیک برای جایزه', route: '/events/auction', icon: markRaw(GavelIcon), tone: 'yellow' },
  { code: 'prize_wheel', title: 'گردونه شانس', subtitle: 'جوایز تصادفی و امن از سرور', route: '/events/prize-wheel', icon: markRaw(GiftIcon), tone: 'violet' },
  { code: 'pig', title: 'بازی خوک', subtitle: 'تاس بریز، ریسک کن یا نقد کن', route: '/events/pig', icon: markRaw(DicesIcon), tone: 'rose' },
] as const

const visibleCards = computed(() => cards.filter((card) => isMentor.value || configuration(card.code)?.enabled))

watch(catalog, (rows) => {
  for (const row of rows) durationMinutes[row.code] = Math.max(1, Math.round((row.duration_seconds ?? 60) / 60))
}, { immediate: true })

function configuration(code: EventCode): EventConfiguration | undefined {
  return catalog.value.find((item) => item.code === code)
}

function ticketFor(code: EventCode): MatchmakingTicket | undefined {
  return tickets.value.find((item) => item.event_code === code && item.status !== 'cancelled' && !item.dismissed_at)
}

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.detail
  if (error instanceof Error) return error.message
  return 'ارتباط با سرور برقرار نشد.'
}

async function toggle(item: EventConfiguration): Promise<void> {
  try {
    await updateMutation.mutateAsync({ code: item.code, input: { enabled: !item.enabled } })
    toast.success(item.enabled ? 'رویداد غیرفعال شد.' : 'رویداد فعال شد.')
  } catch (error) { toast.error(messageOf(error)) }
}

async function quickStart(item: EventConfiguration): Promise<void> {
  try {
    const minutes = Math.max(1, Math.floor(durationMinutes[item.code] || 1))
    const seconds = minutes * 60
    if (item.code === 'charity_bag') await createCharityMutation.mutateAsync({ board: board.value, duration_seconds: seconds })
    else if (item.code === 'limited_auction') await createAuctionMutation.mutateAsync(seconds)
    else return
    toast.success(`رویداد فعال ${minutes.toLocaleString('fa-IR')} دقیقه‌ای ساخته شد.`)
  } catch (error) { toast.error(messageOf(error)) }
}

async function queue(code: EventCode, action: 'join' | 'cancel' | 'dismiss'): Promise<void> {
  try {
    const ticket = await matchmakingMutation.mutateAsync({ code, action, ticketId: ticketFor(code)?.id })
    toast.success(action === 'dismiss' ? 'مسابقه قبلی بسته شد؛ می‌توانید دوباره حریف پیدا کنید.' : ticket.status === 'matched' ? `حریف پیدا شد: ${ticket.matched_team?.name}` : action === 'join' ? 'به صف همتایابی پیوستید.' : 'از صف خارج شدید.')
  } catch (error) { toast.error(messageOf(error)) }
}
</script>

<template>
  <main class="event-hub h-full min-h-0 overflow-y-auto" dir="rtl">
    <div class="mx-auto w-full max-w-7xl p-4 sm:p-6">
      <header class="hub-header">
        <div class="flex items-center gap-3"><div class="hub-mark"><Gamepad2Icon class="size-7" /></div><div><h1 class="text-xl font-black sm:text-3xl">همه رویدادها</h1><p class="text-muted-foreground mt-1 text-xs sm:text-sm">بازی را انتخاب کنید یا برای مسابقه دونفره حریف پیدا کنید.</p></div></div>
        <Badge v-if="isMentor" variant="secondary">پنل مدیریت رویداد</Badge>
      </header>

      <div v-if="catalogQuery.isPending.value" class="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><Skeleton v-for="n in 8" :key="n" class="h-64 rounded-2xl" /></div>
      <div v-else class="event-grid mt-5">
        <Card v-for="card in visibleCards" :key="card.code" class="event-card" :class="[`tone-${card.tone}`, !configuration(card.code)?.enabled && 'is-disabled']">
          <CardHeader class="pb-3"><div class="flex items-start justify-between gap-3"><div class="game-icon"><component :is="card.icon" class="size-6" /></div><Badge :variant="configuration(card.code)?.enabled ? 'outline' : 'destructive'">{{ configuration(card.code)?.enabled ? 'فعال' : 'غیرفعال' }}</Badge></div><CardTitle class="mt-3 text-lg">{{ card.title }}</CardTitle><p class="text-muted-foreground text-xs leading-6">{{ card.subtitle }}</p></CardHeader>
          <CardContent class="mt-auto space-y-3">
            <div v-if="configuration(card.code)?.has_time_limit" class="timer-line"><Clock3Icon class="size-4" /><span>مدت رویداد تازه</span><b>{{ durationMinutes[card.code] }} دقیقه</b></div>

            <template v-if="isMentor && configuration(card.code)">
              <div v-if="configuration(card.code)?.has_time_limit" class="grid grid-cols-[1fr_auto] gap-2"><div><Label :for="`duration-${card.code}`" class="sr-only">زمان به دقیقه</Label><Input :id="`duration-${card.code}`" v-model.number="durationMinutes[card.code]" type="number" min="1" inputmode="numeric" /></div><Button size="sm" :disabled="createAuctionMutation.isPending.value || createCharityMutation.isPending.value" @click="quickStart(configuration(card.code)!)"><PlayIcon class="size-3.5" /> ساخت و شروع</Button></div>
              <Button class="w-full" :variant="configuration(card.code)?.enabled ? 'destructive' : 'default'" @click="toggle(configuration(card.code)!)"><CircleOffIcon v-if="configuration(card.code)?.enabled" class="size-4" />{{ configuration(card.code)?.enabled ? 'غیرفعال‌کردن' : 'فعال‌کردن' }}</Button>
            </template>

            <template v-else-if="isPlayer && configuration(card.code)?.supports_matchmaking && configuration(card.code)?.enabled">
              <Button v-if="!ticketFor(card.code)" class="w-full" variant="outline" :disabled="matchmakingMutation.isPending.value" @click="queue(card.code, 'join')"><SearchIcon class="size-4" /> پیدا کردن حریف</Button>
              <Button v-else-if="ticketFor(card.code)?.status === 'waiting'" class="w-full" variant="secondary" @click="queue(card.code, 'cancel')"><UsersIcon class="size-4 animate-pulse" /> در انتظار حریف · لغو</Button>
              <div v-else-if="ticketFor(card.code)?.match_path" class="grid gap-2">
                <Button class="w-full" as-child><RouterLink :to="ticketFor(card.code)!.match_path!">مسابقه با {{ ticketFor(card.code)?.matched_team?.name }}</RouterLink></Button>
                <Button class="w-full" variant="ghost" :disabled="matchmakingMutation.isPending.value" @click="queue(card.code, 'dismiss')"><LogOutIcon class="size-4" /> خروج پس از پایان بازی</Button>
              </div>
            </template>

            <Button v-if="configuration(card.code)?.enabled" class="w-full" :variant="isMentor ? 'outline' : 'default'" as-child><RouterLink :to="card.route">ورود به بازی</RouterLink></Button>
            <div v-else-if="!isMentor" class="disabled-note"><CircleOffIcon class="size-4" /> این رویداد موقتاً بسته است.</div>
          </CardContent>
        </Card>
      </div>
    </div>
  </main>
</template>

<style scoped>
.event-hub{background:radial-gradient(circle at 8% 5%,rgb(37 99 235/.09),transparent 26rem),radial-gradient(circle at 94% 96%,rgb(124 58 237/.08),transparent 24rem),var(--background)}.hub-header{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1rem;border:1px solid var(--border);border-radius:1.25rem;background:color-mix(in oklab,var(--card) 92%,transparent);backdrop-filter:blur(12px)}.hub-mark{display:grid;width:3.5rem;height:3.5rem;place-items:center;border-radius:1rem;background:linear-gradient(145deg,#2563eb,#7c3aed);color:white;box-shadow:0 15px 30px -18px #4338ca}.event-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1rem}.event-card{display:flex;min-height:17rem;flex-direction:column;overflow:hidden;border-top:3px solid var(--game-color);background:linear-gradient(150deg,color-mix(in oklab,var(--game-color) 7%,var(--card)),var(--card) 52%);transition:transform .2s ease,box-shadow .2s ease}.event-card:hover{transform:translateY(-3px);box-shadow:0 18px 35px -28px var(--game-color)}.event-card.is-disabled{filter:saturate(.45);opacity:.78}.game-icon{display:grid;width:3rem;height:3rem;place-items:center;border-radius:.9rem;background:color-mix(in oklab,var(--game-color) 14%,var(--card));color:var(--game-color)}.tone-blue{--game-color:#2563eb}.tone-emerald{--game-color:#059669}.tone-orange{--game-color:#ea580c}.tone-amber{--game-color:#d97706}.tone-cyan{--game-color:#0891b2}.tone-yellow{--game-color:#ca8a04}.tone-violet{--game-color:#7c3aed}.tone-rose{--game-color:#e11d48}.timer-line{display:flex;align-items:center;gap:.45rem;padding:.6rem;border-radius:.7rem;background:var(--muted);font-size:.7rem}.timer-line b{margin-inline-start:auto;font-family:var(--font-secondary)}.disabled-note{display:flex;align-items:center;justify-content:center;gap:.4rem;padding:.65rem;color:var(--muted-foreground);font-size:.75rem}@media(max-width:1100px){.event-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:640px){.event-grid{grid-template-columns:1fr}.hub-header{align-items:flex-start}.hub-header>span{display:none}.event-card{min-height:auto}}@media(prefers-reduced-motion:reduce){.event-card{transition:none}.event-card:hover{transform:none}}
</style>
