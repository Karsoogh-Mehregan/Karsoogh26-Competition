<script setup lang="ts">
import {
  CircleAlertIcon,
  CrownIcon,
  DicesIcon,
  FlagIcon,
  PlusIcon,
  RefreshCwIcon,
  ShieldIcon,
  SparklesIcon,
  SwordsIcon,
  TargetIcon,
} from '@lucide/vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import TerritoryBoard from '@/components/territory/TerritoryBoard.vue'
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
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { ApiError } from '@/lib/http'
import { playDiceRollSound, playResultSound } from '@/lib/gameAudio'
import {
  useCreateTerritoryGameMutation,
  usePlayTerritoryTurnMutation,
  useTerritoryGameQuery,
  useTerritoryGamesQuery,
} from '@/queries/events'
import type { TerritoryCell, TerritoryGame, TerritoryPlayer, TerritoryTurn } from '@/types/api'

const { me, teams, isMentor } = useActing()
const enabled = () => me.value != null
const gamesQuery = useTerritoryGamesQuery(enabled)
const games = computed(() => gamesQuery.data.value ?? [])
const selectedGameId = ref<number | null>(null)
const gameQuery = useTerritoryGameQuery(selectedGameId, enabled)
const playMutation = usePlayTerritoryTurnMutation()
const createMutation = useCreateTerritoryGameMutation()
const rollingDie = ref(false)
const rollingFace = ref(1)
let rollingTimer: number | null = null

const selectedCell = ref<TerritoryCell | null>(null)
const createOpen = ref(false)
const firstTeamCode = ref('')
const secondTeamCode = ref('')

watch(
  games,
  (rows) => {
    if (!rows.length) {
      selectedGameId.value = null
      return
    }
    if (rows.some((game) => game.id === selectedGameId.value)) return
    const ownCode = me.value?.team?.code
    const preferred =
      rows.find(
        (game) =>
          game.status === 'running' && game.players.some((player) => player.code === ownCode),
      ) ??
      rows.find((game) => game.status === 'running') ??
      rows[0]
    selectedGameId.value = preferred.id
  },
  { immediate: true },
)

watch(selectedGameId, () => {
  selectedCell.value = null
})

const game = computed<TerritoryGame | null>(
  () =>
    gameQuery.data.value ??
    games.value.find((candidate) => candidate.id === selectedGameId.value) ??
    null,
)
const myTeamCode = computed(() => me.value?.team?.code ?? null)
const myPlayer = computed<TerritoryPlayer | null>(() => {
  if (!game.value || !myTeamCode.value) return null
  return game.value.players.find((player) => player.code === myTeamCode.value) ?? null
})
const canAct = computed(
  () =>
    game.value?.status === 'running' &&
    !!myTeamCode.value &&
    game.value.active_player?.code === myTeamCode.value,
)

const selectedKey = computed(() =>
  selectedCell.value ? cellKey(selectedCell.value) : null,
)

const selectableKeys = computed(() => {
  const result = new Set<string>()
  if (!game.value || !myPlayer.value || !canAct.value) return result
  const cells = game.value.board.flat()
  if (!myPlayer.value.has_selected_start) {
    for (const cell of cells) {
      if (!cell.owner && isBoundary(cell)) result.add(cellKey(cell))
    }
    return result
  }

  const mine = new Set(
    cells.filter((cell) => cell.owner?.code === myTeamCode.value).map(cellKey),
  )
  for (const cell of cells) {
    if (cell.owner?.code === myTeamCode.value) continue
    if (orthogonalNeighbours(cell).some((key) => mine.has(key))) result.add(cellKey(cell))
  }
  return result
})

const selectedAction = computed(() => {
  if (!selectedCell.value || !myPlayer.value) return null
  if (!myPlayer.value.has_selected_start) return 'start'
  return selectedCell.value.owner ? 'attack' : 'capture'
})

const loading = computed(
  () => gamesQuery.isPending.value || (selectedGameId.value != null && gameQuery.isPending.value),
)
const refreshing = computed(() => gamesQuery.isFetching.value || gameQuery.isFetching.value)
const errorMessage = computed(() => {
  const error = gameQuery.error.value ?? gamesQuery.error.value
  return error ? messageOf(error) : ''
})

function cellKey(cell: TerritoryCell): string {
  return `${cell.row}:${cell.column}`
}

function isBoundary(cell: TerritoryCell): boolean {
  return cell.row === 0 || cell.row === 4 || cell.column === 0 || cell.column === 4
}

