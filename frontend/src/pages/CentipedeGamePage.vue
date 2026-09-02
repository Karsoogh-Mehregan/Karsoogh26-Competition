<script setup lang="ts">
import {
  ArrowLeftIcon,
  CircleAlertIcon,
  CoinsIcon,
  CrownIcon,
  FootprintsIcon,
  HandIcon,
  PlusIcon,
  RefreshCwIcon,
  RouteIcon,
  ShieldIcon,
  SparklesIcon,
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
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { formatBalance } from '@/lib/format'
import { playCoinDropSound, playResultSound } from '@/lib/gameAudio'
import { ApiError } from '@/lib/http'
import {
  useCentipedeGameQuery,
  useCentipedeGamesQuery,
  useCreateCentipedeGameMutation,
  usePlayCentipedeActionMutation,
} from '@/queries/events'
import type { CentipedeAction, CentipedeGame, CentipedePlayer } from '@/types/api'

const { me, teams, isMentor } = useActing()
const enabled = () => me.value != null
const gamesQuery = useCentipedeGamesQuery(enabled)
const games = computed(() => gamesQuery.data.value ?? [])
const selectedGameId = ref<number | null>(null)
const gameQuery = useCentipedeGameQuery(selectedGameId, enabled)
const playMutation = usePlayCentipedeActionMutation()
const createMutation = useCreateCentipedeGameMutation()
const takeOpen = ref(false)
const createOpen = ref(false)
const firstTeamCode = ref('')
const secondTeamCode = ref('')
const actionPulse = ref<CentipedeAction | null>(null)

watch(
  games,
  (rows) => {
    if (!rows.length) {
      selectedGameId.value = null
      return
    }
    if (rows.some((item) => item.id === selectedGameId.value)) return
    const ownCode = me.value?.team?.code
    const preferred =
      rows.find(
        (item) => item.status === 'active' && item.players.some((player) => player.code === ownCode),
      ) ??
      rows.find((item) => item.status === 'active') ??
      rows[0]
    selectedGameId.value = preferred.id
  },
  { immediate: true },
)

const game = computed<CentipedeGame | null>(
  () =>
    gameQuery.data.value ??
    games.value.find((item) => item.id === selectedGameId.value) ??
    null,
)
const myCode = computed(() => me.value?.team?.code ?? null)
const myPlayer = computed<CentipedePlayer | null>(() => {
  if (!game.value || !myCode.value) return null
  return game.value.players.find((player) => player.code === myCode.value) ?? null
})
const canAct = computed(
  () =>
    game.value?.status === 'active' &&
    !!myPlayer.value &&
    game.value.active_player?.code === myCode.value,
)
const winnerPayout = computed(
  () => game.value?.players.find((player) => player.code === game.value?.winner?.code)?.final_payout ?? 0,
)
const loading = computed(
  () => gamesQuery.isPending.value || (selectedGameId.value != null && gameQuery.isPending.value),
)
const refreshing = computed(() => gamesQuery.isFetching.value || gameQuery.isFetching.value)
const errorMessage = computed(() => {
  const error = gameQuery.error.value ?? gamesQuery.error.value
  return error ? messageOf(error) : ''
})

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.detail
  if (error instanceof Error) return error.message
  return 'خطا در ارتباط با سرور.'
}

function playerColor(player: CentipedePlayer, index: number): string {
  return player.color ?? (index === 0 ? '#2b6ca8' : '#e67e22')
}

function actionLabel(action: CentipedeAction): string {
  return action === 'take' ? 'برداشت' : 'ادامه'
}

async function refresh(): Promise<void> {
  await Promise.all([gamesQuery.refetch(), selectedGameId.value ? gameQuery.refetch() : null])
}

