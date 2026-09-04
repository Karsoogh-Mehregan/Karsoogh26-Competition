<script setup lang="ts">
/**
 * One page, two audiences.
 *
 * A team sees its live duel (with the meeting link), the table of floors it may
 * challenge, and every duel it has already played. A judge sees the duel the
 * rotation handed them, the same link, and the two buttons that close it.
 *
 * Someone can be both — a judge who also plays — so the sections stack rather
 * than switching on a role.
 */
import {
  CircleAlertIcon,
  ExternalLinkIcon,
  GavelIcon,
  RefreshCwIcon,
  SwordsIcon,
} from '@lucide/vue'
import { computed, ref } from 'vue'
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
import { useDuels } from '@/composables/useDuels'
import { formatBalance, formatRelativeTime } from '@/lib/format'
import type { Duel, DuelTarget } from '@/types/api'

const { actingTeam } = useActing()
const {
  isDuelMentor,
  isPlayer,
  active,
  history,
  judging,
  judged,
  canRequest,
  blockedReason,
  targets,
  loading,
  submitting,
  error,
  refetch,
  challenge,
  callWinner,
} = useDuels()

const LEVEL_LABEL: Record<string, string> = {
  easy: 'آسان',
  medium: 'متوسط',
  hard: 'سخت',
}

// Which row's button is spinning. Without it every button in the table would
// look busy while one of them is submitting.
const pendingTarget = ref<number | null>(null)
const pendingWinner = ref<string | null>(null)

const pastDuels = computed<Duel[]>(() => (isDuelMentor.value ? judged.value : history.value))

function levelLabel(level: string): string {
  return LEVEL_LABEL[level] ?? level
}

function houseLabel(duel: Duel | DuelTarget): string {
  const name = 'node_name' in duel ? duel.node_name : ''
  return name || ('node_code' in duel ? duel.node_code : '')
}

function outcomeFor(duel: Duel): string {
  if (duel.status === 'open') return 'در جریان'
  const own = actingTeam.value?.code
  if (!own || !duel.winner) return `برندهٔ ${duel.winner?.name ?? '—'}`
  return duel.winner.code === own ? 'برد' : 'باخت'
}

async function onChallenge(target: DuelTarget) {
  pendingTarget.value = target.occupancy_id
  try {
    await challenge(target)
  } finally {
    pendingTarget.value = null
  }
}

async function onCallWinner(duel: Duel, winnerCode: string) {
  pendingWinner.value = winnerCode
  try {
    await callWinner(duel, winnerCode)
  } finally {
    pendingWinner.value = null
  }
}
</script>

