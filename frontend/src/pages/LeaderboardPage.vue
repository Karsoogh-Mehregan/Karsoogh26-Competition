<script setup lang="ts">
import { CircleAlertIcon, RefreshCwIcon, TrophyIcon } from '@lucide/vue'
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useActing } from '@/composables/useActing'
import { formatBalance } from '@/lib/format'
import { ApiError } from '@/lib/http'
import { useGameStateQuery } from '@/queries/gameState'
import { useLeaderboardQuery } from '@/queries/teams'
import type { LeaderboardRow } from '@/types/api'

const { me, actingTeam, isPlayer } = useActing()
const isAuthenticated = () => me.value != null
const { data, isPending, error, refetch, isFetching } = useLeaderboardQuery(isAuthenticated)
const { data: gameState } = useGameStateQuery(isAuthenticated)

const rows = computed(() => data.value ?? [])
const leaderboardFrozen = computed(() => gameState.value?.leaderboard_frozen === true)
const frozenForPlayer = computed(() => leaderboardFrozen.value && isPlayer.value)
const errorMessage = computed(() => {
  if (!error.value) return ''
  return error.value instanceof ApiError ? error.value.detail : 'خطا در دریافت جدول امتیازات.'
})

const MEDAL_CLASS: Record<number, string> = {
  1: 'border-transparent bg-amber-400 text-amber-950',
  2: 'border-transparent bg-slate-300 text-slate-900',
  3: 'border-transparent bg-orange-400 text-orange-950',
}

function isOwnRow(row: LeaderboardRow): boolean {
  return !!actingTeam.value && actingTeam.value.code === row.code
}
</script>

<template>
  <div class="h-full overflow-y-auto p-6">
    <div class="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <header class="flex items-center justify-between gap-3">
        <div class="flex items-center gap-2">
          <TrophyIcon class="text-muted-foreground size-5 shrink-0" />
          <h1 class="text-lg font-bold">جدول امتیازات</h1>
          <Badge v-if="leaderboardFrozen" variant="secondary">فریز شده</Badge>
          <Badge v-if="rows.length" variant="secondary" class="tabular-nums">
            {{ formatBalance(rows.length) }} تیم
          </Badge>
        </div>
        <Button
          v-if="me && !frozenForPlayer"
          variant="ghost"
          size="sm"
          :disabled="isFetching"
          :aria-busy="isFetching"
          aria-label="بازخوانی جدول امتیازات"
          @click="refetch()"
        >
          <RefreshCwIcon class="size-4" :class="isFetching && 'animate-spin'" />
          بازخوانی
        </Button>
      </header>

      <p v-if="!me" class="text-muted-foreground text-sm">
        برای دیدن جدول امتیازات وارد شوید.
      </p>

      <template v-else>
        <p v-if="leaderboardFrozen" class="text-muted-foreground text-sm">
          {{
            frozenForPlayer
              ? 'رتبه‌ها در لحظهٔ فریز ثابت شده‌اند و دیگر به‌روز نمی‌شوند.'
              : 'تیم‌ها جدول ثابت می‌بینند؛ این صفحه زنده است.'
          }}
        </p>

        <div
          v-if="errorMessage"
          class="border-destructive/30 bg-destructive/5 flex flex-col items-start gap-3 rounded-lg border p-4"
          role="alert"
        >
          <p class="text-destructive flex items-start gap-2 text-sm">
            <CircleAlertIcon class="mt-0.5 size-4 shrink-0" />
            {{ errorMessage }}
          </p>
          <Button variant="outline" size="sm" :disabled="isFetching" @click="refetch()">
            <RefreshCwIcon class="size-4" :class="isFetching && 'animate-spin'" />
            تلاش دوباره
          </Button>
        </div>

        <Card v-else class="overflow-hidden p-0">
          <Table>
          <TableHeader>
            <TableRow class="hover:bg-transparent">
              <TableHead class="w-16 border-e text-center">رتبه</TableHead>
              <TableHead class="border-e">تیم</TableHead>
              <TableHead class="text-end">موجودی</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <template v-if="isPending">
              <TableRow v-for="i in 5" :key="`skeleton-${i}`" class="hover:bg-transparent">
                <TableCell class="border-e text-center">
                  <Skeleton class="mx-auto size-6 rounded-full" />
                </TableCell>
                <TableCell class="border-e">
                  <Skeleton class="h-4 w-32" />
                </TableCell>
                <TableCell class="text-end">
                  <Skeleton class="ms-auto h-4 w-14" />
                </TableCell>
              </TableRow>
            </template>

            <TableEmpty v-else-if="rows.length === 0" :colspan="3">
              <span class="text-muted-foreground text-sm">هنوز تیمی ثبت نشده است.</span>
            </TableEmpty>

            <template v-else>
              <TableRow
                v-for="row in rows"
                :key="row.code"
                :class="isOwnRow(row) ? 'bg-accent hover:bg-accent' : ''"
              >
                <TableCell
                  class="border-e border-s-2 text-center"
                  :class="isOwnRow(row) ? 'border-s-primary' : 'border-s-transparent'"
                >
                  <Badge
                    v-if="row.rank <= 3"
                    :class="MEDAL_CLASS[row.rank]"
                    class="mx-auto size-6 rounded-full p-0 tabular-nums"
                  >
                    {{ row.rank }}
                  </Badge>
                  <span
                    v-else
                    class="text-muted-foreground mx-auto flex size-6 items-center justify-center text-sm tabular-nums"
                  >
                    {{ row.rank }}
                  </span>
                </TableCell>
                <TableCell class="border-e font-medium">
                  {{ row.name }}
                  <Badge v-if="isOwnRow(row)" variant="secondary" class="ms-1.5 font-normal">
                    تیم شما
                  </Badge>
                </TableCell>
                <TableCell class="text-end font-semibold tabular-nums">
                  {{ formatBalance(row.balance) }}
                </TableCell>
              </TableRow>
            </template>
          </TableBody>
          </Table>
        </Card>
      </template>
    </div>
  </div>
</template>
