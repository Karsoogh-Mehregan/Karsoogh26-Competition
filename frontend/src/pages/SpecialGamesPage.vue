<script setup lang="ts">
import { CoinsIcon, DicesIcon, GavelIcon, GiftIcon, PlayIcon, RefreshCwIcon, TrophyIcon } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { toast } from 'vue-sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { playCoinDropSound, playDiceRollSound, playResultSound } from '@/lib/gameAudio'
import { ApiError } from '@/lib/http'
import { createRequestId } from '@/lib/uuid'
import {
  useAuctionBidMutation,
  useAuctionEventsQuery,
  useCreateAuctionMutation,
  useCreatePigMutation,
  useCreateWheelMutation,
  useFinishPigMutation,
  usePigActionMutation,
  usePigEventsQuery,
  useResolveAuctionMutation,
  useStartPigGameMutation,
  useWheelDeliveryMutation,
  useWheelEventsQuery,
  useWheelSpinMutation,
  useWheelStateMutation,
} from '@/queries/events'
import type { AuctionPair, WheelPrizeInput, WheelSpin } from '@/types/api'

type Tab = 'auction' | 'wheel' | 'pig'
const route = useRoute()
const tab = computed<Tab>(() => route.path.endsWith('/prize-wheel') ? 'wheel' : route.path.endsWith('/pig') ? 'pig' : 'auction')
const { me, actingTeam, isMentor } = useActing()
const enabled = () => me.value != null

const auctionQuery = useAuctionEventsQuery(() => enabled() && tab.value === 'auction')
const wheelQuery = useWheelEventsQuery(() => enabled() && tab.value === 'wheel')
const pigQuery = usePigEventsQuery(() => enabled() && tab.value === 'pig')
const createAuction = useCreateAuctionMutation()
const bidMutation = useAuctionBidMutation()
const resolveAuction = useResolveAuctionMutation()
const createWheel = useCreateWheelMutation()
const wheelState = useWheelStateMutation()
const spinMutation = useWheelSpinMutation()
const deliveryMutation = useWheelDeliveryMutation()
const createPig = useCreatePigMutation()
const finishPig = useFinishPigMutation()
const startPig = useStartPigGameMutation()
const pigAction = usePigActionMutation()

const auction = computed(() => auctionQuery.data.value?.find((item) => item.status === 'active') ?? auctionQuery.data.value?.[0] ?? null)
const wheel = computed(() => wheelQuery.data.value?.find((item) => item.status === 'active') ?? wheelQuery.data.value?.[0] ?? null)
const pig = computed(() => pigQuery.data.value?.find((item) => item.status === 'active') ?? pigQuery.data.value?.[0] ?? null)
const ownPair = computed(() => auction.value?.pairs.find((pair) => [pair.team_one.code, pair.team_two?.code].includes(actingTeam.value?.code)) ?? null)
const ownGame = computed(() => pig.value?.games.find((game) => game.status === 'active') ?? pig.value?.games[0] ?? null)
const pageQuery = computed(() => tab.value === 'auction' ? auctionQuery : tab.value === 'wheel' ? wheelQuery : pigQuery)
const loading = computed(() => pageQuery.value.isPending.value)
const refreshing = computed(() => pageQuery.value.isFetching.value)

const auctionMinutes = ref(10)
const now = ref(Date.now())
let clock: number | null = null
const bidAmount = ref(10)
const spinCost = ref(10)
const wheelPrizes = ref<WheelPrizeInput[]>([
  { code: 'glorium', prize_type: 'glorium', display_name: 'گِلوریوم', glorium_amount: 50, weight: 10 },
  { code: 'gift', prize_type: 'merchandise', display_name: 'هدیه یادبود', weight: 3, stock: 10 },
  { code: 'grand', prize_type: 'grand_prize', display_name: 'جایزه بزرگ', weight: 1 },
])
const maxPot = ref(500)
const spinning = ref(false)
const rolling = ref(false)
const diceFace = ref(1)
const lastSpin = ref<WheelSpin | null>(null)

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.detail
  if (error instanceof Error) return error.message
  return 'ارتباط با سرور برقرار نشد.'
}

function money(value: number): string { return value.toLocaleString('fa-IR') }
function teamName(pair: AuctionPair, side: 'one' | 'two'): string { return side === 'one' ? pair.team_one.name : pair.team_two?.name ?? 'استراحت' }
function uuid(): string { return createRequestId() }

