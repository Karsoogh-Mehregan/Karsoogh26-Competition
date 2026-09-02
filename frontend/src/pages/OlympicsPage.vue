<script setup lang="ts">
import {
  CircleAlertIcon,
  CircleDotIcon,
  FlagIcon,
  HistoryIcon,
  MedalIcon,
  PlayIcon,
  PlusIcon,
  RefreshCwIcon,
  RulerIcon,
  SparklesIcon,
  TargetIcon,
  TrophyIcon,
  XIcon,
} from '@lucide/vue'
import { computed, ref, watch } from 'vue'
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
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { ApiError } from '@/lib/http'
import {
  useCreateOlympicsMatchMutation,
  useOlympicsMatchQuery,
  useOlympicsMatchesQuery,
  useRecordOlympicsResultMutation,
  useStartOlympicsMatchMutation,
} from '@/queries/events'
import type {
  OlympicsMatch,
  OlympicsMiniGame,
  OlympicsResult,
  OlympicsScoringZone,
} from '@/types/api'

const { me, teams, isMentor } = useActing()
const enabled = () => me.value != null
const matchesQuery = useOlympicsMatchesQuery(enabled)
const matches = computed(() => matchesQuery.data.value ?? [])
const selectedMatchId = ref<number | null>(null)
const matchQuery = useOlympicsMatchQuery(selectedMatchId, enabled)
const createMutation = useCreateOlympicsMatchMutation()
const startMutation = useStartOlympicsMatchMutation()
const resultMutation = useRecordOlympicsResultMutation()

const createOpen = ref(false)
const resultOpen = ref(false)
const miniGame = ref<OlympicsMiniGame>('coin_near_wall')
const firstTeamCode = ref('')
const secondTeamCode = ref('')
const zones = ref<OlympicsScoringZone[]>([])
const coinOutcome = ref<string>('')
const firstDistance = ref('')
const secondDistance = ref('')
const firstAttempts = ref<Array<string | number | null>>([])
const secondAttempts = ref<Array<string | number | null>>([])
const resultRequestId = ref('')

watch(
  matches,
  (rows) => {
    if (!rows.length) {
      selectedMatchId.value = null
      return
    }
    if (rows.some((item) => item.id === selectedMatchId.value)) return
    const ownCode = me.value?.team?.code
    const preferred =
      rows.find(
        (item) => item.status !== 'finished' && item.players.some((p) => p.code === ownCode),
      ) ??
      rows.find((item) => item.status !== 'finished') ??
      rows[0]
    selectedMatchId.value = preferred.id
  },
  { immediate: true },
)

const match = computed<OlympicsMatch | null>(
  () =>
    matchQuery.data.value ??
    matches.value.find((item) => item.id === selectedMatchId.value) ??
    null,
)
const loading = computed(
  () => matchesQuery.isPending.value || (selectedMatchId.value != null && matchQuery.isPending.value),
)
const refreshing = computed(() => matchesQuery.isFetching.value || matchQuery.isFetching.value)
const errorMessage = computed(() => {
  const error = matchQuery.error.value ?? matchesQuery.error.value
  return error ? messageOf(error) : ''
})
const canRecord = computed(
  () => isMentor.value && match.value && ['active', 'waiting_for_result', 'tiebreak'].includes(match.value.status),
)
const marbleTotals = computed<[number, number]>(() => {
  if (!match.value) return [0, 0]
  const score = (attempt: string | number | null) => {
    if (attempt == null) return 0
    if (typeof attempt === 'number') return attempt
    return match.value?.scoring_zones.find((zone) => zone.code === attempt)?.score ?? 0
  }
  return [
    firstAttempts.value.reduce<number>((sum, item) => sum + score(item), 0),
    secondAttempts.value.reduce<number>((sum, item) => sum + score(item), 0),
  ]
})
const leadingMarblePlayerName = computed(() => {
  if (!match.value || marbleTotals.value[0] === marbleTotals.value[1]) return ''
  return marbleTotals.value[0] > marbleTotals.value[1]
    ? match.value.players[0].name
    : match.value.players[1].name
})
const resultReady = computed(() => {
  if (!match.value) return false
  if (match.value.mini_game === 'coin_near_wall') {
    if (!coinOutcome.value) return false
    return (!firstDistance.value && !secondDistance.value) || (!!firstDistance.value && !!secondDistance.value)
  }
  return (
    firstAttempts.value.length > 0 &&
    firstAttempts.value.length === secondAttempts.value.length &&
    firstAttempts.value.every((item) => item != null) &&
    secondAttempts.value.every((item) => item != null)
  )
})

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.detail
  if (error instanceof Error) return error.message
  return 'خطا در ارتباط با سرور.'
}