async function submitAction(action: CentipedeAction): Promise<void> {
  if (!game.value || !canAct.value) return
  const previousRound = game.value.round_number
  actionPulse.value = action
  if (action === 'take') playCoinDropSound()
  try {
    const updated = await playMutation.mutateAsync({ gameId: game.value.id, action })
    takeOpen.value = false
    if (action === 'take') {
      playResultSound(true)
      toast.success(`برداشت ثبت شد؛ ${formatBalance(myPlayer.value?.current_reward ?? 0)} گلوریوم پرداخت شد.`)
    } else if (updated.round_number > previousRound) {
      playResultSound(true)
      toast.success('هر دو بازیکن ادامه دادند؛ جایزه‌ها دو برابر شد!')
    } else {
      toast.success('ادامه ثبت شد؛ نوبت به بازیکن بعدی رسید.')
    }
  } catch (error) {
    toast.error(messageOf(error))
  } finally {
    window.setTimeout(() => (actionPulse.value = null), 450)
  }
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
    toast.success('بازی هزارپای تازه آغاز شد.')
  } catch (error) {
    toast.error(messageOf(error))
  }
}
</script>

<template>
  <div class="centipede-page h-full min-h-0 overflow-y-auto" dir="rtl">
    <div class="event-frame mx-auto flex min-h-full w-full max-w-7xl flex-col gap-4 p-4 sm:p-6">
      <header class="event-header flex items-center justify-between gap-3">
        <div class="flex min-w-0 items-center gap-3">
          <div class="event-emblem"><RouteIcon class="size-6" /></div>
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-xl font-black sm:text-2xl">بازی هزارپا</h1>
              <Badge variant="outline">دو بازیکن</Badge>
            </div>
            <p class="text-muted-foreground mt-1 text-xs sm:text-sm">
              جلو بروید تا جایزه‌ها دو برابر شوند؛ یا سهم خودتان را بردارید و بازی را تمام کنید.
            </p>
          </div>
        </div>
        <div class="flex shrink-0 gap-2">
          <Button size="icon" variant="outline" :disabled="refreshing" aria-label="تازه‌سازی" @click="refresh">
            <RefreshCwIcon class="size-4" :class="refreshing && 'animate-spin'" />
          </Button>
          <Button v-if="isMentor" class="hidden sm:flex" @click="openCreateDialog">
            <PlusIcon class="size-4" /> بازی تازه
          </Button>
        </div>
      </header>

      <div v-if="games.length > 1" class="flex gap-2 overflow-x-auto pb-1">
        <Button
          v-for="item in games"
          :key="item.id"
          size="sm"
          class="shrink-0"
          :variant="selectedGameId === item.id ? 'default' : 'outline'"
          @click="selectedGameId = item.id"
        >
          بازی {{ item.id.toLocaleString('fa-IR') }} · دور {{ item.round_number.toLocaleString('fa-IR') }}
        </Button>
      </div>

      <div v-if="loading" class="grid flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Skeleton class="min-h-96 rounded-2xl" />
        <Skeleton class="min-h-72 rounded-2xl" />
      </div>

      <Card v-else-if="errorMessage" class="m-auto max-w-lg border-destructive/30">
        <CardContent class="flex flex-col items-center gap-3 p-8 text-center">
          <CircleAlertIcon class="text-destructive size-9" />
          <p class="font-bold">بازی بارگیری نشد</p>
          <p class="text-muted-foreground text-sm">{{ errorMessage }}</p>
          <Button variant="outline" @click="refresh">دوباره تلاش کن</Button>
        </CardContent>
      </Card>

      <Card v-else-if="!game" class="m-auto max-w-lg border-dashed">
        <CardContent class="flex flex-col items-center gap-4 p-10 text-center">
          <div class="empty-icon"><FootprintsIcon class="size-8" /></div>
          <div>
            <h2 class="font-bold">هنوز بازی‌ای ساخته نشده</h2>
            <p class="text-muted-foreground mt-2 text-sm">
              مربی پس از تعیین ترتیب بازیکنان با سنگ، کاغذ، قیچی بازی را می‌سازد.
            </p>
          </div>
          <Button v-if="isMentor" @click="openCreateDialog"><PlusIcon class="size-4" /> ساخت بازی</Button>
        </CardContent>
      </Card>

      <template v-else>
        <section class="reward-board">
          <article
            v-for="(player, index) in game.players"
            :key="player.code"
            class="player-reward"
            :class="{
              'is-active': game.active_player?.code === player.code,
              'is-winner': game.winner?.code === player.code,
              'is-lost': game.status === 'finished' && game.winner?.code !== player.code,
            }"
            :style="{ '--player-color': playerColor(player, index) }"
          >
            <div class="flex min-w-0 items-center gap-2">
              <span class="player-swatch" />
              <div class="min-w-0">
                <p class="truncate text-sm font-bold">{{ player.name }}</p>
                <p class="text-muted-foreground text-[0.65rem]">بازیکن {{ player.position.toLocaleString('fa-IR') }}</p>
              </div>
            </div>
            <div class="text-end">
              <p class="reward-number">{{ formatBalance(player.current_reward) }}</p>
              <p class="text-muted-foreground flex items-center justify-end gap-1 text-[0.65rem]"><CoinsIcon class="size-3" /> گلوریوم</p>
            </div>
            <span v-if="game.active_player?.code === player.code" class="active-ribbon">نوبت تصمیم</span>
            <span v-else-if="game.winner?.code === player.code" class="winner-ribbon"><CrownIcon class="size-3" /> برنده</span>
          </article>

          <div class="round-center">
            <span class="text-muted-foreground text-[0.65rem]">دور</span>
            <strong>{{ game.round_number.toLocaleString('fa-IR') }}</strong>
          </div>

          <div class="centipede-track" aria-hidden="true">
            <span
              v-for="step in Math.min(Math.max(game.round_number + 4, 7), 12)"
              :key="step"
              class="track-node"
              :class="step <= game.round_number && 'is-reached'"
            >
              <span v-if="step === game.round_number" class="track-head"><SparklesIcon class="size-3" /></span>
            </span>
          </div>
        </section>

        <section class="game-layout grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_21rem]">
          <Card class="decision-stage min-h-0 overflow-hidden">
            <CardContent class="flex h-full min-h-0 flex-col items-center justify-center p-5 text-center sm:p-8">
              <template v-if="game.status === 'finished'">
                <div class="result-crown"><CrownIcon class="size-8" /></div>
                <Badge class="mt-4" variant="secondary">بازی تمام شد</Badge>
                <h2 class="mt-3 text-xl font-black sm:text-2xl">{{ game.winner?.name }} برداشت کرد</h2>
                <p class="text-muted-foreground mt-2 max-w-md text-sm leading-7">
                  {{ formatBalance(winnerPayout) }} گلوریوم به موجودی برنده اضافه شد و سهم بازیکن دیگر از بین رفت.
                </p>
              </template>

              <template v-else-if="canAct">
                <div class="decision-orb"><HandIcon class="size-7" /></div>
                <Badge class="mt-4">نوبت شماست</Badge>
                <h2 class="mt-3 text-xl font-black sm:text-2xl">ریسک می‌کنید یا برمی‌دارید؟</h2>
                <p class="text-muted-foreground mt-2 max-w-lg text-sm leading-7">
                  با برداشت، همین حالا {{ formatBalance(myPlayer?.current_reward ?? 0) }} گلوریوم می‌گیرید. با ادامه، نوبت به حریف می‌رسد؛ اگر او هم ادامه دهد، هر دو جایزه دو برابر می‌شوند.
                </p>
                <div class="mt-6 grid w-full max-w-xl gap-3 sm:grid-cols-2">
                  <Button
                    size="lg"
                    variant="outline"
                    class="continue-button h-auto min-h-16 flex-col gap-1"
                    :class="actionPulse === 'continue' && 'is-pulsing'"
                    :disabled="playMutation.isPending.value"
                    @click="submitAction('continue')"
                  >
                    <span class="flex items-center gap-2 font-black"><FootprintsIcon class="size-5" /> ادامه می‌دهم</span>
                    <span class="text-muted-foreground text-[0.65rem] font-normal">شانس دو برابر شدن جایزه</span>
                  </Button>
                  <Button
                    size="lg"
                    class="take-button h-auto min-h-16 flex-col gap-1"
                    :class="actionPulse === 'take' && 'is-pulsing'"
                    :disabled="playMutation.isPending.value"
                    @click="takeOpen = true"
                  >
                    <span class="flex items-center gap-2 font-black"><CoinsIcon class="size-5" /> برداشت می‌کنم</span>
                    <span class="text-[0.65rem] font-normal opacity-80">پایان فوری بازی</span>
                  </Button>
                </div>
              </template>

              <template v-else>
                <div class="waiting-orb"><ShieldIcon class="size-7" /></div>
                <Badge class="mt-4" variant="outline">در انتظار تصمیم</Badge>
                <h2 class="mt-3 text-xl font-black">نوبت {{ game.active_player?.name }}</h2>
                <p class="text-muted-foreground mt-2 max-w-md text-sm leading-7">
                  {{ myPlayer ? 'پس از ثبت تصمیم حریف، صفحه خودکار تازه می‌شود.' : 'شما این بازی را در نمای تماشاگر می‌بینید.' }}
                </p>
              </template>
            </CardContent>
          </Card>

          <Card class="history-card min-h-0 overflow-hidden">
            <CardHeader class="border-b px-5 py-4">
              <div class="flex items-center justify-between gap-2">
                <CardTitle class="text-sm">مسیر تصمیم‌ها</CardTitle>
                <Badge variant="outline">{{ game.actions_completed.toLocaleString('fa-IR') }} تصمیم</Badge>
              </div>
            </CardHeader>
            <CardContent class="history-content min-h-0 overflow-y-auto p-4">
              <div v-if="!game.history.length" class="flex h-full min-h-40 flex-col items-center justify-center text-center">
                <RouteIcon class="text-muted-foreground/50 size-7" />
                <p class="mt-3 text-sm font-bold">مسیر هنوز آغاز نشده</p>
                <p class="text-muted-foreground mt-1 text-xs">اولین تصمیم اینجا ثبت می‌شود.</p>
              </div>
              <ol v-else class="decision-list">
                <li v-for="decision in [...game.history].reverse()" :key="decision.sequence" class="decision-item">
                  <span class="decision-dot" :class="decision.action === 'take' && 'is-take'" />
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center justify-between gap-2">
                      <p class="truncate text-xs font-bold">{{ decision.actor.name }}</p>
                      <Badge :variant="decision.action === 'take' ? 'default' : 'outline'" class="text-[0.6rem]">
                        {{ actionLabel(decision.action) }}
                      </Badge>
                    </div>
                    <div class="text-muted-foreground mt-1 flex items-center justify-between text-[0.65rem]">
                      <span>دور {{ decision.round_number.toLocaleString('fa-IR') }}</span>
                      <span>{{ formatBalance(decision.displayed_reward) }} گلوریوم</span>
                    </div>
                  </div>
                </li>
              </ol>
            </CardContent>
          </Card>
        </section>
      </template>
    </div>

    <Dialog v-model:open="takeOpen">
      <DialogContent class="sm:max-w-md" dir="rtl">
        <DialogHeader>
          <DialogTitle>جایزه را بردارید؟</DialogTitle>
          <DialogDescription>
            با تأیید، بازی همان لحظه تمام می‌شود. شما {{ formatBalance(myPlayer?.current_reward ?? 0) }} گلوریوم می‌گیرید و حریف چیزی دریافت نمی‌کند.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter class="gap-2 sm:justify-start">
          <Button :disabled="playMutation.isPending.value" @click="submitAction('take')">
            <CoinsIcon class="size-4" /> {{ playMutation.isPending.value ? 'در حال ثبت…' : 'بله، برداشت کن' }}
          </Button>
          <Button variant="outline" :disabled="playMutation.isPending.value" @click="takeOpen = false">برگشت</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="createOpen">
      <DialogContent class="sm:max-w-lg" dir="rtl">
        <DialogHeader>
          <DialogTitle>ساخت بازی هزارپا</DialogTitle>
          <DialogDescription>
            ابتدا سنگ، کاغذ، قیچی را بیرون نرم‌افزار انجام دهید؛ برنده را بازیکن اول بگذارید تا نخستین تصمیم را بگیرد.
          </DialogDescription>
        </DialogHeader>
        <p v-if="teams.length < 2" class="text-destructive py-4 text-sm">برای ساخت بازی حداقل دو تیم لازم است.</p>
        <div v-else class="grid min-h-0 grid-cols-2 gap-3">
          <section class="flex min-w-0 flex-col gap-2">
            <h3 class="text-xs font-bold">بازیکن اول · شروع‌کننده</h3>
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
                <span class="size-2 shrink-0 rounded-full border" :style="{ backgroundColor: team.color ?? '#2b6ca8' }" />
                <span class="truncate">{{ team.name }}</span>
              </Button>
            </div>
          </section>
          <section class="flex min-w-0 flex-col gap-2">
            <h3 class="text-xs font-bold">بازیکن دوم</h3>
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
                <span class="size-2 shrink-0 rounded-full border" :style="{ backgroundColor: team.color ?? '#e67e22' }" />
                <span class="truncate">{{ team.name }}</span>
              </Button>
            </div>
          </section>
        </div>
        <DialogFooter class="gap-2 sm:justify-start">
          <Button
            :disabled="teams.length < 2 || !firstTeamCode || !secondTeamCode || firstTeamCode === secondTeamCode || createMutation.isPending.value"
            @click="createGame"
          >
            <ArrowLeftIcon class="size-4" /> {{ createMutation.isPending.value ? 'در حال ساخت…' : 'شروع بازی' }}
          </Button>
          <Button variant="outline" @click="createOpen = false">انصراف</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped>