function orthogonalNeighbours(cell: TerritoryCell): string[] {
  return [
    `${cell.row - 1}:${cell.column}`,
    `${cell.row + 1}:${cell.column}`,
    `${cell.row}:${cell.column - 1}`,
    `${cell.row}:${cell.column + 1}`,
  ]
}

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.detail
  if (error instanceof Error) return error.message
  return 'خطا در ارتباط با سرور.'
}

function playerColor(player: TerritoryPlayer, index: number): string {
  return player.color ?? (index === 0 ? '#2b6ca8' : '#e67e22')
}

function turnSegmentStyle(turn: number) {
  if (!game.value) return {}
  const index = (turn - 1) % 2
  const color = playerColor(game.value.players[index], index)
  return {
    '--segment-color': color,
    opacity: turn <= game.value.turns_completed ? '1' : '0.16',
  }
}

function selectCell(cell: TerritoryCell): void {
  selectedCell.value = cell
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

function stopRolling(): void {
  if (rollingTimer != null) window.clearInterval(rollingTimer)
  rollingTimer = null
  rollingDie.value = false
}

onBeforeUnmount(stopRolling)

async function confirmTurn(): Promise<void> {
  if (!game.value || !selectedCell.value) return
  const cell = selectedCell.value
  const needsRoll = selectedAction.value !== 'start'
  if (needsRoll) {
    rollingDie.value = true
    playDiceRollSound()
    rollingTimer = window.setInterval(() => {
      rollingFace.value = (rollingFace.value % 6) + 1
    }, 85)
  }
  try {
    const [updated] = await Promise.all([
      playMutation.mutateAsync({
        gameId: game.value.id,
        row: cell.row,
        column: cell.column,
      }),
      wait(needsRoll ? 1120 : 0),
    ])
    stopRolling()
    if (updated.previous_turn?.dice_result) rollingFace.value = updated.previous_turn.dice_result
    selectedCell.value = null
    announceTurn(updated.previous_turn)
    if (needsRoll && updated.previous_turn) playResultSound(updated.previous_turn.success)
  } catch (error) {
    stopRolling()
    toast.error(messageOf(error))
  }
}

function announceTurn(turn: TerritoryTurn | null): void {
  if (!turn) return
  if (turn.action_type === 'starting_position') {
    toast.success('خانه شروع ثبت شد؛ قلمرو شما شکل گرفت.')
  } else if (turn.success) {
    toast.success(turn.action_type === 'opponent_attack' ? 'حمله موفق بود!' : 'خانه تصرف شد!')
  } else {
    toast.error('تاس با شما یار نبود؛ این نوبت از دست رفت.')
  }
}

async function refresh(): Promise<void> {
  await Promise.all([gamesQuery.refetch(), selectedGameId.value ? gameQuery.refetch() : null])
}

function openCreateDialog(): void {
  firstTeamCode.value = teams.value[0]?.code ?? ''
  secondTeamCode.value = teams.value.find((team) => team.code !== firstTeamCode.value)?.code ?? ''
  createOpen.value = true
}

async function createGame(): Promise<void> {
  if (!firstTeamCode.value || !secondTeamCode.value) return
  try {
    const created = await createMutation.mutateAsync({
      player_one: firstTeamCode.value,
      player_two: secondTeamCode.value,
    })
    selectedGameId.value = created.id
    createOpen.value = false
    toast.success('نبرد تازه ساخته شد.')
  } catch (error) {
    toast.error(messageOf(error))
  }
}

function actionLabel(action: TerritoryTurn['action_type']): string {
  if (action === 'starting_position') return 'انتخاب خانه شروع'
  if (action === 'opponent_attack') return 'حمله به قلمرو حریف'
  return 'تصرف خانه آزاد'
}

function signedScore(value: number): string {
  if (value > 0) return `+${value.toLocaleString('fa-IR')}`
  return value.toLocaleString('fa-IR')
}

const selectedActionTitle = computed(() => {
  if (selectedAction.value === 'start') return 'پایه قلمرو را بساز'
  if (selectedAction.value === 'attack') return 'به قلمرو حریف حمله کن'
  if (selectedAction.value === 'capture') return 'این خانه را تصرف کن'
  return ''
})

const selectedActionHint = computed(() => {
  const cell = selectedCell.value
  if (!cell) return ''
  if (selectedAction.value === 'start') return 'این انتخاب قطعی است، امتیازی ندارد و تاس نمی‌خواهد.'
  if (selectedAction.value === 'attack') {
    return `برای پیروزی باید تاس ${cell.value.toLocaleString('fa-IR')} یا بیشتر بیاید.`
  }
  return `تاس برابر یا بیشتر از ${cell.value.toLocaleString('fa-IR')} خانه را به قلمرو شما اضافه می‌کند.`
})
</script>

<template>
  <div class="event-page h-full overflow-y-auto lg:overflow-hidden" dir="rtl">
    <div class="event-frame mx-auto flex min-h-full w-full max-w-7xl flex-col gap-3 p-3 sm:p-4 lg:h-full lg:min-h-0 xl:p-5">
      <header class="event-header flex shrink-0 flex-wrap items-start justify-between gap-3">
        <div class="flex min-w-0 items-start gap-3">
          <div class="event-emblem">
            <SwordsIcon class="size-6" />
          </div>
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-xl font-black tracking-tight sm:text-2xl">نبرد قلمرو</h1>
              <Badge variant="secondary" class="gap-1 font-normal">
                <SparklesIcon class="size-3" />
                رویداد ۲۰ نوبتی
              </Badge>
            </div>
            <p class="text-muted-foreground mt-1 max-w-xl text-sm">
              قلمروت را از لبه صفحه آغاز کن، با تاس گسترش بده و زمان مناسب به حریف حمله کن.
            </p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            :disabled="refreshing"
            aria-label="بازخوانی نبرد"
            @click="refresh"
          >
            <RefreshCwIcon class="size-4" :class="refreshing && 'animate-spin'" />
            بازخوانی
          </Button>
          <Button v-if="isMentor" size="sm" @click="openCreateDialog">
            <PlusIcon class="size-4" />
            نبرد تازه
          </Button>
        </div>
      </header>

      <nav
        v-if="games.length > 1"
        class="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1"
        aria-label="انتخاب نبرد"
      >
        <Button
          v-for="item in games"
          :key="item.id"
          size="sm"
          class="shrink-0"
          :variant="item.id === selectedGameId ? 'default' : 'outline'"
          @click="selectedGameId = item.id"
        >
          <span
            class="size-2 rounded-full"
            :class="item.status === 'running' ? 'bg-emerald-400' : 'bg-muted-foreground'"
          />
          #{{ item.id }} · {{ item.players[0].name }} / {{ item.players[1].name }}
        </Button>
      </nav>

      <div v-if="loading" class="grid flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Skeleton class="aspect-square w-full max-w-2xl justify-self-center rounded-2xl" />
        <div class="flex flex-col gap-3">
          <Skeleton class="h-36 w-full rounded-xl" />
          <Skeleton class="h-52 w-full rounded-xl" />
        </div>
      </div>

      <Card
        v-else-if="errorMessage"
        class="border-destructive/30 bg-destructive/5 mx-auto w-full max-w-xl"
        role="alert"
      >
        <CardContent class="flex flex-col items-center gap-3 text-center">
          <CircleAlertIcon class="text-destructive size-8" />
          <p class="text-sm">{{ errorMessage }}</p>
          <Button variant="outline" size="sm" @click="refresh">تلاش دوباره</Button>
        </CardContent>
      </Card>

      <Card v-else-if="!game" class="mx-auto w-full max-w-xl border-dashed text-center">
        <CardContent class="flex flex-col items-center gap-3">
          <ShieldIcon class="text-muted-foreground size-10" />
          <div>
            <h2 class="font-bold">هنوز نبردی ساخته نشده است</h2>
            <p class="text-muted-foreground mt-1 text-sm">
              {{ isMentor ? 'دو تیم را انتخاب کنید و اولین نبرد را بسازید.' : 'منتظر بمانید تا مربی یک نبرد برای تیم شما بسازد.' }}
            </p>
          </div>
          <Button v-if="isMentor" @click="openCreateDialog">
            <PlusIcon class="size-4" />
            ساخت نبرد
          </Button>
        </CardContent>
      </Card>

      <template v-else>
        <section class="scoreboard" aria-label="امتیاز و وضعیت نبرد">
          <div
            v-for="(player, index) in game.players"
            :key="player.code"
            class="player-score"
            :class="{
              'is-active': game.active_player?.code === player.code,
              'is-me': myTeamCode === player.code,
            }"
            :style="{ '--player-color': playerColor(player, index) }"
          >
            <div class="flex min-w-0 items-center gap-2">
              <span class="player-swatch" />
              <div class="min-w-0">
                <div class="flex items-center gap-1.5">
                  <strong class="truncate text-sm sm:text-base">{{ player.name }}</strong>
                  <Badge v-if="myTeamCode === player.code" variant="outline" class="h-5 text-[10px]">
                    شما
                  </Badge>
                </div>
                <span class="text-muted-foreground text-[11px]">{{ player.code }}</span>
              </div>
            </div>
            <div class="text-end">
              <span class="block text-2xl leading-none font-black tabular-nums sm:text-3xl">
                {{ player.score.toLocaleString('fa-IR') }}
              </span>
              <span class="text-muted-foreground text-[11px]">امتیاز</span>
            </div>
            <span v-if="game.active_player?.code === player.code" class="active-ribbon">
              نوبت بازی
            </span>
          </div>

          <div class="turn-center">
            <div
              class="turn-orb"
              :class="{
                'is-finished': game.status === 'finished',
                'is-my-turn': canAct,
              }"
            >
              <CrownIcon v-if="game.status === 'finished'" class="size-5" />
              <DicesIcon v-else class="size-5" />
            </div>
            <div class="text-center">
              <p v-if="game.status === 'finished'" class="text-xs font-bold">
                {{ game.is_draw ? 'مساوی' : `برنده: ${game.winner?.name}` }}
              </p>
              <template v-else>
                <p class="text-xs font-bold">نوبت {{ game.turns_completed + 1 }} از ۲۰</p>
                <p class="text-muted-foreground mt-0.5 text-[10px]">
                  {{ canAct ? 'حرکت با شماست' : `در انتظار ${game.active_player?.name}` }}
                </p>
              </template>
            </div>
          </div>

          <div class="turn-track" aria-label="پیشرفت بیست نوبت">
            <span
              v-for="turn in 20"
              :key="turn"
              class="turn-segment"
              :class="turn <= game.turns_completed && 'is-complete'"
              :style="turnSegmentStyle(turn)"
            />
          </div>
        </section>
        <section class="battle-layout grid min-h-0 flex-1 items-start gap-3 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <div class="battle-board min-w-0">
            <div class="board-heading mb-2 flex shrink-0 flex-wrap items-end justify-between gap-2 px-1">
              <div>
                <h2 class="flex items-center gap-2 font-bold">
                  <TargetIcon class="text-muted-foreground size-4" />
                  صفحه نبرد
                </h2>
                <p class="text-muted-foreground mt-0.5 text-xs">
                  <template v-if="canAct">
                    {{ myPlayer?.has_selected_start ? 'خانه‌های درخشان همسایه قلمرو شما هستند.' : 'یک خانه آزاد روی مرز را برای شروع انتخاب کنید.' }}
                  </template>
                  <template v-else-if="game.status === 'finished'">نبرد پایان یافته است.</template>
                  <template v-else>حرکت‌های ممکن در نوبت شما روشن می‌شوند.</template>
                </p>
              </div>
              <Badge v-if="canAct" class="gap-1 bg-sky-700 text-white hover:bg-sky-700">
                <DicesIcon class="size-3" />
                نوبت شما
              </Badge>
              <Badge v-else-if="game.status === 'running'" variant="outline">تماشای زنده</Badge>
            </div>

            <div class="board-stage">
              <TerritoryBoard
                class="battle-map"
                :game="game"
                :selectable-keys="selectableKeys"
                :selected-key="selectedKey"
                :my-team-code="myTeamCode"
                :busy="playMutation.isPending.value"
                @select="selectCell"
              />
            </div>

            <ul class="board-legend mt-2 flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 px-1 text-xs">
              <li v-for="(player, index) in game.players" :key="player.code" class="flex items-center gap-1.5">
                <span class="size-2.5 rounded-full" :style="{ backgroundColor: playerColor(player, index) }" />
                قلمرو {{ player.name }}
              </li>
              <li class="text-muted-foreground flex items-center gap-1.5">
                <span class="size-2.5 rounded-full border bg-white" /> خانه آزاد
              </li>
              <li v-if="canAct" class="text-sky-700 flex items-center gap-1.5 font-medium">
                <span class="size-2.5 rounded-full border-2 border-sky-700" /> حرکت مجاز
              </li>
            </ul>
          </div>

          <aside class="battle-sidebar flex min-w-0 flex-col gap-3">
            <Card v-if="selectedCell" class="action-card gap-4 border-sky-700/30 py-5">
              <CardHeader class="gap-2 px-5">
                <div class="flex items-center justify-between gap-3">
                  <div class="action-icon"><TargetIcon class="size-5" /></div>
                  <Badge variant="outline" class="font-normal tabular-nums">
                    ردیف {{ selectedCell.row + 1 }} · ستون {{ selectedCell.column + 1 }}
                  </Badge>
                </div>
                <CardTitle class="text-base">{{ selectedActionTitle }}</CardTitle>
              </CardHeader>
              <CardContent class="flex flex-col gap-4 px-5">
                <div v-if="rollingDie" class="dice-roll-stage" aria-live="polite">
                  <div class="rolling-die" aria-hidden="true">{{ rollingFace.toLocaleString('fa-IR') }}</div>
                  <div>
                    <strong>تاس در حال چرخش است…</strong>
                    <span>نتیجه از سرور می‌آید</span>
                  </div>
                </div>
                <div v-else class="selected-value">
                  <span class="text-muted-foreground text-xs">ارزش خانه</span>
                  <strong class="font-secondary text-4xl leading-none tabular-nums">
                    {{ selectedCell.value.toLocaleString('fa-IR') }}
                  </strong>
                </div>
                <p class="text-muted-foreground text-xs leading-6">{{ selectedActionHint }}</p>
                <div class="grid grid-cols-2 gap-2">
                  <Button variant="outline" :disabled="playMutation.isPending.value" @click="selectedCell = null">
                    انصراف
                  </Button>
                  <Button :disabled="playMutation.isPending.value" @click="confirmTurn">
                    <DicesIcon
                      v-if="selectedAction !== 'start'"
                      class="size-4"
                      :class="playMutation.isPending.value && 'animate-spin'"
                    />
                    <FlagIcon v-else class="size-4" />
                    {{ playMutation.isPending.value ? 'در حال ثبت…' : selectedAction === 'start' ? 'ثبت شروع' : 'تاس بریز' }}
                  </Button>
                </div>
              </CardContent>
            </Card>

            <Card v-else class="status-card gap-4 py-5">
              <CardHeader class="px-5">
                <div class="status-illustration" :class="canAct && 'is-live'">
                  <CrownIcon v-if="game.status === 'finished'" class="size-7" />
                  <TargetIcon v-else-if="canAct" class="size-7" />
                  <ShieldIcon v-else class="size-7" />
                </div>
              </CardHeader>
              <CardContent class="px-5 text-center">
                <h3 class="font-bold">
                  <template v-if="game.status === 'finished'">
                    {{ game.is_draw ? 'نبرد بدون برنده تمام شد' : `${game.winner?.name} پیروز شد` }}
                  </template>
                  <template v-else-if="canAct">حرکت بعدی با شماست</template>
                  <template v-else-if="myPlayer">در انتظار حرکت حریف</template>
                  <template v-else>نمای تماشاگر</template>
                </h3>
                <p class="text-muted-foreground mt-2 text-xs leading-6">
                  <template v-if="canAct">یکی از خانه‌های روشن را انتخاب کنید تا جزئیات حرکت را ببینید.</template>
                  <template v-else-if="game.status === 'running'">صفحه هر چند ثانیه تازه می‌شود و نتیجه حرکت بعدی را نشان می‌دهد.</template>
                  <template v-else>نتیجه نهایی و آخرین حرکت در همین صفحه باقی می‌ماند.</template>
                </p>
              </CardContent>
            </Card>

            <Card v-if="game.previous_turn" class="gap-4 py-5">
              <CardHeader class="px-5">
                <div class="flex items-center justify-between gap-2">
                  <CardTitle class="text-sm">آخرین حرکت</CardTitle>
                  <Badge :variant="game.previous_turn.success ? 'secondary' : 'destructive'">
                    {{ game.previous_turn.success ? 'موفق' : 'ناموفق' }}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent class="flex flex-col gap-4 px-5 text-xs">
                <div class="flex items-center justify-between gap-3">
                  <div>
                    <p class="font-semibold">{{ game.previous_turn.acting_player.name }}</p>
                    <p class="text-muted-foreground mt-1">
                      {{ actionLabel(game.previous_turn.action_type) }}
                    </p>
                  </div>
                  <div v-if="game.previous_turn.dice_result" class="dice-result">
                    <DicesIcon class="size-4" />
                    <strong>{{ game.previous_turn.dice_result.toLocaleString('fa-IR') }}</strong>
                  </div>
                  <div v-else class="dice-result"><FlagIcon class="size-4" /></div>
                </div>
                <div class="grid grid-cols-3 gap-2 text-center">
                  <div class="result-stat">
                    <span>خانه</span>
                    <strong>
                      {{ game.previous_turn.target.row + 1 }}·{{ game.previous_turn.target.column + 1 }}
                    </strong>
                  </div>
                  <div class="result-stat">
                    <span>ارزش</span>
                    <strong>{{ game.previous_turn.target_value.toLocaleString('fa-IR') }}</strong>
                  </div>
                  <div class="result-stat">
                    <span>امتیاز</span>
                    <strong
                      :class="game.previous_turn.attacker_score_change >= 0 ? 'text-emerald-700' : 'text-destructive'"
                    >
                      {{ signedScore(game.previous_turn.attacker_score_change) }}
                    </strong>
                  </div>
                </div>
                <p
                  v-if="game.previous_turn.defender_score_change"
                  class="border-destructive/20 bg-destructive/5 rounded-lg border p-2.5 text-center"
                >
                  حریف {{ signedScore(game.previous_turn.defender_score_change) }} امتیاز از دست داد.
                </p>
              </CardContent>
            </Card>

            <Card v-else class="gap-3 border-dashed py-5">
              <CardContent class="flex items-center gap-3 px-5">
                <div class="bg-muted grid size-9 shrink-0 place-items-center rounded-full">
                  <DicesIcon class="text-muted-foreground size-4" />
                </div>
                <div>
                  <p class="text-sm font-semibold">هنوز حرکتی انجام نشده</p>
                  <p class="text-muted-foreground mt-1 text-xs">نتیجه هر نوبت اینجا نمایش داده می‌شود.</p>
                </div>
              </CardContent>
            </Card>
          </aside>
        </section>
      </template>
    </div>

    <Dialog v-model:open="createOpen">
      <DialogContent class="sm:max-w-lg" dir="rtl">
        <DialogHeader>
          <DialogTitle>ساخت نبرد تازه</DialogTitle>
          <DialogDescription>
            بازیکن اول نبرد را آغاز می‌کند. هر تیم در این مسابقه امتیاز مستقل دارد.
          </DialogDescription>
        </DialogHeader>

        <p v-if="teams.length < 2" class="text-destructive py-4 text-sm">
          برای ساخت نبرد حداقل دو تیم لازم است.
        </p>
        <div v-else class="grid min-h-0 grid-cols-2 gap-3">
          <section class="flex min-w-0 flex-col gap-2">
            <h3 class="flex items-center gap-1.5 text-xs font-bold">
              <span class="size-2 rounded-full bg-[#2b6ca8]" /> بازیکن اول
            </h3>
            <div class="flex max-h-64 flex-col gap-1.5 overflow-y-auto pe-1">
              <Button
                v-for="team in teams"
                :key="`first-${team.code}`"
                size="sm"
                class="h-auto min-h-9 justify-start whitespace-normal"
                :variant="firstTeamCode === team.code ? 'default' : 'outline'"
                :disabled="secondTeamCode === team.code"
                @click="firstTeamCode = team.code"
              >
                <span
                  class="size-2 shrink-0 rounded-full border"
                  :style="{ backgroundColor: team.color ?? '#2b6ca8' }"
                />
                <span class="truncate">{{ team.name }}</span>
              </Button>
            </div>
          </section>
          <section class="flex min-w-0 flex-col gap-2">
            <h3 class="flex items-center gap-1.5 text-xs font-bold">
              <span class="size-2 rounded-full bg-[#e67e22]" /> بازیکن دوم
            </h3>
            <div class="flex max-h-64 flex-col gap-1.5 overflow-y-auto pe-1">
              <Button
                v-for="team in teams"
                :key="`second-${team.code}`"
                size="sm"
                class="h-auto min-h-9 justify-start whitespace-normal"
                :variant="secondTeamCode === team.code ? 'default' : 'outline'"
                :disabled="firstTeamCode === team.code"
                @click="secondTeamCode = team.code"
              >
                <span
                  class="size-2 shrink-0 rounded-full border"
                  :style="{ backgroundColor: team.color ?? '#e67e22' }"
                />
                <span class="truncate">{{ team.name }}</span>
              </Button>
            </div>
          </section>
        </div>

        <DialogFooter class="gap-2 sm:justify-start">
          <Button
            :disabled="
              teams.length < 2 ||
              !firstTeamCode ||
              !secondTeamCode ||
              firstTeamCode === secondTeamCode ||
              createMutation.isPending.value
            "
            @click="createGame"
          >
            <SwordsIcon class="size-4" />
            {{ createMutation.isPending.value ? 'در حال ساخت…' : 'آغاز نبرد' }}
          </Button>
          <Button variant="outline" @click="createOpen = false">انصراف</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped>