function miniGameLabel(value: OlympicsMiniGame): string {
  return value === 'coin_near_wall' ? 'سکه نزدیک دیوار' : 'تیله هدف'
}

function statusLabel(value: OlympicsMatch['status']): string {
  return {
    created: 'آماده شروع',
    active: 'در حال اجرا',
    waiting_for_result: 'در انتظار نتیجه',
    tiebreak: 'تساوی‌شکن',
    finished: 'تمام‌شده',
  }[value]
}

function playerColor(index: number): string {
  return match.value?.players[index]?.color ?? (index === 0 ? '#2b6ca8' : '#e67e22')
}

async function refresh(): Promise<void> {
  await Promise.all([matchesQuery.refetch(), selectedMatchId.value ? matchQuery.refetch() : null])
}

function openCreateDialog(): void {
  miniGame.value = 'coin_near_wall'
  firstTeamCode.value = teams.value[0]?.code ?? ''
  secondTeamCode.value = teams.value.find((team) => team.code !== firstTeamCode.value)?.code ?? ''
  zones.value = [{ code: 'zone-1', label: 'منطقه ۱', score: 1 }]
  createOpen.value = true
}

function addZone(): void {
  const number = zones.value.length + 1
  zones.value.push({
    code: `zone-${crypto.randomUUID().slice(0, 8)}`,
    label: `منطقه ${number.toLocaleString('fa-IR')}`,
    score: number,
  })
}

async function createMatch(): Promise<void> {
  if (!firstTeamCode.value || !secondTeamCode.value) return
  try {
    const created = await createMutation.mutateAsync({
      mini_game: miniGame.value,
      player_one: firstTeamCode.value,
      player_two: secondTeamCode.value,
      scoring_zones: miniGame.value === 'marble_target' ? zones.value : [],
    })
    selectedMatchId.value = created.id
    createOpen.value = false
    toast.success('مسابقه فیزیکی ساخته شد؛ اکنون می‌توانید آن را شروع کنید.')
  } catch (error) {
    toast.error(messageOf(error))
  }
}

async function startMatch(): Promise<void> {
  if (!match.value) return
  try {
    await startMutation.mutateAsync(match.value.id)
    toast.success('مسابقه شروع شد؛ اجرای فیزیکی را انجام دهید.')
  } catch (error) {
    toast.error(messageOf(error))
  }
}

function openResultDialog(): void {
  if (!match.value) return
  coinOutcome.value = ''
  firstDistance.value = ''
  secondDistance.value = ''
  const attemptCount = match.value.status === 'tiebreak' ? 1 : 4
  firstAttempts.value = Array.from({ length: attemptCount }, () => null)
  secondAttempts.value = Array.from({ length: attemptCount }, () => null)
  resultRequestId.value = crypto.randomUUID()
  resultOpen.value = true
}

function addTiebreakAttempt(): void {
  firstAttempts.value.push(null)
  secondAttempts.value.push(null)
}

async function submitResult(): Promise<void> {
  if (!match.value || !resultReady.value) return
  try {
    const payload =
      match.value.mini_game === 'coin_near_wall'
        ? {
            matchId: match.value.id,
            request_id: resultRequestId.value,
            winner: coinOutcome.value === 'tie' ? null : coinOutcome.value,
            is_tie: coinOutcome.value === 'tie',
            player_one_best_distance: firstDistance.value || null,
            player_two_best_distance: secondDistance.value || null,
          }
        : {
            matchId: match.value.id,
            request_id: resultRequestId.value,
            is_tie: marbleTotals.value[0] === marbleTotals.value[1],
            player_one_attempts: firstAttempts.value as Array<string | number>,
            player_two_attempts: secondAttempts.value as Array<string | number>,
          }
    const updated = await resultMutation.mutateAsync(payload)
    resultOpen.value = false
    if (updated.status === 'tiebreak') {
      toast.warning('نتیجه مساوی شد؛ دور تساوی‌شکن لازم است.')
    } else {
      toast.success(`نتیجه نهایی ثبت شد؛ ${updated.winner?.name} برنده است.`)
    }
  } catch (error) {
    toast.error(messageOf(error))
  }
}