async function refresh(): Promise<void> {
  await pageQuery.value.refetch()
}

async function makeAuction(): Promise<void> {
  try {
    await createAuction.mutateAsync(Math.max(1, Math.floor(auctionMinutes.value)) * 60)
    toast.success('حراج بر اساس رتبه فعلی تیم‌ها آغاز شد.')
  } catch (error) { toast.error(messageOf(error)) }
}

async function bid(): Promise<void> {
  if (!ownPair.value) return
  try {
    playCoinDropSound()
    await bidMutation.mutateAsync({ pairId: ownPair.value.id, amount: bidAmount.value, requestId: uuid() })
    toast.success('پیشنهاد شما ثبت و تعهد آن از موجودی کم شد.')
  } catch (error) { toast.error(messageOf(error)) }
}

async function settleAuction(): Promise<void> {
  if (!auction.value) return
  try { await resolveAuction.mutateAsync(auction.value.id); toast.success('حراج تسویه شد.') }
  catch (error) { toast.error(messageOf(error)) }
}

async function makeWheel(): Promise<void> {
  try {
    await createWheel.mutateAsync({ spinCost: spinCost.value, prizes: wheelPrizes.value })
    toast.success('گردونه با جوایز تنظیم‌شده ساخته شد.')
  } catch (error) { toast.error(messageOf(error)) }
}

async function changeWheel(action: 'start' | 'stop'): Promise<void> {
  if (!wheel.value) return
  try { await wheelState.mutateAsync({ eventId: wheel.value.id, action }); toast.success(action === 'start' ? 'گردونه فعال شد.' : 'گردونه متوقف شد.') }
  catch (error) { toast.error(messageOf(error)) }
}

async function spin(): Promise<void> {
  if (!wheel.value || spinning.value) return
  spinning.value = true
  playDiceRollSound()
  try {
    const [result] = await Promise.all([
      spinMutation.mutateAsync({ eventId: wheel.value.id, requestId: uuid() }),
      new Promise((resolve) => setTimeout(resolve, 1150)),
    ])
    lastSpin.value = result
    playResultSound(true)
    toast.success(`جایزه شما: ${result.prize_name}`)
  } catch (error) { toast.error(messageOf(error)) }
  finally { spinning.value = false }
}

async function deliver(spinId: number): Promise<void> {
  try { await deliveryMutation.mutateAsync(spinId); toast.success('تحویل جایزه ثبت شد.') }
  catch (error) { toast.error(messageOf(error)) }
}

async function makePig(): Promise<void> {
  try { await createPig.mutateAsync(maxPot.value); toast.success('بازی خوک آماده شد.') }
  catch (error) { toast.error(messageOf(error)) }
}

async function beginPig(): Promise<void> {
  if (!pig.value) return
  try { await startPig.mutateAsync(pig.value.id); playCoinDropSound(); toast.success('ورودی پرداخت شد؛ بازی شروع شد.') }
  catch (error) { toast.error(messageOf(error)) }
}

async function actPig(action: 'roll' | 'cash_out'): Promise<void> {
  if (!ownGame.value || rolling.value) return
  if (action === 'roll') {
    rolling.value = true
    playDiceRollSound()
    const ticker = window.setInterval(() => { diceFace.value = 1 + Math.floor(Math.random() * 6) }, 90)
    try {
      const [game] = await Promise.all([
        pigAction.mutateAsync({ gameId: ownGame.value.id, action, requestId: uuid() }),
        new Promise((resolve) => setTimeout(resolve, 850)),
      ])
      diceFace.value = game.rolls.at(-1)?.dice_result ?? 1
      playResultSound(game.status !== 'finished_rolled_one')
    } catch (error) { toast.error(messageOf(error)) }
    finally { window.clearInterval(ticker); rolling.value = false }
  } else {
    try { await pigAction.mutateAsync({ gameId: ownGame.value.id, action, requestId: uuid() }); playCoinDropSound(); toast.success('موجودی گلدان نقد شد.') }
    catch (error) { toast.error(messageOf(error)) }
  }
}