<template>
  <div class="h-full overflow-y-auto p-6" dir="rtl">
    <div class="mx-auto flex w-full max-w-3xl flex-col gap-5">
      <header class="flex items-center justify-between gap-3">
        <div class="flex items-center gap-2">
          <SwordsIcon class="text-muted-foreground size-5 shrink-0" />
          <h1 class="text-lg font-bold">دوئل‌ها</h1>
        </div>
        <Button
          variant="ghost"
          size="sm"
          :disabled="submitting"
          aria-label="بازخوانی دوئل‌ها"
          @click="refetch()"
        >
          <RefreshCwIcon class="size-4" />
          بازخوانی
        </Button>
      </header>

      <p
        v-if="error"
        class="border-destructive/30 bg-destructive/5 text-destructive flex items-start gap-2 rounded-lg border p-3 text-sm"
        role="alert"
      >
        <CircleAlertIcon class="mt-0.5 size-4 shrink-0" />
        {{ error }}
      </p>

      <div v-if="loading" class="flex flex-col gap-3">
        <Skeleton class="h-28 w-full" />
        <Skeleton class="h-40 w-full" />
      </div>

      <template v-else>
        <!-- The team's live duel: who, which floor, and the way into the room. -->
        <Card v-if="active" class="flex flex-col gap-3 p-4">
          <div class="flex flex-wrap items-center gap-2">
            <Badge>دوئل فعال</Badge>
            <span class="font-bold">{{ active.attacker.name }}</span>
            <span class="text-muted-foreground">در برابر</span>
            <span class="font-bold">{{ active.attacked.name }}</span>
          </div>
          <p class="text-muted-foreground text-sm">
            بر سر طبقهٔ {{ active.floor }} ساختمان «{{ houseLabel(active) }}» —
            ورودی {{ formatBalance(active.stake) }}
          </p>
          <p class="text-muted-foreground text-sm">
            داور: {{ active.mentor }} · اتاق «{{ active.room_name }}»
          </p>
          <Button v-if="active.room_link" as-child class="w-fit">
            <a :href="active.room_link" target="_blank" rel="noopener noreferrer">
              <ExternalLinkIcon class="size-4" />
              ورود به میت
            </a>
          </Button>
          <p class="text-muted-foreground text-xs">
            هر چه زودتر در میت حاضر شوید؛ تیمی که حاضر نشود بازندهٔ دوئل است.
          </p>
        </Card>

        <!-- The judge's half: the same room, plus the only decision they make. -->
        <Card v-if="isDuelMentor" class="flex flex-col gap-3 p-4">
          <div class="flex items-center gap-2">
            <GavelIcon class="text-muted-foreground size-4 shrink-0" />
            <h2 class="font-bold">داوری</h2>
          </div>

          <template v-if="judging">
            <p class="text-sm">
              <span class="font-bold">{{ judging.attacker.name }}</span>
              <span class="text-muted-foreground"> در برابر </span>
              <span class="font-bold">{{ judging.attacked.name }}</span>
              <span class="text-muted-foreground">
                — طبقهٔ {{ judging.floor }} ساختمان «{{ houseLabel(judging) }}»
              </span>
            </p>
            <Button v-if="judging.room_link" as-child variant="outline" class="w-fit">
              <a :href="judging.room_link" target="_blank" rel="noopener noreferrer">
                <ExternalLinkIcon class="size-4" />
                {{ judging.room_name }}
              </a>
            </Button>
            <div class="flex flex-col gap-2">
              <span class="text-muted-foreground text-sm">برندهٔ دوئل کدام تیم بود؟</span>
              <div class="flex flex-wrap gap-2">
                <Button
                  :disabled="submitting"
                  :aria-busy="pendingWinner === judging.attacker.code"
                  @click="onCallWinner(judging, judging.attacker.code)"
                >
                  {{ judging.attacker.name }}
                </Button>
                <Button
                  :disabled="submitting"
                  :aria-busy="pendingWinner === judging.attacked.code"
                  @click="onCallWinner(judging, judging.attacked.code)"
                >
                  {{ judging.attacked.name }}
                </Button>
              </div>
            </div>
          </template>

          <p v-else class="text-muted-foreground text-sm">
            الان دوئلی به شما سپرده نشده است.
          </p>
        </Card>

        <!-- «تیم‌هایی که می‌توانید به آن‌ها دوئل بزنید» -->
        <section v-if="isPlayer && !active" class="flex flex-col gap-2">
          <h2 class="font-bold">تیم‌هایی که می‌توانید به آن‌ها دوئل بزنید</h2>
          <p v-if="blockedReason" class="text-muted-foreground text-sm">
            {{ blockedReason }}
          </p>
          <Card class="overflow-hidden p-0">
            <Table>
              <TableHeader>
                <TableRow class="hover:bg-transparent">
                  <TableHead class="border-e">ساختمان</TableHead>
                  <TableHead class="border-e text-center">طبقه</TableHead>
                  <TableHead class="border-e">صاحب</TableHead>
                  <TableHead class="border-e text-end">ورودی</TableHead>
                  <TableHead class="w-24 text-center">دوئل</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableEmpty v-if="targets.length === 0" :colspan="5">
                  <span class="text-muted-foreground text-sm">
                    ساختمان پُری در همسایگی شما نیست.
                  </span>
                </TableEmpty>
                <TableRow v-for="target in targets" :key="target.occupancy_id">
                  <TableCell class="border-e">
                    <span class="font-medium">{{ houseLabel(target) }}</span>
                    <span class="text-muted-foreground text-xs">
                      · {{ levelLabel(target.level) }}
                    </span>
                  </TableCell>
                  <TableCell class="border-e text-center tabular-nums">
                    {{ target.floor }}
                  </TableCell>
                  <TableCell class="border-e">{{ target.team.name }}</TableCell>
                  <TableCell class="border-e text-end tabular-nums">
                    {{ formatBalance(target.cost) }}
                  </TableCell>
                  <TableCell class="text-center">
                    <Button
                      size="sm"
                      :disabled="!canRequest || submitting"
                      :aria-busy="pendingTarget === target.occupancy_id"
                      @click="onChallenge(target)"
                    >
                      <SwordsIcon class="size-3.5" />
                      دوئل
                    </Button>
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </Card>
        </section>

        <!-- Everything already played, so a team can see what it did. -->
        <section class="flex flex-col gap-2">
          <h2 class="font-bold">دوئل‌های گذشته</h2>
          <Card class="overflow-hidden p-0">
            <Table>
              <TableHeader>
                <TableRow class="hover:bg-transparent">
                  <TableHead class="border-e">طرفین</TableHead>
                  <TableHead class="border-e">ساختمان</TableHead>
                  <TableHead class="border-e text-end">ورودی</TableHead>
                  <TableHead class="border-e">نتیجه</TableHead>
                  <TableHead>زمان</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableEmpty v-if="pastDuels.length === 0" :colspan="5">
                  <span class="text-muted-foreground text-sm">هنوز دوئلی انجام نشده است.</span>
                </TableEmpty>
                <TableRow v-for="duel in pastDuels" :key="duel.id">
                  <TableCell class="border-e">
                    {{ duel.attacker.name }} — {{ duel.attacked.name }}
                  </TableCell>
                  <TableCell class="border-e">
                    {{ houseLabel(duel) }} · طبقهٔ {{ duel.floor }}
                  </TableCell>
                  <TableCell class="border-e text-end tabular-nums">
                    {{ formatBalance(duel.stake) }}
                  </TableCell>
                  <TableCell class="border-e">
                    <Badge v-if="isDuelMentor" variant="secondary">
                      {{ duel.winner?.name ?? '—' }}
                    </Badge>
                    <Badge v-else :variant="outcomeFor(duel) === 'برد' ? 'default' : 'secondary'">
                      {{ outcomeFor(duel) }}
                    </Badge>
                  </TableCell>
                  <TableCell class="text-muted-foreground text-xs">
                    {{ formatRelativeTime(duel.resolved_at ?? duel.created_at) }}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </Card>
        </section>
      </template>
    </div>
  </div>
</template>
