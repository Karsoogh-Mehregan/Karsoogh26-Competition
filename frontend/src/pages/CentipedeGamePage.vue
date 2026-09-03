<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { CoinsIcon, FootprintsIcon, PlusIcon, RefreshCwIcon, ShieldIcon, HandIcon, SplitIcon, SproutIcon } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { formatBalance } from '@/lib/format'
import { playCoinDropSound, playResultSound } from '@/lib/gameAudio'
import { useCentipedeGameQuery, useCentipedeGamesQuery, useCreateCentipedeGameMutation, usePlayCentipedeActionMutation } from '@/queries/events'
import type { CentipedeAction } from '@/types/api'

const route = useRoute()
const { me, teams, isMentor } = useActing()
const enabled = () => me.value != null
const gamesQuery = useCentipedeGamesQuery(enabled)
const games = computed(() => gamesQuery.data.value ?? [])
const selectedGameId = ref<number | null>(Number(route.query.game) || null)
const gameQuery = useCentipedeGameQuery(selectedGameId, enabled)
const game = computed(() => gameQuery.data.value ?? games.value.find(g => g.id === selectedGameId.value) ?? null)
const playMutation = usePlayCentipedeActionMutation()
const createMutation = useCreateCentipedeGameMutation()
const createOpen = ref(false)
const firstTeamCode = ref('')
const secondTeamCode = ref('')
const confirmation = ref<{ action: CentipedeAction; round: number; gameId: number } | null>(null)
const myPlayer = computed(() => game.value?.players.find(p => p.code === me.value?.team?.code))
const legacy = computed(() => game.value?.rules_version === 1)
const canAct = computed(() => game.value?.status === 'active' && !!myPlayer.value && (
  legacy.value ? game.value.active_player?.code === myPlayer.value.code : !myPlayer.value.has_chosen
))
const loading = computed(() => gamesQuery.isPending.value || (selectedGameId.value != null && gameQuery.isPending.value))
const pageError = computed(() => gameQuery.error.value ?? gamesQuery.error.value)
const choices = [
  { action: 'produce' as const, label: 'تولید', icon: SproutIcon, color: 'text-emerald-700', description: 'اگر هر دو تولید کنید، ۲۰۰ گلوریوم به صندوق اضافه می‌شود.' },
  { action: 'split' as const, label: 'توافق', icon: SplitIcon, color: 'text-blue-700', description: 'نصف صندوق؛ مگر اینکه طرف مقابل دزدی کند.' },
  { action: 'steal' as const, label: 'دزدی', icon: HandIcon, color: 'text-amber-700', description: 'همه صندوق؛ مقابل قناعت چهارپنجم، مقابل دزدی صفر.' },
  { action: 'preserve' as const, label: 'قناعت', icon: ShieldIcon, color: 'text-violet-700', description: 'در هر حالت یک‌پنجم صندوق را دریافت می‌کنید.' },
]
function label(action: CentipedeAction) {
  return ({ produce: 'تولید', split: 'توافق', steal: 'دزدی', preserve: 'قناعت', take: 'برداشت', continue: 'ادامه' })[action]
}
function message(error: unknown) { return error instanceof Error ? error.message : 'ارتباط با سرور برقرار نشد.' }
watch(games, rows => {
  if (!gamesQuery.data.value || rows.some(g => g.id === selectedGameId.value)) return
  selectedGameId.value = (rows.find(g => g.status === 'active') ?? rows[0])?.id ?? null
}, { immediate: true })
watch([() => game.value?.id, () => game.value?.round_number, () => game.value?.status], () => { confirmation.value = null })
async function refresh() { await Promise.all([gamesQuery.refetch(), selectedGameId.value ? gameQuery.refetch() : null]) }
function choose(action: CentipedeAction) {
  if (game.value && canAct.value) confirmation.value = { action, round: game.value.round_number, gameId: game.value.id }
}
async function submit() {
  const selected = confirmation.value
  if (!selected || !canAct.value) return
  try {
    const updated = await playMutation.mutateAsync({ gameId: selected.gameId, action: selected.action, round_number: selected.round })
    confirmation.value = null
    if (updated.status === 'finished') {
      playCoinDropSound()
      toast.success('بازی تمام شد؛ نتیجه نهایی ثبت شد.')
    } else if (updated.round_number > selected.round) {
      playResultSound(true)
      toast.success(legacy.value ? 'دور بعد آغاز شد.' : '۲۰۰ گلوریوم به صندوق اضافه شد!')
    } else toast.success('تصمیم شما ثبت شد؛ منتظر بازیکن دیگر بمانید.')
  } catch (error) { toast.error(message(error)); await refresh() }
}
function openCreate() {
  firstTeamCode.value = teams.value[0]?.code ?? ''
  secondTeamCode.value = teams.value.find(t => t.code !== firstTeamCode.value)?.code ?? ''
  createOpen.value = true
}
async function createGame() {
  try {
    const created = await createMutation.mutateAsync({ player_one: firstTeamCode.value, player_two: secondTeamCode.value })
    selectedGameId.value = created.id
    createOpen.value = false
    toast.success('از هر بازیکن ۱۰۰ گلوریوم دریافت شد؛ بازی آغاز شد.')
  } catch (error) { toast.error(message(error)) }
}
</script>

