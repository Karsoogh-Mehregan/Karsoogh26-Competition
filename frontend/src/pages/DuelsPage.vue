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
  Loader2Icon,
  RefreshCwIcon,
  SwordsIcon,
} from '@lucide/vue'
import { computed, ref } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
import { useMapDesign } from '@/composables/useMapDesign'
import { formatBalance, formatRelativeTime } from '@/lib/format'
// The shared table, not a local copy: it gained `center` when the centre-city
// tier landed, and a duel page with its own map would have shown the raw key.
import { LEVEL_LABEL } from '@/lib/mapLevels'
import type { Duel, DuelTarget, DuelTeam } from '@/types/api'

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

const { metaByCode } = useMapDesign()

/**
 * Where a building sits, not just what it is called.
 *
 * A bare «برج شمالی» tells a player nothing about which of eight neighbourhoods
 * they are being asked to walk into, and node names repeat across the map. The
 * tier and the neighbourhood come from the same design layer the map paints
 * from, so this reads exactly as the board does.
 */
function categoryOf(nodeCode: string, name?: string): string {
  const meta = metaByCode(nodeCode)
  const parts = [meta ? LEVEL_LABEL[meta.level] : null, meta?.neighborhoodName]
  // Unnamed nodes already show their code as the title; repeating it reads as a
  // stutter — «L2_16 · آسان · محلهٔ آبی · L2_16».
  if (name && name !== nodeCode) parts.push(nodeCode)
  return parts.filter(Boolean).join(' · ')
}

/** Targets grouped by the building they belong to, best floor first. */
const targetGroups = computed(() => {
  const groups = new Map<string, { code: string; name: string; rows: DuelTarget[] }>()
  for (const row of targets.value) {
    const group = groups.get(row.node_code) ?? {
      code: row.node_code,
      name: row.node_name || row.node_code,
      rows: [],
    }
    group.rows.push(row)
    groups.set(row.node_code, group)
  }
  for (const group of groups.values()) {
    group.rows.sort((a, b) => b.floor - a.floor)
  }
  return [...groups.values()].sort((a, b) => a.name.localeCompare(b.name, 'fa'))
})

// Which row's button is spinning. Without it every button in the table would
// look busy while one of them is submitting.
const pendingTarget = ref<number | null>(null)

const pastDuels = computed<Duel[]>(() => (isDuelMentor.value ? judged.value : history.value))

function houseLabel(duel: Duel | DuelTarget): string {
  const name = 'node_name' in duel ? duel.node_name : ''
  return name || ('node_code' in duel ? duel.node_code : '')
}

/**
 * The duel's id, as something a player can quote.
 *
 * Two duels between the same pair over the same floor differ only by their
 * outcome and how long ago they were, which is not enough to point at one in a
 * message to an organiser. Left in Latin digits on purpose — like the node
 * codes, this is a key to look up, not a number to read.
 */
function duelRef(duel: Duel): string {
  return `#${duel.id}`
}