function resultSummary(result: OlympicsResult): string {
  if (!match.value) return ''
  if (result.outcome === 'tie') return 'تساوی · نیاز به تکرار'
  const player = result.outcome === 'player_one' ? match.value.players[0] : match.value.players[1]
  return `${player.name} برنده دور`
}
</script>

<template>
  <div class="olympics-page h-full min-h-0 overflow-y-auto" dir="rtl">
    <div class="event-frame mx-auto flex min-h-full w-full max-w-7xl flex-col gap-4 p-4 sm:p-6">
      <header class="event-header flex items-center justify-between gap-3">
        <div class="flex min-w-0 items-center gap-3">
          <div class="event-emblem"><MedalIcon class="size-6" /></div>
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-xl font-black sm:text-2xl">گیلیمپیک</h1>
              <Badge variant="outline">رویداد فیزیکی</Badge>
            </div>
            <p class="text-muted-foreground mt-1 text-xs sm:text-sm">
              اجرای بازی روی زمین؛ ثبت دقیق و قابل پیگیری نتیجه در سامانه.
            </p>
          </div>
        </div>
        <div class="flex shrink-0 gap-2">
          <Button size="icon" variant="outline" :disabled="refreshing" aria-label="تازه‌سازی" @click="refresh">
            <RefreshCwIcon class="size-4" :class="refreshing && 'animate-spin'" />
          </Button>
          <Button v-if="isMentor" class="hidden sm:flex" @click="openCreateDialog">
            <PlusIcon class="size-4" /> مسابقه تازه
          </Button>
        </div>
      </header>

      <div v-if="matches.length > 1" class="flex gap-2 overflow-x-auto pb-1">
        <Button
          v-for="item in matches"
          :key="item.id"
          size="sm"
          class="shrink-0"
          :variant="selectedMatchId === item.id ? 'default' : 'outline'"
          @click="selectedMatchId = item.id"
        >
          {{ miniGameLabel(item.mini_game) }} · {{ item.id.toLocaleString('fa-IR') }}
        </Button>
      </div>

      <div v-if="loading" class="grid flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <Skeleton class="min-h-96 rounded-2xl" />
        <Skeleton class="min-h-72 rounded-2xl" />
      </div>

      <Card v-else-if="errorMessage" class="m-auto max-w-lg border-destructive/30">
        <CardContent class="flex flex-col items-center gap-3 p-8 text-center">
          <CircleAlertIcon class="text-destructive size-9" />
          <p class="font-bold">مسابقه بارگیری نشد</p>
          <p class="text-muted-foreground text-sm">{{ errorMessage }}</p>
          <Button variant="outline" @click="refresh">دوباره تلاش کن</Button>
        </CardContent>
      </Card>

      <Card v-else-if="!match" class="m-auto max-w-lg border-dashed">
        <CardContent class="flex flex-col items-center gap-4 p-10 text-center">
          <div class="empty-icon"><MedalIcon class="size-8" /></div>
          <div>
            <h2 class="font-bold">هنوز مسابقه‌ای ثبت نشده</h2>
            <p class="text-muted-foreground mt-2 text-sm">سرپرست نوع بازی و دو شرکت‌کننده را انتخاب می‌کند.</p>
          </div>
          <Button v-if="isMentor" @click="openCreateDialog"><PlusIcon class="size-4" /> ساخت مسابقه</Button>
        </CardContent>
      </Card>

      <template v-else>
        <section class="match-scoreboard">
          <article
            v-for="(player, index) in match.players"
            :key="player.code"
            class="player-card"
            :class="match.winner?.code === player.code && 'is-winner'"
            :style="{ '--player-color': playerColor(index) }"
          >
            <span class="player-swatch" />
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-bold">{{ player.name }}</p>
              <p class="text-muted-foreground text-[0.65rem]">شرکت‌کننده {{ player.position.toLocaleString('fa-IR') }}</p>
            </div>
            <TrophyIcon v-if="match.winner?.code === player.code" class="text-amber-600 size-5" />
          </article>
          <div class="versus"><strong>VS</strong><span>{{ match.id.toLocaleString('fa-IR') }}</span></div>
        </section>

        <section class="game-layout grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_21rem]">
          <Card class="arena-card min-h-0 overflow-hidden">
            <CardContent class="flex h-full min-h-0 flex-col p-5 sm:p-7">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <Badge :variant="match.status === 'finished' ? 'secondary' : match.status === 'tiebreak' ? 'destructive' : 'outline'">{{ statusLabel(match.status) }}</Badge>
                  <h2 class="mt-3 text-xl font-black sm:text-2xl">{{ miniGameLabel(match.mini_game) }}</h2>
                  <p class="text-muted-foreground mt-1 text-xs leading-6">
                    <template v-if="match.mini_game === 'coin_near_wall'">هر طرف سه سکه پرتاب می‌کند؛ نزدیک‌ترین سکه نتیجه را تعیین می‌کند.</template>
                    <template v-else>هر طرف چهار تیله دارد؛ امتیاز مناطق توسط سرپرست همین مسابقه تعیین شده است.</template>
                  </p>
                </div>
                <div class="game-mark" :class="match.mini_game === 'marble_target' && 'target-mark'">
                  <RulerIcon v-if="match.mini_game === 'coin_near_wall'" class="size-7" />
                  <TargetIcon v-else class="size-7" />
                </div>
              </div>

              <div class="physical-stage my-6 flex min-h-40 flex-1 items-center justify-center">
                <div v-if="match.mini_game === 'coin_near_wall'" class="coin-lane" aria-hidden="true">
                  <div class="wall" />
                  <span v-for="n in 3" :key="`a-${n}`" class="coin coin-a" :style="{ '--n': n }">{{ n.toLocaleString('fa-IR') }}</span>
                  <span v-for="n in 3" :key="`b-${n}`" class="coin coin-b" :style="{ '--n': n }">{{ n.toLocaleString('fa-IR') }}</span>
                </div>
                <div v-else class="target-stage" aria-hidden="true">
                  <div class="target-ring ring-outer">
                    <div class="target-ring ring-middle">
                      <div class="target-ring ring-center"><CircleDotIcon class="size-6" /></div>
                    </div>
                  </div>
                  <span class="marble marble-a" /><span class="marble marble-b" />
                </div>
              </div>

              <div v-if="match.mini_game === 'marble_target'" class="mb-5 flex flex-wrap justify-center gap-2">
                <Badge variant="outline"><span class="size-2 rounded-full bg-muted-foreground" /> بیرون هدف: ۰</Badge>
                <Badge v-for="zone in match.scoring_zones" :key="zone.code" variant="outline">{{ zone.label }}: {{ zone.score.toLocaleString('fa-IR') }}</Badge>
              </div>

              <div class="operator-panel">
                <template v-if="match.status === 'created'">
                  <div><p class="font-bold">مسابقه آماده است</p><p class="text-muted-foreground mt-1 text-xs">پس از آماده شدن وسایل و شرکت‌کنندگان، زمان شروع را ثبت کنید.</p></div>
                  <Button v-if="isMentor" :disabled="startMutation.isPending.value" @click="startMatch"><PlayIcon class="size-4" /> {{ startMutation.isPending.value ? 'در حال شروع…' : 'شروع مسابقه' }}</Button>
                </template>
                <template v-else-if="match.status === 'finished'">
                  <div><p class="font-bold">{{ match.winner?.name }} برنده شد</p><p class="text-muted-foreground mt-1 text-xs">نتیجه نهایی توسط سرپرست ثبت و قفل شده است.</p></div>
                  <TrophyIcon class="text-amber-600 size-7" />
                </template>
                <template v-else-if="match.status === 'tiebreak'">
                  <div><p class="font-bold">مسابقه مساوی شد</p><p class="text-muted-foreground mt-1 text-xs">یک دور فیزیکی تساوی‌شکن اجرا و نتیجه تازه را ثبت کنید.</p></div>
                  <Button v-if="isMentor" :disabled="resultMutation.isPending.value" @click="openResultDialog"><SparklesIcon class="size-4" /> ثبت تساوی‌شکن</Button>
                </template>
                <template v-else>
                  <div><p class="font-bold">اجرای فیزیکی در جریان است</p><p class="text-muted-foreground mt-1 text-xs">سامانه حرکت سکه یا تیله را شبیه‌سازی نمی‌کند.</p></div>
                  <Button v-if="isMentor" :disabled="!canRecord" @click="openResultDialog"><FlagIcon class="size-4" /> ثبت نتیجه</Button>
                </template>
              </div>
            </CardContent>
          </Card>

          <Card class="history-card min-h-0 overflow-hidden">
            <CardHeader class="border-b px-5 py-4">
              <div class="flex items-center justify-between">
                <CardTitle class="flex items-center gap-2 text-sm"><HistoryIcon class="size-4" /> گزارش مسابقه</CardTitle>
                <Badge variant="outline">{{ match.results.length.toLocaleString('fa-IR') }} دور</Badge>
              </div>
            </CardHeader>
            <CardContent class="min-h-0 flex-1 overflow-y-auto p-4">
              <div v-if="!match.results.length" class="flex min-h-44 flex-col items-center justify-center text-center">
                <FlagIcon class="text-muted-foreground/50 size-7" />
                <p class="mt-3 text-sm font-bold">هنوز نتیجه‌ای ثبت نشده</p>
                <p class="text-muted-foreground mt-1 text-xs">هر دور با نام ثبت‌کننده نگهداری می‌شود.</p>
              </div>
              <ol v-else class="result-list">
                <li v-for="result in [...match.results].reverse()" :key="result.request_id" class="result-item">
                  <span class="result-dot" :class="result.outcome === 'tie' && 'is-tie'" />
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center justify-between gap-2">
                      <p class="text-xs font-bold">دور {{ result.round_number.toLocaleString('fa-IR') }}</p>
                      <Badge :variant="result.outcome === 'tie' ? 'destructive' : 'secondary'" class="text-[0.6rem]">{{ resultSummary(result) }}</Badge>
                    </div>
                    <div v-if="result.player_one_total != null" class="mt-2 grid grid-cols-2 gap-2 text-center">
                      <div class="result-stat"><span>{{ match.players[0].name }}</span><strong>{{ result.player_one_total.toLocaleString('fa-IR') }}</strong></div>
                      <div class="result-stat"><span>{{ match.players[1].name }}</span><strong>{{ result.player_two_total?.toLocaleString('fa-IR') }}</strong></div>
                    </div>
                    <div v-else-if="result.player_one_best_distance" class="mt-2 grid grid-cols-2 gap-2 text-center">
                      <div class="result-stat"><span>{{ match.players[0].name }}</span><strong>{{ result.player_one_best_distance }} cm</strong></div>
                      <div class="result-stat"><span>{{ match.players[1].name }}</span><strong>{{ result.player_two_best_distance }} cm</strong></div>
                    </div>
                    <p class="text-muted-foreground mt-2 text-[0.6rem]">ثبت توسط {{ result.recorded_by }}</p>
                  </div>
                </li>
              </ol>
            </CardContent>
          </Card>
        </section>
      </template>
    </div>

    <Dialog v-model:open="createOpen">
      <DialogContent class="max-h-[90vh] overflow-y-auto sm:max-w-xl" dir="rtl">
        <DialogHeader>
          <DialogTitle>ساخت مسابقه گیلیمپیک</DialogTitle>
          <DialogDescription>نوع بازی، دو شرکت‌کننده و در صورت نیاز مناطق امتیازی را مشخص کنید.</DialogDescription>
        </DialogHeader>
        <div class="grid grid-cols-2 gap-2">
          <Button class="h-auto min-h-16 flex-col" :variant="miniGame === 'coin_near_wall' ? 'default' : 'outline'" @click="miniGame = 'coin_near_wall'"><RulerIcon class="size-5" /> سکه نزدیک دیوار</Button>
          <Button class="h-auto min-h-16 flex-col" :variant="miniGame === 'marble_target' ? 'default' : 'outline'" @click="miniGame = 'marble_target'"><TargetIcon class="size-5" /> تیله هدف</Button>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <section class="flex min-w-0 flex-col gap-2">
            <Label>شرکت‌کننده اول</Label>
            <div class="flex max-h-40 flex-col gap-1 overflow-y-auto">
              <Button v-for="team in teams" :key="`first-${team.code}`" size="sm" class="justify-start" :variant="firstTeamCode === team.code ? 'default' : 'outline'" :disabled="secondTeamCode === team.code" @click="firstTeamCode = team.code">{{ team.name }}</Button>
            </div>
          </section>
          <section class="flex min-w-0 flex-col gap-2">
            <Label>شرکت‌کننده دوم</Label>
            <div class="flex max-h-40 flex-col gap-1 overflow-y-auto">
              <Button v-for="team in teams" :key="`second-${team.code}`" size="sm" class="justify-start" :variant="secondTeamCode === team.code ? 'default' : 'outline'" :disabled="firstTeamCode === team.code" @click="secondTeamCode = team.code">{{ team.name }}</Button>
            </div>
          </section>
        </div>
        <section v-if="miniGame === 'marble_target'" class="rounded-xl border p-3">
          <div class="mb-3 flex items-center justify-between gap-3">
            <div><h3 class="text-sm font-bold">مناطق امتیازی</h3><p class="text-muted-foreground mt-1 text-xs">هر منطقه را برای هدف واقعی تنظیم کنید.</p></div>
            <Button size="sm" variant="outline" @click="addZone"><PlusIcon class="size-3.5" /> منطقه</Button>
          </div>
          <div class="flex flex-col gap-2">
            <div v-for="(zone, index) in zones" :key="index" class="grid grid-cols-[1fr_5.5rem_auto] gap-2">
              <Input v-model="zone.label" aria-label="عنوان منطقه" />
              <Input v-model.number="zone.score" type="number" min="0" aria-label="امتیاز منطقه" />
              <Button size="icon" variant="ghost" :disabled="zones.length === 1" aria-label="حذف منطقه" @click="zones.splice(index, 1)"><XIcon class="size-4" /></Button>
            </div>
          </div>
        </section>
        <DialogFooter class="gap-2 sm:justify-start">
          <Button :disabled="teams.length < 2 || !firstTeamCode || !secondTeamCode || (miniGame === 'marble_target' && zones.some((zone) => !zone.label || zone.score < 0)) || createMutation.isPending.value" @click="createMatch"><MedalIcon class="size-4" /> {{ createMutation.isPending.value ? 'در حال ساخت…' : 'ساخت مسابقه' }}</Button>
          <Button variant="outline" @click="createOpen = false">انصراف</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="resultOpen">
      <DialogContent class="max-h-[92vh] overflow-y-auto sm:max-w-2xl" dir="rtl">
        <DialogHeader>
          <DialogTitle>{{ match?.status === 'tiebreak' ? 'ثبت نتیجه تساوی‌شکن' : 'ثبت نتیجه فیزیکی' }}</DialogTitle>
          <DialogDescription>نتیجه پس از ثبت نهایی قابل ویرایش نیست. در صورت تساوی، مسابقه به دور بعد می‌رود.</DialogDescription>
        </DialogHeader>
        <template v-if="match?.mini_game === 'coin_near_wall'">
          <div class="grid grid-cols-3 gap-2">
            <Button v-for="player in match.players" :key="player.code" class="h-auto min-h-16 flex-col" :variant="coinOutcome === player.code ? 'default' : 'outline'" @click="coinOutcome = player.code"><TrophyIcon class="size-5" /> {{ player.name }}</Button>
            <Button class="h-auto min-h-16 flex-col" :variant="coinOutcome === 'tie' ? 'destructive' : 'outline'" @click="coinOutcome = 'tie'"><SparklesIcon class="size-5" /> تساوی</Button>
          </div>
          <div class="rounded-xl border p-4">
            <div class="mb-3"><h3 class="text-sm font-bold">فاصله بهترین سکه <span class="text-muted-foreground font-normal">(اختیاری)</span></h3><p class="text-muted-foreground mt-1 text-xs">اگر یکی را وارد می‌کنید، فاصله هر دو طرف را وارد کنید؛ سامانه نتیجه را کنترل می‌کند.</p></div>
            <div class="grid grid-cols-2 gap-3">
              <div><Label for="first-distance">{{ match.players[0].name }} · سانتی‌متر</Label><Input id="first-distance" v-model="firstDistance" class="mt-1.5" type="number" min="0" step="0.01" /></div>
              <div><Label for="second-distance">{{ match.players[1].name }} · سانتی‌متر</Label><Input id="second-distance" v-model="secondDistance" class="mt-1.5" type="number" min="0" step="0.01" /></div>
            </div>
          </div>
        </template>
        <template v-else-if="match">
          <div class="grid gap-4 sm:grid-cols-2">
            <section v-for="(player, playerIndex) in match.players" :key="player.code" class="rounded-xl border p-3">
              <div class="mb-3 flex items-center justify-between"><h3 class="text-sm font-bold">{{ player.name }}</h3><Badge variant="secondary">مجموع {{ (marbleTotals[playerIndex] ?? 0).toLocaleString('fa-IR') }}</Badge></div>
              <div class="flex flex-col gap-3">
                <div v-for="(_, attemptIndex) in playerIndex === 0 ? firstAttempts : secondAttempts" :key="attemptIndex">
                  <p class="text-muted-foreground mb-1.5 text-[0.65rem]">تیله {{ (attemptIndex + 1).toLocaleString('fa-IR') }}</p>
                  <div class="flex flex-wrap gap-1">
                    <Button size="sm" :variant="(playerIndex === 0 ? firstAttempts : secondAttempts)[attemptIndex] === 0 ? 'default' : 'outline'" @click="(playerIndex === 0 ? firstAttempts : secondAttempts)[attemptIndex] = 0">۰</Button>
                    <Button v-for="zone in match.scoring_zones" :key="zone.code" size="sm" :variant="(playerIndex === 0 ? firstAttempts : secondAttempts)[attemptIndex] === zone.code ? 'default' : 'outline'" @click="(playerIndex === 0 ? firstAttempts : secondAttempts)[attemptIndex] = zone.code">{{ zone.score.toLocaleString('fa-IR') }}</Button>
                  </div>
                </div>
              </div>
            </section>
          </div>
          <Button v-if="match.status === 'tiebreak'" variant="outline" size="sm" @click="addTiebreakAttempt"><PlusIcon class="size-3.5" /> افزودن تلاش به هر دو طرف</Button>
          <div v-if="resultReady" class="rounded-lg border p-3 text-center text-sm font-bold">
            <template v-if="marbleTotals[0] === marbleTotals[1]">نتیجه فعلی مساوی است و دور دیگری لازم خواهد بود.</template>
            <template v-else>{{ leadingMarblePlayerName }} با امتیاز بیشتر برنده می‌شود.</template>
          </div>
        </template>
        <DialogFooter class="gap-2 sm:justify-start">
          <Button :disabled="!resultReady || resultMutation.isPending.value" @click="submitResult"><FlagIcon class="size-4" /> {{ resultMutation.isPending.value ? 'در حال ثبت…' : 'ثبت قطعی نتیجه' }}</Button>
          <Button variant="outline" :disabled="resultMutation.isPending.value" @click="resultOpen = false">انصراف</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped>