.event-page {
  background:
    radial-gradient(circle at 12% 8%, rgb(43 108 168 / 9%), transparent 26rem),
    radial-gradient(circle at 92% 92%, rgb(230 126 34 / 7%), transparent 24rem),
    radial-gradient(circle, rgb(43 108 168 / 7%) 1px, transparent 1px),
    var(--background);
  background-size: auto, auto, 24px 24px, auto;
}

.battle-board {
  display: flex;
  flex-direction: column;
}

.board-stage {
  display: flex;
  min-height: 0;
  flex: 1;
  align-items: center;
  justify-content: center;
}

@media (min-width: 1024px) {
  .battle-layout {
    height: 100%;
    overflow: hidden;
  }

  .battle-board,
  .battle-sidebar {
    height: 100%;
    min-height: 0;
  }

  .battle-map {
    width: auto;
    height: 100%;
    max-width: 100%;
    max-height: 100%;
    aspect-ratio: 1;
  }

  .battle-sidebar {
    overflow-y: auto;
    padding-inline-end: 0.2rem;
  }
}

@media (max-width: 1023px) {
  .event-frame {
    max-width: 48rem;
  }

  .battle-map {
    max-width: 40rem;
    margin-inline: auto;
  }
}

.event-emblem {
  display: grid;
  width: 3rem;
  height: 3rem;
  flex: none;
  place-items: center;
  border: 1px solid rgb(43 108 168 / 25%);
  border-radius: 1rem;
  background: linear-gradient(145deg, #2b6ca8, #174c78);
  color: white;
  box-shadow: 0 14px 28px -16px rgb(43 108 168 / 85%);
}

.scoreboard {
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(4.5rem, 10vw, 7rem) minmax(0, 1fr);
  gap: 0.65rem;
  align-items: stretch;
  padding: 0.75rem;
  border: 1px solid var(--border);
  border-radius: calc(var(--radius) * 1.8);
  background: color-mix(in oklab, var(--card) 94%, transparent);
  box-shadow: 0 18px 50px -38px rgb(15 23 42 / 55%);
  backdrop-filter: blur(8px);
}

.player-score {
  position: relative;
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  overflow: hidden;
  padding: 0.8rem 0.9rem;
  border: 1px solid color-mix(in oklab, var(--player-color) 24%, var(--border));
  border-radius: calc(var(--radius) * 1.35);
  background: linear-gradient(
    110deg,
    color-mix(in oklab, var(--player-color) 9%, var(--card)),
    var(--card) 70%
  );
  transition: border-color 180ms ease, box-shadow 180ms ease;
}

.player-score:nth-of-type(1) { grid-column: 1; }
.player-score:nth-of-type(2) { grid-column: 3; }
.player-score.is-active {
  border-color: color-mix(in oklab, var(--player-color) 72%, #111 28%);
  box-shadow: 0 0 0 2px color-mix(in oklab, var(--player-color) 16%, transparent);
}
.player-swatch { width: 0.75rem; height: 0.75rem; flex: none; border: 2px solid white; border-radius: 999px; background: var(--player-color); box-shadow: 0 0 0 1px color-mix(in oklab, var(--player-color) 70%, #111 30%); }
.active-ribbon { position: absolute; inset-inline-start: 0; inset-block-end: 0; padding: 0.15rem 0.55rem; border-start-end-radius: 0.5rem; background: var(--player-color); color: white; font-size: 0.6rem; font-weight: 700; }

.turn-center { grid-column: 2; grid-row: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.4rem; }
.turn-orb { display: grid; width: 2.5rem; height: 2.5rem; place-items: center; border: 1px solid var(--border); border-radius: 999px; background: var(--muted); color: var(--muted-foreground); }
.turn-orb.is-my-turn { border-color: rgb(43 108 168 / 40%); background: rgb(43 108 168 / 12%); color: #2b6ca8; animation: orb-pulse 1.8s ease-in-out infinite; }
.turn-orb.is-finished { border-color: rgb(217 168 38 / 35%); background: rgb(251 191 36 / 15%); color: #9a6700; }
.turn-track { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(20, minmax(0, 1fr)); gap: 0.22rem; padding-inline: 0.25rem; }
.turn-segment { height: 0.3rem; border-radius: 999px; background: var(--segment-color); transition: opacity 240ms ease, transform 240ms ease; }
.turn-segment.is-complete { transform: scaleY(1.15); }

.action-card { background: linear-gradient(160deg, color-mix(in oklab, #2b6ca8 7%, var(--card)), var(--card) 58%); }
.action-icon { display: grid; width: 2.5rem; height: 2.5rem; place-items: center; border-radius: 0.8rem; background: #2b6ca8; color: white; box-shadow: 0 10px 24px -14px rgb(43 108 168 / 90%); }
.selected-value { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0.85rem 1rem; border: 1px solid var(--border); border-radius: 0.8rem; background: color-mix(in oklab, var(--background) 72%, transparent); }
.dice-roll-stage { display:flex; min-height:5.2rem; align-items:center; justify-content:center; gap:1rem; overflow:hidden; border:1px solid rgb(43 108 168 / 28%); border-radius:.9rem; background:radial-gradient(circle at 30% 30%,rgb(255 255 255 / 92%),rgb(43 108 168 / 10%)); }
.dice-roll-stage > div:last-child { display:flex; flex-direction:column; gap:.2rem; }
.dice-roll-stage span { color:var(--muted-foreground); font-size:.65rem; }
.rolling-die { display:grid; width:3.4rem; height:3.4rem; place-items:center; border:2px solid #1d4f76; border-radius:.8rem; background:white; color:#174c78; box-shadow:0 12px 20px -14px rgb(23 76 120 / 90%),inset 0 -4px 0 rgb(43 108 168 / 12%); font-family:var(--font-secondary); font-size:1.65rem; font-weight:900; animation:dice-tumble 420ms linear infinite,dice-bounce 210ms ease-in-out infinite alternate; }
.font-secondary { font-family: var(--font-secondary); }
.status-card { background: linear-gradient(160deg, var(--card), color-mix(in oklab, #2b6ca8 5%, var(--card))); }
.status-illustration { display: grid; width: 4rem; height: 4rem; margin-inline: auto; place-items: center; border: 1px solid var(--border); border-radius: 1.25rem; background: var(--muted); color: var(--muted-foreground); transform: rotate(-3deg); }
.status-illustration.is-live { border-color: rgb(43 108 168 / 25%); background: rgb(43 108 168 / 10%); color: #2b6ca8; animation: target-float 2.6s ease-in-out infinite; }
.dice-result { display: flex; min-width: 3.25rem; align-items: center; justify-content: center; gap: 0.35rem; padding: 0.55rem 0.7rem; border: 1px solid rgb(43 108 168 / 20%); border-radius: 0.75rem; background: rgb(43 108 168 / 8%); color: #2b6ca8; font-family: var(--font-secondary); font-size: 1rem; }
.result-stat { display: flex; flex-direction: column; gap: 0.25rem; padding: 0.6rem 0.35rem; border-radius: 0.65rem; background: var(--muted); }
.result-stat span { color: var(--muted-foreground); font-size: 0.65rem; }
.result-stat strong { font-family: var(--font-secondary); font-size: 0.85rem; }

@keyframes orb-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgb(43 108 168 / 0%); }
  50% { box-shadow: 0 0 0 7px rgb(43 108 168 / 10%); }
}
@keyframes target-float {
  0%, 100% { transform: rotate(-3deg) translateY(0); }
  50% { transform: rotate(2deg) translateY(-4px); }
}
@keyframes dice-tumble { to { transform:rotate(360deg) rotateY(180deg); } }
@keyframes dice-bounce { to { translate:0 -.35rem; box-shadow:0 20px 22px -16px rgb(23 76 120 / 80%),inset 0 -4px 0 rgb(43 108 168 / 12%); } }

@media (max-width: 640px) {
  .event-header {
    align-items: center;
  }
  .event-header p {
    display: none;
  }
  .event-emblem {
    width: 2.5rem;
    height: 2.5rem;
    border-radius: 0.8rem;
  }
  .scoreboard { grid-template-columns: minmax(0, 1fr) 4rem minmax(0, 1fr); gap: 0.35rem; padding: 0.45rem; }
  .player-score { flex-direction: column; align-items: stretch; padding: 0.65rem; }
  .player-score > :last-child { text-align: start; }
  .turn-orb { width: 2.1rem; height: 2.1rem; }
}

@media (min-width: 1024px) and (max-height: 820px) {
  .event-frame {
    gap: 0.55rem;
    padding-block: 0.65rem;
  }
  .event-header p,
  .board-heading p {
    display: none;
  }
  .event-emblem {
    width: 2.4rem;
    height: 2.4rem;
    border-radius: 0.75rem;
  }
  .scoreboard {
    gap: 0.4rem;
    padding: 0.45rem;
  }
  .player-score {
    padding: 0.5rem 0.7rem;
  }
  .board-heading,
  .board-legend {
    margin-block: 0.25rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .turn-orb.is-my-turn,
  .status-illustration.is-live,
  .rolling-die { animation: none; }
}
</style>