<template>
  <div class="h-full overflow-y-auto bg-background" dir="rtl">
    <main class="mx-auto flex max-w-5xl flex-col gap-4 p-4 sm:p-6">
      <header class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <FootprintsIcon class="size-10 rounded-xl bg-primary p-2 text-primary-foreground" />
          <div><h1 class="text-xl font-black">بازی هزارپا</h1><p class="text-xs text-muted-foreground">دو بازیکن، یک صندوق، چهار انتخاب</p></div>
        </div>
        <div class="flex gap-2">
          <Button as-child variant="outline"><RouterLink to="/events">همه رویدادها</RouterLink></Button>
          <Button variant="outline" size="icon" aria-label="تازه‌سازی" @click="refresh"><RefreshCwIcon class="size-4" /></Button>
          <Button v-if="isMentor" @click="openCreate"><PlusIcon class="size-4" />بازی جدید</Button>
        </div>
      </header>
      <p v-if="pageError" role="alert" class="rounded-lg border border-destructive p-3 text-destructive">{{ message(pageError) }}</p>
      <Skeleton v-if="loading" class="h-72 w-full" />
      <Card v-else-if="!game"><CardContent class="py-10 text-center">
        <p class="font-bold">هنوز بازی‌ای ندارید</p><p class="mt-2 text-sm text-muted-foreground">ورودی هر بازیکن ۱۰۰ گلوریوم است. از صفحه همه رویدادها وارد صف شوید.</p>
        <Button as-child class="mt-4"><RouterLink to="/events">رفتن به رویدادها</RouterLink></Button>
      </CardContent></Card>
      <template v-else>
        <div v-if="isMentor && games.length > 1" class="flex flex-wrap gap-2">
          <Button v-for="item in games" :key="item.id" size="sm" :variant="item.id === game.id ? 'default' : 'outline'" @click="selectedGameId = item.id">#{{ item.id }} · {{ item.players[0].name }} / {{ item.players[1].name }}</Button>
        </div>
        <Badge v-if="legacy" variant="secondary">بازی قدیمی؛ قوانین برداشت و ادامه حفظ شده‌اند</Badge>
        <Card class="overflow-hidden border-primary/20 bg-gradient-to-bl from-primary/10 via-card to-card">
          <CardContent class="flex flex-col gap-5 py-6">
            <div class="text-center" aria-live="polite">
              <Badge variant="outline">{{ game.status === 'finished' ? 'پایان بازی' : 'دور ' + game.round_number }}</Badge>
              <template v-if="!legacy">
                <p class="mt-4 text-sm text-muted-foreground">موجودی صندوق مشترک</p>
                <p :key="game.pot" class="pot-reveal mt-1 text-5xl font-black tabular-nums text-primary">{{ formatBalance(game.pot) }} <span class="text-sm">گلوریوم</span></p>
                <div class="mt-4 flex justify-center gap-2" aria-label="مراحل تولید">
                  <span v-for="step in 4" :key="step" class="h-2 w-12 rounded-full transition-colors" :class="step <= game.production_rounds ? 'bg-primary' : 'bg-muted'" />
                </div>
                <p class="mt-2 text-xs text-muted-foreground">{{ game.production_rounds }} از ۴ مرحله تولید · سقف صندوق ۱۰۰۰</p>
              </template>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div v-for="player in game.players" :key="player.code" class="min-w-0 rounded-xl border bg-card/80 p-3 text-center">
                <p class="truncate font-bold">{{ player.name }} <span v-if="player.code === myPlayer?.code" class="text-xs text-primary">(شما)</span></p>
                <p v-if="game.status === 'finished'" class="mt-2 text-xl font-black">{{ formatBalance(player.final_payout) }} <span class="text-xs">گلوریوم دریافتی</span></p>
                <p v-else-if="legacy" class="mt-2">جایزه: {{ formatBalance(player.current_reward) }}</p>
                <p v-else class="mt-2 text-xs text-muted-foreground">{{ player.has_chosen ? '🔒 تصمیم ثبت شده' : 'در حال انتخاب…' }}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card v-if="game.status !== 'finished'">
          <CardHeader><CardTitle class="text-base">{{ canAct ? 'تصمیم این دور شما چیست؟' : myPlayer?.has_chosen ? 'انتخاب شما قفل شد' : 'در انتظار تصمیم بازیکنان' }}</CardTitle></CardHeader>
          <CardContent class="flex flex-col gap-4">
            <p v-if="!legacy" class="text-sm text-muted-foreground">انتخاب‌ها تا ثبت تصمیم هر دو نفر مخفی می‌مانند. پس از تأیید، تغییر انتخاب ممکن نیست.</p>
            <div v-if="legacy" class="flex gap-2"><Button :disabled="!canAct || playMutation.isPending.value" @click="choose('take')">برداشت</Button><Button variant="outline" :disabled="!canAct || playMutation.isPending.value" @click="choose('continue')">ادامه</Button></div>
            <div v-else class="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Button v-for="choice in choices" :key="choice.action" variant="outline" class="h-auto items-start justify-start whitespace-normal rounded-xl p-4 text-start transition-transform enabled:hover:-translate-y-0.5 motion-reduce:transform-none" :disabled="!canAct || playMutation.isPending.value || (choice.action === 'produce' && game.production_rounds >= 4)" @click="choose(choice.action)">
                <component :is="choice.icon" class="mt-1 size-6 shrink-0" :class="choice.color" />
                <span class="flex flex-col gap-1"><span class="text-base font-bold">{{ choice.label }}</span><span class="text-xs font-normal leading-6 text-muted-foreground">{{ choice.action === 'produce' && game.production_rounds >= 4 ? 'سقف تولید تکمیل شده؛ گزینه دیگری انتخاب کنید.' : choice.description }}</span></span>
              </Button>
            </div>
            <p v-if="!legacy" class="text-xs leading-6 text-muted-foreground">فقط تولید دوطرفه بازی را ادامه می‌دهد. در سایر حالت‌ها بازی تمام می‌شود. تولیدکننده سهمی نمی‌گیرد؛ اگر هر دو دزدی کنند، هر دو صفر می‌گیرند. باقی‌مانده پرداخت‌نشده صندوق به کسی تعلق نمی‌گیرد.</p>
          </CardContent>
        </Card>
        <Card v-else><CardContent class="flex flex-wrap items-center justify-between gap-3 py-4"><p class="text-sm">تسویه انجام شد. برای خروج از مسابقه و ورود دوباره به صف، به همه رویدادها برگردید.</p><Button as-child><RouterLink to="/events">همه رویدادها</RouterLink></Button></CardContent></Card>
        <Card><CardHeader><CardTitle class="text-base">تاریخچه انتخاب‌ها</CardTitle></CardHeader><CardContent>
          <p v-if="!game.history.length" class="text-sm text-muted-foreground">پس از مشخص شدن نتیجه دور، انتخاب‌ها اینجا نمایش داده می‌شوند.</p>
          <ol v-else class="grid gap-2 sm:grid-cols-2"><li v-for="decision in game.history" :key="decision.sequence" class="flex items-center justify-between gap-2 rounded-lg border p-3 text-sm"><span>دور {{ decision.round_number }} · {{ decision.actor.name }}</span><Badge variant="secondary">{{ label(decision.action) }}</Badge></li></ol>
        </CardContent></Card>
      </template>
    </main>
    <Dialog :open="confirmation !== null" @update:open="value => { if (!value && !playMutation.isPending.value) confirmation = null }">
      <DialogContent><DialogHeader><DialogTitle>تأیید {{ confirmation ? label(confirmation.action) : '' }}</DialogTitle><DialogDescription>این انتخاب برای دور جاری ثبت و قفل می‌شود. آیا مطمئن هستید؟</DialogDescription></DialogHeader><DialogFooter class="gap-2"><Button :disabled="playMutation.isPending.value || !canAct" @click="submit">{{ playMutation.isPending.value ? 'در حال ثبت…' : 'تأیید انتخاب' }}</Button><Button variant="outline" :disabled="playMutation.isPending.value" @click="confirmation = null">بازگشت</Button></DialogFooter></DialogContent>
    </Dialog>
    <Dialog v-model:open="createOpen"><DialogContent><DialogHeader><DialogTitle>بازی جدید هزارپا</DialogTitle><DialogDescription>از موجودی هر تیم ۱۰۰ گلوریوم کم می‌شود. صندوق اولیه ۲۰۰ گلوریوم است.</DialogDescription></DialogHeader>
      <div class="grid grid-cols-2 gap-3"><section v-for="position in [1, 2]" :key="position" class="flex min-w-0 flex-col gap-2"><h3 class="font-bold">بازیکن {{ position }}</h3><div class="flex max-h-64 flex-col gap-2 overflow-y-auto"><Button v-for="team in teams" :key="team.code" class="h-auto whitespace-normal" :variant="(position === 1 ? firstTeamCode : secondTeamCode) === team.code ? 'default' : 'outline'" :disabled="(position === 1 ? secondTeamCode : firstTeamCode) === team.code" @click="position === 1 ? firstTeamCode = team.code : secondTeamCode = team.code">{{ team.name }}</Button></div></section></div>
      <DialogFooter><Button :disabled="!firstTeamCode || !secondTeamCode || firstTeamCode === secondTeamCode || createMutation.isPending.value" @click="createGame"><CoinsIcon class="size-4" />{{ createMutation.isPending.value ? 'در حال ساخت…' : 'دریافت ورودی و شروع' }}</Button></DialogFooter>
    </DialogContent></Dialog>
  </div>
</template>

<style scoped>
@keyframes pot-reveal { from { opacity: .5; transform: scale(.93) } to { opacity: 1; transform: scale(1) } }
.pot-reveal { animation: pot-reveal .4s ease-out; }
@media (prefers-reduced-motion: reduce) { .pot-reveal { animation: none; } }
</style>