const pendingDeliveries = computed(() => wheel.value?.spins.filter((item) => item.delivery_status === 'pending') ?? [])
const auctionRemaining = computed(() => auction.value?.status === 'active' ? Math.max(0, Math.ceil((new Date(auction.value.ends_at).getTime() - now.value) / 1000)) : 0)
onMounted(() => { clock = window.setInterval(() => { now.value = Date.now() }, 1000) })
onBeforeUnmount(() => { if (clock != null) window.clearInterval(clock) })
</script>

<template>
  <main class="club h-full min-h-0 overflow-y-auto" dir="rtl">
    <div class="mx-auto flex min-h-full w-full max-w-7xl flex-col gap-4 p-4 sm:p-6">
      <header class="flex items-center justify-between gap-3">
        <div><div class="flex items-center gap-2"><component :is="tab === 'auction' ? GavelIcon : tab === 'wheel' ? GiftIcon : DicesIcon" class="text-amber-600 size-6" /><h1 class="text-xl font-black sm:text-2xl">{{ tab === 'auction' ? 'حراج محدود' : tab === 'wheel' ? 'گردونه شانس' : 'بازی خوک' }}</h1></div><p class="text-muted-foreground mt-1 text-xs sm:text-sm">رویداد مستقل با ثبت امن همه نتایج در سرور.</p></div>
        <Button size="icon" variant="outline" :disabled="refreshing" aria-label="تازه‌سازی" @click="refresh"><RefreshCwIcon class="size-4" :class="refreshing && 'animate-spin'" /></Button>
      </header>

      <div v-if="loading" class="grid flex-1 gap-4 lg:grid-cols-3"><Skeleton v-for="n in 3" :key="n" class="min-h-64 rounded-2xl" /></div>

      <section v-else-if="tab === 'auction'" class="game-grid">
        <Card class="hero-card auction-hero">
          <CardHeader><div class="flex items-center justify-between"><div><Badge variant="outline">رتبه‌بندی زنده</Badge><CardTitle class="mt-3 text-2xl">حراج محدود</CardTitle></div><div class="emblem amber"><GavelIcon class="size-7" /></div></div></CardHeader>
          <CardContent v-if="auction" class="flex flex-col gap-4">
            <div class="stat-row"><div><span>جایزه هر نبرد</span><strong>{{ money(auction.reward) }}</strong></div><div><span>زمان باقی‌مانده</span><strong>{{ money(auctionRemaining) }} ثانیه</strong></div><div><span>شروع پیشنهاد</span><strong>{{ money(auction.opening_bid) }}</strong></div></div>
            <article v-if="ownPair" class="duel">
              <div><b>{{ teamName(ownPair, 'one') }}</b><span>{{ money(ownPair.team_one_bid) }}</span></div><div class="versus">VS</div><div><b>{{ teamName(ownPair, 'two') }}</b><span>{{ money(ownPair.team_two_bid) }}</span></div>
            </article>
            <div v-if="ownPair?.status === 'active' && !isMentor" class="flex flex-col gap-2 sm:flex-row"><Input v-model.number="bidAmount" type="number" :min="Math.max(auction.opening_bid, ownPair.highest_bid + 1)" /><Button :disabled="bidMutation.isPending.value" @click="bid"><CoinsIcon class="size-4" /> ثبت پیشنهاد</Button></div>
            <p v-else-if="ownPair?.winner" class="rounded-xl bg-amber-500/10 p-4 text-center font-bold"><TrophyIcon class="me-2 inline size-5 text-amber-600" />{{ ownPair.winner.name }} برنده شد</p>
          </CardContent>
          <CardContent v-else class="empty">هنوز حراج فعالی وجود ندارد.</CardContent>
        </Card>
        <Card class="side-card"><CardHeader><CardTitle class="text-sm">{{ isMentor ? 'مدیریت حراج' : 'قانون کوتاه' }}</CardTitle></CardHeader><CardContent class="space-y-3">
          <template v-if="isMentor"><Label>مدت حراج (دقیقه)</Label><Input v-model.number="auctionMinutes" type="number" min="1" inputmode="numeric" /><Button class="w-full" :disabled="!!auction && auction.status === 'active'" @click="makeAuction"><PlayIcon class="size-4" /> ساخت و شروع</Button><p class="text-muted-foreground text-xs">رتبه‌بندی هنگام شروع به‌صورت خودکار ثبت می‌شود.</p><Button v-if="auction?.status === 'active'" class="w-full" variant="outline" @click="settleAuction">پایان و تسویه</Button></template>
          <p v-else class="text-muted-foreground text-sm leading-7">پیشنهاد باید از رکورد فعلی بیشتر باشد. فقط اختلاف پیشنهاد جدید شما از موجودی کم می‌شود و همه پیشنهادها نهایی‌اند.</p>
        </CardContent></Card>
        <Card v-if="isMentor && auction" class="wide-card"><CardHeader><CardTitle class="text-sm">جفت‌های حراج</CardTitle></CardHeader><CardContent class="pair-list"><div v-for="pair in auction.pairs" :key="pair.id"><span>{{ teamName(pair, 'one') }} × {{ teamName(pair, 'two') }}</span><b>{{ money(pair.highest_bid) }}</b><Badge variant="secondary">{{ pair.winner?.name ?? pair.highest_bidder?.name ?? 'بدون پیشنهاد' }}</Badge></div></CardContent></Card>
      </section>

      <section v-else-if="tab === 'wheel'" class="game-grid">
        <Card class="hero-card wheel-hero"><CardHeader><div class="flex items-center justify-between"><div><Badge variant="outline">انتخاب امن در سرور</Badge><CardTitle class="mt-3 text-2xl">گردونه شانس</CardTitle></div><div class="emblem violet"><GiftIcon class="size-7" /></div></div></CardHeader><CardContent class="flex flex-col items-center gap-5">
          <div class="wheel" :class="spinning && 'is-spinning'"><div v-for="n in 8" :key="n" class="wheel-ray" :style="{ transform: `rotate(${n * 45}deg)` }" /><GiftIcon class="relative z-10 size-10" /></div>
          <template v-if="wheel"><div class="flex flex-wrap justify-center gap-2"><Badge v-for="prize in wheel.prizes" :key="prize.code" variant="secondary">{{ prize.display_name }}</Badge></div><Button v-if="!isMentor" size="lg" :disabled="!wheel.spins_available || spinning" @click="spin">{{ spinning ? 'در حال چرخش…' : `چرخاندن · ${money(wheel.spin_cost)} گِلوریوم` }}</Button><div v-if="lastSpin" class="result-pop"><TrophyIcon class="size-5" />{{ lastSpin.prize_name }}<small v-if="lastSpin.glorium_payout">+{{ money(lastSpin.glorium_payout) }}</small></div></template>
          <p v-else class="empty">گردونه‌ای ساخته نشده است.</p>
        </CardContent></Card>
        <Card class="side-card"><CardHeader><CardTitle class="text-sm">{{ isMentor ? 'تنظیم گردونه' : 'وضعیت رویداد' }}</CardTitle></CardHeader><CardContent class="space-y-3">
          <template v-if="isMentor"><Label>هزینه هر چرخش</Label><Input v-model.number="spinCost" type="number" min="1" /><div v-for="prize in wheelPrizes" :key="prize.code" class="prize-edit"><Input v-model="prize.display_name" /><Input v-model.number="prize.weight" type="number" min="1" title="وزن شانس" /><Input v-if="prize.prize_type === 'glorium'" v-model.number="prize.glorium_amount" type="number" min="0" title="جایزه گِلوریوم" /><Input v-if="prize.prize_type === 'merchandise'" :model-value="prize.stock ?? 0" type="number" min="0" title="موجودی" @update:model-value="prize.stock = Number($event)" /></div><Button v-if="!wheel || !['scheduled','active'].includes(wheel.status)" class="w-full" @click="makeWheel">ساخت گردونه</Button><Button v-else class="w-full" @click="changeWheel(wheel.status === 'active' ? 'stop' : 'start')">{{ wheel.status === 'active' ? 'توقف گردونه' : 'فعال‌سازی گردونه' }}</Button></template>
          <template v-else-if="wheel"><div class="stat-row vertical"><div><span>وضعیت</span><strong>{{ wheel.status }}</strong></div><div><span>کل ورودی‌ها</span><strong>{{ money(wheel.total_collected) }}</strong></div></div></template>
        </CardContent></Card>
        <Card v-if="isMentor && pendingDeliveries.length" class="wide-card"><CardHeader><CardTitle class="text-sm">جوایز در انتظار تحویل</CardTitle></CardHeader><CardContent class="pair-list"><div v-for="item in pendingDeliveries" :key="item.id"><span>{{ item.team.name }} · {{ item.prize_name }}</span><Button size="sm" variant="outline" @click="deliver(item.id)">ثبت تحویل</Button></div></CardContent></Card>
      </section>

      <section v-else class="game-grid">
        <Card class="hero-card pig-hero"><CardHeader><div class="flex items-center justify-between"><div><Badge variant="outline">تاس واقعی از سرور</Badge><CardTitle class="mt-3 text-2xl">بازی خوک</CardTitle></div><div class="emblem rose"><DicesIcon class="size-7" /></div></div></CardHeader><CardContent class="flex flex-col items-center gap-5">
          <div class="dice" :class="rolling && 'is-rolling'">{{ money(diceFace) }}</div>
          <template v-if="ownGame"><div class="pot"><span>گلدان فعلی</span><strong>{{ money(ownGame.pot) }}</strong><small>از سقف {{ money(ownGame.max_pot) }}</small></div><div v-if="ownGame.status === 'active'" class="grid w-full max-w-md grid-cols-2 gap-2"><Button size="lg" :disabled="rolling" @click="actPig('roll')"><DicesIcon class="size-4" /> تاس بریز</Button><Button size="lg" variant="outline" :disabled="ownGame.pot <= 0 || rolling" @click="actPig('cash_out')"><CoinsIcon class="size-4" /> نقد کردن</Button></div><Badge v-else variant="secondary">بازی پایان یافت · پرداخت {{ money(ownGame.final_payout) }}</Badge></template>
          <Button v-else-if="pig && !isMentor" size="lg" @click="beginPig"><PlayIcon class="size-4" /> شروع با ورودی {{ money(pig.entry_fee) }}</Button><p v-else class="empty">رویداد فعالی وجود ندارد.</p>
        </CardContent></Card>
        <Card class="side-card"><CardHeader><CardTitle class="text-sm">{{ isMentor ? 'مدیریت بازی' : 'سوابق تاس' }}</CardTitle></CardHeader><CardContent class="space-y-3">
          <template v-if="isMentor"><Label>سقف گلدان</Label><Input v-model.number="maxPot" type="number" min="10" step="10" /><Button class="w-full" :disabled="pig?.status === 'active'" @click="makePig">ساخت رویداد</Button><Button v-if="pig?.status === 'active'" class="w-full" variant="outline" @click="finishPig.mutate(pig.id)">پایان پذیرش بازی تازه</Button></template>
          <ol v-else-if="ownGame?.rolls.length" class="rolls"><li v-for="roll in [...ownGame.rolls].reverse()" :key="roll.number"><span>تاس {{ money(roll.number) }}</span><b>{{ money(roll.dice_result) }}</b><small>گلدان {{ money(roll.pot_after) }}</small></li></ol><p v-else class="text-muted-foreground text-sm leading-7">با عدد ۱ همه گلدان از دست می‌رود؛ عددهای ۲ تا ۶ ده برابر به گلدان اضافه می‌کنند.</p>
        </CardContent></Card>
        <Card v-if="isMentor && pig" class="wide-card"><CardHeader><CardTitle class="text-sm">بازی‌های ثبت‌شده</CardTitle></CardHeader><CardContent class="pair-list"><div v-for="game in pig.games" :key="game.id"><span>{{ game.team.name }}</span><b>{{ money(game.pot) }}</b><Badge variant="secondary">{{ game.status }}</Badge></div></CardContent></Card>
      </section>
    </div>
  </main>