.centipede-page {
  background:
    radial-gradient(circle at 12% 10%, rgb(43 108 168 / 10%), transparent 24rem),
    radial-gradient(circle at 88% 88%, rgb(230 126 34 / 9%), transparent 25rem),
    radial-gradient(circle, rgb(43 108 168 / 6%) 1px, transparent 1px),
    var(--background);
  background-size: auto, auto, 24px 24px, auto;
}
.event-emblem, .empty-icon { display:grid; flex:none; place-items:center; border-radius:1rem; }
.event-emblem { width:3rem; height:3rem; background:linear-gradient(145deg,#2b6ca8,#174c78); color:white; box-shadow:0 14px 28px -16px rgb(43 108 168 / 85%); }
.empty-icon { width:4rem; height:4rem; background:rgb(43 108 168 / 10%); color:#2b6ca8; }
.reward-board { display:grid; grid-template-columns:minmax(0,1fr) clamp(4rem,9vw,6rem) minmax(0,1fr); gap:.65rem; align-items:stretch; padding:.75rem; border:1px solid var(--border); border-radius:calc(var(--radius)*1.8); background:color-mix(in oklab,var(--card) 94%,transparent); box-shadow:0 18px 50px -38px rgb(15 23 42 / 55%); }
.player-reward { position:relative; display:flex; min-width:0; align-items:center; justify-content:space-between; gap:.75rem; overflow:hidden; padding:.85rem 1rem; border:1px solid color-mix(in oklab,var(--player-color) 24%,var(--border)); border-radius:calc(var(--radius)*1.35); background:linear-gradient(110deg,color-mix(in oklab,var(--player-color) 9%,var(--card)),var(--card) 70%); transition:opacity .2s ease,border-color .2s ease,box-shadow .2s ease; }
.player-reward:nth-of-type(1){grid-column:1}.player-reward:nth-of-type(2){grid-column:3}.player-reward.is-active{border-color:color-mix(in oklab,var(--player-color) 75%,#111);box-shadow:0 0 0 2px color-mix(in oklab,var(--player-color) 16%,transparent)}.player-reward.is-winner{border-color:#d5a621;box-shadow:0 0 0 2px rgb(213 166 33 / 13%)}.player-reward.is-lost{opacity:.52}
.player-swatch{width:.75rem;height:.75rem;flex:none;border:2px solid white;border-radius:999px;background:var(--player-color);box-shadow:0 0 0 1px color-mix(in oklab,var(--player-color) 70%,#111)}
.reward-number{font-family:var(--font-secondary);font-size:clamp(1.2rem,3vw,1.85rem);font-weight:900;line-height:1}.active-ribbon,.winner-ribbon{position:absolute;inset-inline-start:0;inset-block-end:0;display:flex;align-items:center;gap:.2rem;padding:.15rem .55rem;border-start-end-radius:.5rem;color:white;font-size:.6rem;font-weight:700}.active-ribbon{background:var(--player-color)}.winner-ribbon{background:#b58408}
.round-center{grid-column:2;grid-row:1;display:flex;flex-direction:column;align-items:center;justify-content:center}.round-center strong{font-family:var(--font-secondary);font-size:1.8rem;line-height:1}
.centipede-track{grid-column:1/-1;display:flex;align-items:center;justify-content:center;gap:.45rem;padding:.35rem}.track-node{position:relative;width:clamp(.65rem,1.5vw,.9rem);height:clamp(.65rem,1.5vw,.9rem);border:2px solid var(--border);border-radius:999px;background:var(--muted)}.track-node:not(:last-child)::after{content:'';position:absolute;top:50%;right:100%;width:.48rem;height:2px;background:var(--border);transform:translateY(-50%)}.track-node.is-reached{border-color:#2b6ca8;background:#2b6ca8;box-shadow:0 0 0 3px rgb(43 108 168 / 9%)}.track-head{position:absolute;inset:50% auto auto 50%;display:grid;width:1.75rem;height:1.75rem;place-items:center;border-radius:999px;background:#174c78;color:white;transform:translate(-50%,-50%);animation:head-float 2s ease-in-out infinite}
.decision-stage{background:linear-gradient(150deg,color-mix(in oklab,#2b6ca8 6%,var(--card)),var(--card) 55%,color-mix(in oklab,#e67e22 4%,var(--card)))}
.decision-orb,.waiting-orb,.result-crown{display:grid;width:4rem;height:4rem;place-items:center;border-radius:1.25rem}.decision-orb{background:rgb(43 108 168 / 11%);color:#2b6ca8;animation:decision-pulse 2s ease-in-out infinite}.waiting-orb{background:var(--muted);color:var(--muted-foreground)}.result-crown{background:rgb(251 191 36 / 16%);color:#9a6700;transform:rotate(-4deg)}
.take-button{background:linear-gradient(135deg,#2b6ca8,#174c78)}.continue-button{border-color:rgb(230 126 34 / 35%);background:rgb(230 126 34 / 5%)}.is-pulsing{animation:action-pop .4s ease}
.history-card{display:flex;flex-direction:column}.history-content{flex:1}.decision-list{display:flex;flex-direction:column}.decision-item{position:relative;display:flex;gap:.8rem;padding:.25rem 0 1rem}.decision-item:not(:last-child)::after{content:'';position:absolute;top:1rem;right:.34rem;bottom:-.05rem;width:1px;background:var(--border)}.decision-dot{z-index:1;width:.75rem;height:.75rem;flex:none;margin-top:.15rem;border:2px solid white;border-radius:999px;background:#2b6ca8;box-shadow:0 0 0 1px #2b6ca8}.decision-dot.is-take{background:#d59b16;box-shadow:0 0 0 1px #b58408}
@keyframes head-float{0%,100%{translate:0 0}50%{translate:0 -.2rem}}@keyframes decision-pulse{0%,100%{box-shadow:0 0 0 0 rgb(43 108 168 / 0%)}50%{box-shadow:0 0 0 9px rgb(43 108 168 / 8%)}}@keyframes action-pop{50%{transform:scale(.97)}}
@media(min-width:1024px){.game-layout{overflow:hidden}.history-card{height:100%;max-height:100%}}
@media(max-width:640px){.event-header p{display:none}.event-emblem{width:2.5rem;height:2.5rem;border-radius:.8rem}.reward-board{grid-template-columns:minmax(0,1fr) 3.5rem minmax(0,1fr);gap:.35rem;padding:.45rem}.player-reward{flex-direction:column;align-items:stretch;padding:.65rem}.player-reward>div:last-of-type{text-align:start}.player-reward>div:last-of-type p{justify-content:flex-start}.round-center strong{font-size:1.4rem}.centipede-track{gap:.35rem}}
@media(min-width:1024px) and (max-height:820px){.event-frame{gap:.65rem;padding-block:.65rem}.event-header p{display:none}.event-emblem{width:2.5rem;height:2.5rem}.reward-board{padding:.5rem}.player-reward{padding:.55rem .75rem}}
@media(prefers-reduced-motion:reduce){.track-head,.decision-orb,.is-pulsing{animation:none}}
</style>