/** Bolds the viewer's own team, so a column of names is scannable at a glance. */
function isOwnSide(team: DuelTeam): boolean {
  return !!actingTeam.value && actingTeam.value.code === team.code
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

/**
 * Naming a winner is irreversible, so it takes two deliberate acts.
 *
 * Closing a duel moves a floor and settles the stake in one transaction, and
 * `DuelAdmin` freezes the row afterwards — there is no undo, only an organiser
 * editing the database. A single click on one of two adjacent buttons is far
 * too little for that, so the click only *proposes* a winner and a modal asks
 * again. The modal is deliberately not an inline swap: a confirm button that
 * appears where the trigger just was is reachable by the second half of an
 * accidental double-click, which is the exact misclick being guarded against.
 */
const proposedWinner = ref<DuelTeam | null>(null)

const confirmOpen = computed({
  get: () => proposedWinner.value !== null,
  set: (value: boolean) => {
    if (!value) proposedWinner.value = null
  },
})

/** What confirming actually does, in the judge's own terms. */
const confirmConsequence = computed(() => {
  const duel = judging.value
  const winner = proposedWinner.value
  if (!duel || !winner) return ''
  const where = `طبقهٔ ${duel.floor} ساختمان «${houseLabel(duel)}»`
  return winner.code === duel.attacker.code
    ? `${where} به تیم «${duel.attacker.name}» می‌رسد و ورودی دوئل به آن بازگردانده می‌شود.`
    : `${where} برای تیم «${duel.attacked.name}» باقی می‌ماند و ورودی دوئل ` +
        `(${formatBalance(duel.stake)}) به آن پرداخت می‌شود.`
})

function askWinner(team: DuelTeam) {
  proposedWinner.value = team
}

async function confirmWinner() {
  const duel = judging.value
  const winner = proposedWinner.value
  if (!duel || !winner || submitting.value) return
  // Only close on success: a refusal leaves the dialog up with the error toast,
  // rather than dropping the judge back to a card that looks unchanged.
  if (await callWinner(duel, winner.code)) proposedWinner.value = null
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
            <Badge variant="outline" class="font-normal">{{ duelRef(active) }}</Badge>
            <span class="font-bold">{{ active.attacker.name }}</span>
            <span class="text-muted-foreground">در برابر</span>
            <span class="font-bold">{{ active.attacked.name }}</span>
          </div>
          <p class="text-muted-foreground text-sm">
            بر سر طبقهٔ {{ active.floor }} ساختمان «{{ houseLabel(active) }}»
            ({{ categoryOf(active.node_code, houseLabel(active)) }}) —
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
              <span class="text-muted-foreground me-1 text-xs">{{ duelRef(judging) }}</span>
              <span class="font-bold">{{ judging.attacker.name }}</span>
              <span class="text-muted-foreground"> در برابر </span>
              <span class="font-bold">{{ judging.attacked.name }}</span>
              <span class="text-muted-foreground">
                — طبقهٔ {{ judging.floor }} ساختمان «{{ houseLabel(judging) }}»
                ({{ categoryOf(judging.node_code, houseLabel(judging)) }})
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
                <Button :disabled="submitting" @click="askWinner(judging.attacker)">
                  {{ judging.attacker.name }}
                </Button>
                <Button :disabled="submitting" @click="askWinner(judging.attacked)">
                  {{ judging.attacked.name }}
                </Button>
              </div>
              <p class="text-muted-foreground text-xs">
                پس از ثبت، نتیجه قابل تغییر نیست.
              </p>
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
                  <TableHead class="border-e text-center">طبقه</TableHead>
                  <TableHead class="border-e">صاحب</TableHead>
                  <TableHead class="border-e text-end">ورودی</TableHead>
                  <TableHead class="w-24 text-center">دوئل</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableEmpty v-if="targetGroups.length === 0" :colspan="4">
                  <span class="text-muted-foreground text-sm">
                    ساختمان پُری در همسایگی شما نیست.
                  </span>
                </TableEmpty>
                <!-- Grouped by building: one header naming the house and where
                     it sits, then its floors underneath. -->
                <template v-for="group in targetGroups" :key="group.code">
                  <TableRow class="bg-muted/50 hover:bg-muted/50">
                    <TableCell colspan="4" class="py-2">
                      <span class="font-bold">{{ group.name }}</span>
                      <span class="text-muted-foreground text-xs">
                        · {{ categoryOf(group.code, group.name) }}
                      </span>
                    </TableCell>
                  </TableRow>
                  <TableRow v-for="target in group.rows" :key="target.occupancy_id">
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
                </template>
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
                  <TableHead class="w-14 border-e text-center">شناسه</TableHead>
                  <TableHead class="border-e">مهاجم</TableHead>
                  <TableHead class="border-e">مدافع</TableHead>
                  <TableHead class="border-e">ساختمان</TableHead>
                  <TableHead class="border-e text-end">ورودی</TableHead>
                  <TableHead class="border-e">نتیجه</TableHead>
                  <TableHead>زمان</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableEmpty v-if="pastDuels.length === 0" :colspan="7">
                  <span class="text-muted-foreground text-sm">هنوز دوئلی انجام نشده است.</span>
                </TableEmpty>
                <TableRow v-for="duel in pastDuels" :key="duel.id">
                  <!-- Latin digits, like the node codes: this is a lookup key an
                       organiser reads back in admin, not a quantity. -->
                  <TableCell class="text-muted-foreground border-e text-center text-xs">
                    {{ duelRef(duel) }}
                  </TableCell>
                  <!-- Attacker and defender in their own columns: which side a
                       team was on decides what the stake did, so the two must be
                       readable down the column rather than parsed out of one cell. -->
                  <TableCell class="border-e" :class="isOwnSide(duel.attacker) && 'font-bold'">
                    {{ duel.attacker.name }}
                  </TableCell>
                  <TableCell class="border-e" :class="isOwnSide(duel.attacked) && 'font-bold'">
                    {{ duel.attacked.name }}
                  </TableCell>
                  <TableCell class="border-e">
                    <span>{{ houseLabel(duel) }} · طبقهٔ {{ duel.floor }}</span>
                    <span class="text-muted-foreground block text-xs">
                      {{ categoryOf(duel.node_code, houseLabel(duel)) }}
                    </span>
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

    <!-- Second act: restates who won, what it does, and that it is final. -->
    <Dialog v-model:open="confirmOpen">
      <DialogContent dir="rtl" class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>تأیید برندهٔ دوئل</DialogTitle>
          <DialogDescription v-if="judging">
            دوئل {{ duelRef(judging) }} — «{{ judging.attacker.name }}» در برابر
            «{{ judging.attacked.name }}»
          </DialogDescription>
        </DialogHeader>

        <div v-if="proposedWinner" class="flex flex-col gap-3">
          <div class="bg-muted flex flex-col gap-1 rounded-lg p-3">
            <span class="text-muted-foreground text-xs">برنده</span>
            <span class="text-base font-bold">{{ proposedWinner.name }}</span>
          </div>
          <p class="text-muted-foreground text-sm">{{ confirmConsequence }}</p>
          <p class="text-destructive flex items-start gap-2 text-xs">
            <CircleAlertIcon class="mt-0.5 size-3.5 shrink-0" />
            این نتیجه پس از ثبت قابل تغییر نیست.
          </p>
        </div>

        <DialogFooter class="flex-row gap-2 sm:justify-start">
          <Button variant="outline" class="flex-1" :disabled="submitting" @click="confirmOpen = false">
            انصراف
          </Button>
          <Button class="flex-1" :disabled="submitting" :aria-busy="submitting" @click="confirmWinner">
            <Loader2Icon v-if="submitting" class="size-4 animate-spin" />
            ثبت برنده
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
</template>