</template>

<style scoped>
.club{background:radial-gradient(circle at 8% 8%,rgb(245 158 11/.1),transparent 25rem),radial-gradient(circle at 92% 90%,rgb(124 58 237/.1),transparent 24rem),var(--background)}
.tab-bar{display:flex;gap:.35rem;padding:.35rem;border:1px solid var(--border);border-radius:1rem;background:color-mix(in oklab,var(--card) 92%,transparent);position:sticky;top:.25rem;z-index:20;backdrop-filter:blur(14px)}
.game-grid{display:grid;min-height:0;gap:1rem;grid-template-columns:minmax(0,1fr) 20rem;align-items:start}.hero-card{min-height:31rem;overflow:hidden}.side-card{position:sticky;top:4.5rem}.wide-card{grid-column:1/-1}.auction-hero{background:linear-gradient(145deg,rgb(245 158 11/.08),var(--card) 45%)}.wheel-hero{background:linear-gradient(145deg,rgb(124 58 237/.08),var(--card) 45%)}.pig-hero{background:linear-gradient(145deg,rgb(244 63 94/.08),var(--card) 45%)}
.emblem{display:grid;width:3.5rem;height:3.5rem;place-items:center;border-radius:1rem}.amber{background:rgb(245 158 11/.14);color:#b45309}.violet{background:rgb(124 58 237/.13);color:#6d28d9}.rose{background:rgb(244 63 94/.13);color:#be123c}
.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:.5rem}.stat-row>div{display:flex;flex-direction:column;gap:.25rem;padding:.8rem;border:1px solid var(--border);border-radius:.8rem;background:color-mix(in oklab,var(--card) 80%,transparent)}.stat-row span,.pot span{color:var(--muted-foreground);font-size:.7rem}.stat-row strong,.pot strong{font-family:var(--font-secondary);font-size:1.1rem}.stat-row.vertical{grid-template-columns:1fr}
.duel{display:grid;grid-template-columns:1fr 3rem 1fr;align-items:center;padding:1rem;border:1px solid var(--border);border-radius:1rem}.duel>div:not(.versus){display:flex;flex-direction:column;gap:.35rem;text-align:center}.duel span{font-family:var(--font-secondary);font-size:1.4rem}.versus{text-align:center;font-weight:900;color:var(--muted-foreground)}.empty{display:grid;min-height:12rem;place-items:center;color:var(--muted-foreground);text-align:center}.pair-list{display:grid;gap:.5rem}.pair-list>div{display:flex;align-items:center;justify-content:space-between;gap:.75rem;padding:.7rem;border-radius:.7rem;background:var(--muted)}
.wheel{position:relative;display:grid;width:14rem;height:14rem;place-items:center;overflow:hidden;border:10px solid color-mix(in oklab,#7c3aed 35%,var(--card));border-radius:999px;background:conic-gradient(#f59e0b 0 12.5%,#7c3aed 0 25%,#06b6d4 0 37.5%,#f43f5e 0 50%,#f59e0b 0 62.5%,#7c3aed 0 75%,#06b6d4 0 87.5%,#f43f5e 0);color:white;box-shadow:0 20px 45px -22px #6d28d9}.wheel::before{content:'';position:absolute;width:4rem;height:4rem;border:7px solid white;border-radius:999px;background:#6d28d9}.wheel-ray{position:absolute;width:2px;height:50%;top:0;transform-origin:bottom;background:rgb(255 255 255/.5)}.wheel.is-spinning{animation:wheel-spin 1.15s cubic-bezier(.2,.7,.2,1)}.result-pop{display:flex;align-items:center;gap:.5rem;padding:.8rem 1.1rem;border-radius:999px;background:rgb(124 58 237/.12);font-weight:800;animation:pop .35s ease}.result-pop small{font-family:var(--font-secondary)}.prize-edit{display:grid;grid-template-columns:minmax(0,1fr) 4rem 5.5rem;gap:.35rem}
.dice{display:grid;width:8rem;height:8rem;place-items:center;border:3px solid #be123c;border-radius:1.7rem;background:linear-gradient(145deg,#fff,#ffe4e6);color:#9f1239;font-family:var(--font-secondary);font-size:3.5rem;font-weight:900;box-shadow:0 22px 35px -23px #be123c}.dice.is-rolling{animation:dice-roll .25s linear infinite}.pot{display:flex;flex-direction:column;align-items:center;gap:.2rem}.pot strong{font-size:2rem}.pot small{color:var(--muted-foreground)}.rolls{display:grid;gap:.45rem}.rolls li{display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:.7rem;padding:.65rem;border-radius:.7rem;background:var(--muted)}.rolls b{font-family:var(--font-secondary);font-size:1.1rem}.rolls small{color:var(--muted-foreground)}
@keyframes wheel-spin{to{transform:rotate(1080deg)}}@keyframes dice-roll{50%{transform:rotate(8deg) scale(.92)}}@keyframes pop{from{transform:scale(.75);opacity:0}}@media(max-width:800px){.game-grid{grid-template-columns:1fr}.side-card{position:static}.hero-card{min-height:auto}.tab-bar span{font-size:.72rem}.stat-row{grid-template-columns:1fr}.pair-list>div{flex-wrap:wrap}}@media(prefers-reduced-motion:reduce){.wheel.is-spinning,.dice.is-rolling,.result-pop{animation:none}}
</style>
