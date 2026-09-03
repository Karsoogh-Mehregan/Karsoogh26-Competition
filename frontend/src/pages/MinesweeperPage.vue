<script setup lang="ts">
import {
  BombIcon,
  FlagIcon,
  MousePointerClickIcon,
  PartyPopperIcon,
} from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { toast } from 'vue-sonner'
import MinesweeperBoard from '@/components/minesweeper/MinesweeperBoard.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useMinesweeper } from '@/composables/useMinesweeper'
import { formatBalance } from '@/lib/format'
import type { MinesweeperDifficulty, MinesweeperGame } from '@/types/api'

const STATUS_LABEL: Record<MinesweeperGame['status'], string> = {
  in_progress: 'در حال بازی',
  won: 'برد',
  lost: 'باخت',
}

const DIFFICULTY_LABEL: Record<MinesweeperDifficulty, string> = {
  easy: 'آسان',
  medium: 'متوسط',
  hard: 'سخت',
}

const route = useRoute()
const gameId = computed(() => {
  const parsed = Number(route.params.id)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
})
const flagMode = ref(false)

const { game, loading, joining, revealing, flagging, error, join, reveal, toggleFlag } =
  useMinesweeper(gameId)

const busy = computed(() => revealing.value || flagging.value)
const inProgress = computed(() => game.value?.status === 'in_progress')

const remainingFlags = computed(() => {
  if (!game.value) return 0
  let flagged = 0
  for (const row of game.value.board.cells) {
    for (const cell of row) {
      if (cell.flagged) flagged += 1
    }
  }
  return game.value.mine_count - flagged
})

watch(
  gameId,
  async () => {
    flagMode.value = false
    if (gameId.value == null) return
    const joined = await join()
    if (!joined && error.value) {
      toast.error(error.value)
    }
  },
  { immediate: true },
)

async function onReveal(row: number, col: number): Promise<void> {
  if (busy.value || !inProgress.value) return
  const result = await reveal(row, col)
  if (!result && error.value) {
    toast.error(error.value)
  }
}

async function onFlag(row: number, col: number): Promise<void> {
  if (busy.value || !inProgress.value) return
  const result = await toggleFlag(row, col)
  if (!result && error.value) {
    toast.error(error.value)
  }
}
</script>

<template>
  <div class="h-full overflow-y-auto p-6">
    <div class="mx-auto flex w-full min-w-0 max-w-5xl flex-col gap-4">
      <header>
        <h1 class="text-lg font-bold">مین‌روب</h1>
        <p class="text-muted-foreground mt-1 text-sm">
          خانه‌ها را باز کنید و مین‌ها را پرچم بزنید. نتیجه و امتیاز را سرور مشخص می‌کند.
        </p>
      </header>

      <div v-if="gameId == null" class="text-destructive text-sm">بازی پیدا نشد.</div>

      <div v-else-if="loading || joining" class="flex flex-col gap-3">
        <Skeleton class="h-16 w-full" />
        <Skeleton class="h-72 w-full" />
      </div>

      <p v-else-if="!game" class="text-destructive text-sm">
        {{ error || 'بازی پیدا نشد.' }}
      </p>

      <template v-else>
        <div
          v-if="game.status === 'won'"
          class="border-emerald-200 bg-emerald-50 text-emerald-950 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-50 flex flex-col gap-2 rounded-xl border p-4"
          role="status"
        >
          <p class="flex items-center gap-2 font-semibold">
            <PartyPopperIcon class="size-4 shrink-0" />
            بازی را بردید
          </p>
          <p class="text-sm">
            امتیاز نهایی:
            <span class="font-bold tabular-nums">{{ formatBalance(game.score) }}</span>
          </p>
        </div>

        <div
          v-else-if="game.status === 'lost'"
          class="border-destructive/30 bg-destructive/5 text-destructive flex flex-col gap-2 rounded-xl border p-4"
          role="status"
        >
          <p class="flex items-center gap-2 font-semibold">
            <BombIcon class="size-4 shrink-0" />
            روی مین رفتید؛ بازی تمام شد
          </p>
          <p class="text-sm">
            امتیاز:
            <span class="font-bold tabular-nums">{{ formatBalance(game.score) }}</span>
          </p>
        </div>

        <Card class="min-w-0 gap-4 py-4">
          <CardHeader class="px-4">
            <CardTitle class="text-base">وضعیت بازی</CardTitle>
            <CardDescription class="sr-only">اطلاعات سطح، مین، امتیاز و وضعیت</CardDescription>
            <dl class="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div class="flex flex-col gap-0.5">
                <dt class="text-muted-foreground">سطح</dt>
                <dd class="font-semibold">{{ DIFFICULTY_LABEL[game.difficulty] }}</dd>
              </div>
              <div class="flex flex-col gap-0.5">
                <dt class="text-muted-foreground">مین‌ها</dt>
                <dd class="font-semibold tabular-nums">{{ formatBalance(game.mine_count) }}</dd>
              </div>
              <div class="flex flex-col gap-0.5">
                <dt class="text-muted-foreground">امتیاز</dt>
                <dd class="font-semibold tabular-nums">{{ formatBalance(game.score) }}</dd>
              </div>
              <div class="flex flex-col gap-0.5">
                <dt class="text-muted-foreground">وضعیت</dt>
                <dd class="font-semibold">{{ STATUS_LABEL[game.status] }}</dd>
              </div>
            </dl>
            <p v-if="inProgress" class="text-muted-foreground mt-3 text-xs">
              پرچم باقی‌مانده (تخمینی):
              <span class="text-foreground font-medium tabular-nums">
                {{ formatBalance(remainingFlags) }}
              </span>
              — شمارش پرچم‌های شماست، نه نقشهٔ واقعی مین‌ها.
            </p>
          </CardHeader>
          <CardContent class="min-w-0 px-4">
            <div v-if="inProgress" class="mb-3 flex flex-wrap gap-2">
              <Button
                size="sm"
                :variant="flagMode ? 'outline' : 'default'"
                :aria-pressed="!flagMode"
                @click="flagMode = false"
              >
                <MousePointerClickIcon class="size-4" />
                باز کردن
              </Button>
              <Button
                size="sm"
                :variant="flagMode ? 'default' : 'outline'"
                :aria-pressed="flagMode"
                @click="flagMode = true"
              >
                <FlagIcon class="size-4" />
                پرچم
              </Button>
              <p class="text-muted-foreground w-full text-xs sm:w-auto sm:self-center">
                {{
                  flagMode
                    ? 'لمس هر خانه پرچم را عوض می‌کند. روی رایانه راست‌کلیک هم پرچم می‌زند.'
                    : 'لمس یا کلیک چپ خانه را باز می‌کند. راست‌کلیک پرچم می‌زند.'
                }}
              </p>
            </div>

            <MinesweeperBoard
              :game="game"
              :interactive="inProgress"
              :flag-mode="flagMode"
              :busy="busy"
              @reveal="onReveal"
              @flag="onFlag"
            />
          </CardContent>
        </Card>
      </template>
    </div>
  </div>
</template>