.olympics-page {
  background:
    radial-gradient(circle at 12% 8%, rgb(43 108 168 / 10%), transparent 24rem),
    radial-gradient(circle at 90% 88%, rgb(230 126 34 / 9%), transparent 25rem),
    radial-gradient(circle, rgb(43 108 168 / 6%) 1px, transparent 1px),
    var(--background);
  background-size: auto, auto, 24px 24px, auto;
}
.event-emblem,.empty-icon { display:grid; flex:none; place-items:center; border-radius:1rem; }
.event-emblem { width:3rem; height:3rem; background:linear-gradient(145deg,#c18a12,#8b5e08); color:white; box-shadow:0 14px 28px -16px rgb(139 94 8 / 80%); }
.empty-icon { width:4rem; height:4rem; background:rgb(193 138 18 / 12%); color:#9a6700; }
.match-scoreboard { display:grid; grid-template-columns:minmax(0,1fr) 4rem minmax(0,1fr); gap:.65rem; align-items:stretch; padding:.75rem; border:1px solid var(--border); border-radius:calc(var(--radius)*1.8); background:color-mix(in oklab,var(--card) 94%,transparent); }
.player-card { display:flex; min-width:0; align-items:center; gap:.75rem; padding:.8rem 1rem; border:1px solid color-mix(in oklab,var(--player-color) 24%,var(--border)); border-radius:calc(var(--radius)*1.35); background:linear-gradient(110deg,color-mix(in oklab,var(--player-color) 8%,var(--card)),var(--card)); }
.player-card:nth-child(1) { grid-column:1; }
.player-card:nth-child(2) { grid-column:3; }
.player-card.is-winner { border-color:#d5a621; box-shadow:0 0 0 2px rgb(213 166 33 / 13%); }
.player-swatch { width:.75rem; height:.75rem; flex:none; border:2px solid white; border-radius:999px; background:var(--player-color); box-shadow:0 0 0 1px color-mix(in oklab,var(--player-color) 70%,#111); }
.versus { grid-column:2; grid-row:1; display:flex; flex-direction:column; align-items:center; justify-content:center; }
.versus strong { font-family:var(--font-secondary); font-size:1.15rem; }
.versus span { color:var(--muted-foreground); font-size:.6rem; }
.arena-card { background:linear-gradient(150deg,color-mix(in oklab,#c18a12 5%,var(--card)),var(--card) 55%,color-mix(in oklab,#2b6ca8 5%,var(--card))); }
.game-mark { display:grid; width:3.5rem; height:3.5rem; flex:none; place-items:center; border-radius:1rem; background:rgb(193 138 18 / 12%); color:#9a6700; }
.game-mark.target-mark { background:rgb(43 108 168 / 10%); color:#2b6ca8; }
.physical-stage { overflow:hidden; border:1px dashed color-mix(in oklab,var(--border) 80%,transparent); border-radius:1.25rem; background:color-mix(in oklab,var(--background) 65%,transparent); }
.coin-lane { position:relative; width:min(100%,32rem); height:11rem; }
.wall { position:absolute; top:0; bottom:0; right:12%; width:.75rem; border-radius:.2rem; background:repeating-linear-gradient(0deg,#64748b 0 14px,#94a3b8 14px 28px); box-shadow:-8px 0 20px -12px #334155; }
.coin { position:absolute; display:grid; width:2.2rem; height:2.2rem; place-items:center; border:2px solid; font-family:var(--font-secondary); font-size:.65rem; font-weight:900; border-radius:999px; animation:coin-hover 2.4s ease-in-out infinite; }
.coin-a { top:calc(var(--n)*2.3rem - 1.5rem); right:calc(24% + var(--n)*9%); border-color:#174c78; background:#2b6ca8; color:white; }
.coin-b { bottom:calc(var(--n)*1.9rem - 1rem); left:calc(8% + var(--n)*10%); border-color:#a84f0b; background:#e67e22; color:white; animation-delay:calc(var(--n)*-.2s); }
.target-stage { position:relative; display:grid; width:15rem; height:15rem; place-items:center; }
.target-ring { display:grid; place-items:center; border:2px solid rgb(43 108 168 / 40%); border-radius:999px; }
.ring-outer { width:14rem; height:14rem; background:rgb(43 108 168 / 5%); }
.ring-middle { width:9.5rem; height:9.5rem; background:rgb(43 108 168 / 8%); }
.ring-center { width:4.8rem; height:4.8rem; background:rgb(43 108 168 / 13%); color:#174c78; }
.marble { position:absolute; width:1.15rem; height:1.15rem; border:2px solid white; border-radius:999px; box-shadow:0 3px 8px rgb(15 23 42 / 25%); animation:marble-orbit 4s ease-in-out infinite; }
.marble-a { top:28%; right:31%; background:#2b6ca8; }
.marble-b { bottom:20%; left:22%; background:#e67e22; animation-delay:-1.8s; }
.operator-panel { display:flex; align-items:center; justify-content:space-between; gap:1rem; padding:1rem; border:1px solid var(--border); border-radius:1rem; background:color-mix(in oklab,var(--card) 88%,transparent); }
.history-card { display:flex; flex-direction:column; }
.result-list { display:flex; flex-direction:column; }
.result-item { position:relative; display:flex; gap:.8rem; padding:.25rem 0 1rem; }
.result-item:not(:last-child)::after { content:''; position:absolute; top:1rem; right:.34rem; bottom:-.05rem; width:1px; background:var(--border); }
.result-dot { z-index:1; width:.75rem; height:.75rem; flex:none; margin-top:.15rem; border:2px solid white; border-radius:999px; background:#2b6ca8; box-shadow:0 0 0 1px #2b6ca8; }
.result-dot.is-tie { background:#e67e22; box-shadow:0 0 0 1px #a84f0b; }
.result-stat { display:flex; flex-direction:column; gap:.2rem; padding:.55rem; border-radius:.6rem; background:var(--muted); }
.result-stat span { color:var(--muted-foreground); font-size:.6rem; }
.result-stat strong { font-family:var(--font-secondary); font-size:.85rem; }
@keyframes coin-hover { 0%,100% { transform:translateY(0) rotate(0); } 50% { transform:translateY(-4px) rotate(7deg); } }
@keyframes marble-orbit { 0%,100% { transform:translate(0,0); } 50% { transform:translate(-7px,5px); } }
@media (min-width:1024px) { .game-layout { overflow:hidden; } .history-card { height:100%; max-height:100%; } }
@media (max-width:640px) { .event-header p { display:none; } .event-emblem { width:2.5rem; height:2.5rem; } .match-scoreboard { grid-template-columns:minmax(0,1fr) 3rem minmax(0,1fr); gap:.35rem; padding:.45rem; } .player-card { padding:.65rem; } .operator-panel { align-items:flex-start; flex-direction:column; } .operator-panel button { width:100%; } }
@media (min-width:1024px) and (max-height:820px) { .event-frame { gap:.65rem; padding-block:.65rem; } .event-header p { display:none; } .physical-stage { min-height:9rem; margin-block:.65rem; } .coin-lane { height:8rem; } .target-stage { scale:.72; } }
@media (prefers-reduced-motion:reduce) { .coin,.marble { animation:none; } }
</style>
