<script setup lang="ts">
/**
 * The detail column beside the map.
 *
 * This is where all the drawing effort went, and the reason the map itself can
 * stay cheap: 473 nodes stay primitives, and the one node the player is
 * actually looking at gets a building.
 *
 * three.js arrives only with `HouseCanvas`, and only once a house is opened.
 *
 * A Designer sees one extra block under the floor list: the building type and
 * tier for this node, editable in place with the model as live preview.
 */
import {
  ChevronRightIcon,
  HandCoinsIcon,
  HouseIcon,
  Loader2Icon,
  Maximize2Icon,
  Minimize2Icon,
  PaintbrushIcon,
  SwordsIcon,
  XIcon,
} from '@lucide/vue'
import { useLocalStorage } from '@vueuse/core'
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { useBuyouts } from '@/composables/useBuyouts'
import { useDuels } from '@/composables/useDuels'
import { useEntry } from '@/composables/useEntry'
import { useHouseSpec } from '@/composables/useHouseSpec'
import { useMapDesign } from '@/composables/useMapDesign'
import { formatBalance } from '@/lib/format'
import { entryCostForLevel } from '@/lib/nodeLevels'
import { ARCHETYPES } from '@/lib/house/archetypes'
import type { FloorState } from '@/lib/house/spec'
import { ApiError } from '@/lib/http'
import { LEVEL_LABEL } from '@/lib/mapLevels'
import { useUpdateNodeDesignMutation } from '@/queries/design'
import { useLevelsQuery } from '@/queries/game'
import { useEnterMinesweeperMutation } from '@/queries/minesweeper'
import { useAttemptStore } from '@/stores/attempt'
import { useInspectorStore } from '@/stores/inspector'
import type { NodeLevel } from '@/types/api'

const HouseCanvas = defineAsyncComponent({
  loader: () => import('./HouseCanvas.vue'),
  loadingComponent: Skeleton,
  delay: 120,
})

const inspector = useInspectorStore()
const { spec, inspection, holdings } = useHouseSpec()
const { me, actingTeam, isPlayer, claimStart, assignQuestion } = useActing()
const { open: openEntrySheet } = useEntry()
const { pinOf, canDesign } = useMapDesign()
const { data: levelConfigs } = useLevelsQuery(() => !!me.value)
const attemptStore = useAttemptStore()
const enterMinesweeper = useEnterMinesweeperMutation()
const router = useRouter()

const collapsed = useLocalStorage('karsoogh.house-panel-collapsed', false)
// A bigger stage for actually looking at the building; the map gives up width for it.
const expanded = useLocalStorage('karsoogh.house-panel-expanded', false)
const busy = ref(false)


/** Penthouse first: floor N is the best unit, so it reads top-down. */
const floorsTopFirst = computed<FloorState[]>(() => [...(spec.value?.floors ?? [])].reverse())

const STATUS_LABEL: Record<FloorState['status'], string> = {
  empty: 'خالی',
  reserved: 'در حال حل',
  owned: 'در تصرف',
}

// ---- duels -------------------------------------------------------------------
//
// A duel is aimed at a *building*, and only at one whose every floor is already
// taken — «اگر یکی از ساختمان‌های اطرافتان پر باشد». Which floor you take it
// from is then your choice, so the picker lives here on the house rather than
// as a row in a table somewhere else.
//
// Eligibility is not re-derived on the client. `GET /api/duels/targets/` has
// already applied every rule the server would enforce on the challenge —
// fullness, adjacency, opponents who are mid-duel or resting, the price of each
// floor — so filtering that list to this node is both the question and the
// answer, and the panel can never offer a duel the API would refuse.

const {
  targets: duelTargets,
  canRequest: canDuel,
  blockedReason: duelBlockedReason,
  submitting: duelSubmitting,
  challenge,
} = useDuels()

const duelTargetsHere = computed(() =>
  duelTargets.value
    .filter((target) => target.node_code === spec.value?.nodeCode)
    .sort((a, b) => b.floor - a.floor),
)

const selectedDuelFloor = ref<number | null>(null)

// Reset the pick when the panel moves to another house, and default to the
// penthouse — the floor most worth taking.
watch(
  duelTargetsHere,
  (rows) => {
    if (!rows.some((row) => row.floor === selectedDuelFloor.value)) {
      selectedDuelFloor.value = rows[0]?.floor ?? null
    }
  },
  { immediate: true },
)

const selectedDuelTarget = computed(
  () => duelTargetsHere.value.find((row) => row.floor === selectedDuelFloor.value) ?? null,
)

/**
 * Show the section only where the server actually offers a duel on this node.
 *
 * Keying it off "is this house full" was wrong in three ways at once: it opened
 * on a house the team is *standing in* (you cannot duel your own building), on
 * one nowhere near the team (a duel is only ever against a neighbour), and on
 * one whose owners are all mid-duel or resting. `/api/duels/targets/` has
 * already applied every one of those rules, so a node with no rows is a node
 * with no duel — and the panel stops advertising one.
 */
const showDuelSection = computed(() => isPlayer.value && duelTargetsHere.value.length > 0)

async function requestDuel() {
  const target = selectedDuelTarget.value
  if (!target || duelSubmitting.value) return
  await challenge(target)
}

// ---- buyouts -----------------------------------------------------------------
//
// «مکانیک خرید»: a team that is stuck pays a lot and takes a unit outright; the
// holder is put out but keeps every rial it was paid, and the buyer is paid the
// floor's points. A duel without the meeting, so the section sits right under
// it and reads the same way: pick a floor, see the price, act.
//
// Eligibility is the server's, exactly as for duels — `GET /api/buyouts/targets/`
// has already applied adjacency, "not a house you sit in" and "not a seat under
// an open duel", so filtering it to this node is both the question and the
// answer. Unlike a duel the house need not be full, so on a shared node this
// section can show where the duel one does not.

const {
  targets: buyoutTargets,
  submitting: buyoutSubmitting,
  buy,
} = useBuyouts()

const buyoutTargetsHere = computed(() =>
  buyoutTargets.value
    .filter((target) => target.node_code === spec.value?.nodeCode)
    .sort((a, b) => b.floor - a.floor),
)

const selectedBuyoutFloor = ref<number | null>(null)

watch(
  buyoutTargetsHere,
  (rows) => {
    if (!rows.some((row) => row.floor === selectedBuyoutFloor.value)) {
      selectedBuyoutFloor.value = rows[0]?.floor ?? null
    }
  },
  { immediate: true },
)

const selectedBuyoutTarget = computed(
  () => buyoutTargetsHere.value.find((row) => row.floor === selectedBuyoutFloor.value) ?? null,
)

const showBuyoutSection = computed(() => isPlayer.value && buyoutTargetsHere.value.length > 0)

/** The price is large by design; a plain wallet check keeps the button honest. */
const canAffordBuyout = computed(() => {
  const target = selectedBuyoutTarget.value
  const balance = actingTeam.value?.balance
  if (!target || balance == null) return true
  return balance >= target.cost
})

// Confirm-once: this is the most expensive click on the board and it evicts
// another team, so the first press arms the button and the second one buys.
const buyoutArmed = ref(false)
watch([selectedBuyoutTarget, () => spec.value?.nodeCode], () => {
  buyoutArmed.value = false
})

async function requestBuyout() {
  const target = selectedBuyoutTarget.value
  if (!target || buyoutSubmitting.value) return
  if (!buyoutArmed.value) {
    buyoutArmed.value = true
    return
  }
  buyoutArmed.value = false
  await buy(target)
}

const ACTION_LABEL: Record<string, string> = {
  reserve: 'رزرو این خانه',
  claim_start: 'ورود به خانهٔ شروع',
  solve: 'رفتن به سؤال',
  entry_gate: 'پاسخ به سؤال‌های ورودی',
  minesweeper: 'ورود به مین‌روب',
  resume_minesweeper: 'ادامه بازی',
}

const reserveEntryCost = computed(() =>
  entryCostForLevel(spec.value?.level, levelConfigs.value),
)

// A toll node is a gate, not a building: it has no units to let, it charges to
// play, and a win is a crossing this team keeps.
const isGate = computed(() => spec.value?.level === 'toll')
const hasCrossed = computed(
  () => !!spec.value && (actingTeam.value?.cleared_tolls ?? []).includes(spec.value.nodeCode),
)
// A board left unfinished here. The toll is charged per board, so this one is
// already bought and the button resumes it instead of quoting the price again.
const hasOpenBoard = computed(
  () => !!spec.value && (actingTeam.value?.active_tolls ?? []).includes(spec.value.nodeCode),
)

function withCost(label: string): string {
  const cost = reserveEntryCost.value
  return cost == null ? label : `${label} (${formatBalance(cost)})`
}

const actionLabel = computed(() => {
  const intent = inspection.value?.intent
  if (!intent) return ''
  if (intent === 'minesweeper') {
    return hasOpenBoard.value
      ? ACTION_LABEL.resume_minesweeper
      : withCost(ACTION_LABEL.minesweeper)
  }
  if (intent === 'reserve') return withCost(ACTION_LABEL.reserve)
  return ACTION_LABEL[intent] ?? ''
})

async function runAction() {
  const current = inspection.value
  if (!current || busy.value) return

  if (current.intent === 'entry_gate') {
    openEntrySheet()
    return
  }

  if (current.intent === 'solve') {
    attemptStore.select(current.occupancyId)
    router.push({ name: 'solve' })
    return
  }

  busy.value = true
  try {
    if (current.intent === 'minesweeper') {
      const issued = await enterMinesweeper.mutateAsync(current.nodeCode)
      await router.push({
        name: 'minesweeper-node',
        params: { id: current.nodeCode },
        query: { entry: issued.entry },
      })
    } else if (current.intent === 'claim_start') {
      await claimStart(current.nodeCode)
      toast.success('خانهٔ شروع ثبت شد')
    } else if (current.intent === 'reserve') {
      const result = await assignQuestion(current.nodeCode)
      attemptStore.select(result.id)
      toast.success('این خانه رزرو شد')
      router.push({ name: 'solve' })
    }
  } catch (error) {
    toast.error(error instanceof Error ? error.message : 'عملیات ناموفق بود.')
  } finally {
    busy.value = false
  }
}

// ---- designer block ----------------------------------------------------------

const { mutateAsync: saveNode, isPending: savingNode } = useUpdateNodeDesignMutation()

const PLAYABLE_LEVELS: NodeLevel[] = ['easy', 'medium', 'hard']

const draftArchetype = ref('')
const draftLevel = ref<NodeLevel>('easy')

// Reset the drafts whenever the inspected node changes.
watch(
  () => spec.value?.nodeCode,
  (code) => {
    if (!code || !spec.value) return
    draftArchetype.value = pinOf(code)
    draftLevel.value = spec.value.level
  },
  { immediate: true },
)

const isSpecialPlot = computed(
  () => spec.value?.level === 'spawn' || spec.value?.level === 'toll' || spec.value?.level === 'center',
)
const nodeOccupied = computed(() => holdings.value.length > 0)
const designDirty = computed(
  () =>
    !!spec.value &&
    (draftArchetype.value !== pinOf(spec.value.nodeCode) || draftLevel.value !== spec.value.level),
)

async function saveDesign() {
  const current = spec.value
  if (!current || !designDirty.value) return
  try {
    await saveNode({
      nodeCode: current.nodeCode,
      changes: {
        archetype: draftArchetype.value,
        ...(draftLevel.value !== current.level ? { level: draftLevel.value } : {}),
      },
    })
    toast.success('طراحی این خانه ذخیره شد')
  } catch (error) {
    toast.error(error instanceof ApiError ? error.detail : 'ذخیرهٔ طراحی ناموفق بود.')
  }
}
</script>

<template>
  <aside v-if="collapsed" class="house-rail">
    <Button
      variant="ghost"
      size="icon"
      aria-label="باز کردن نمای خانه"
      title="نمای خانه"
      @click="collapsed = false"
    >
      <HouseIcon class="size-5" />
    </Button>
  </aside>

  <aside v-else class="house-panel" :class="{ 'is-expanded': expanded }" dir="rtl" aria-label="نمای خانه">
    <header class="house-panel-head">
      <div class="min-w-0">
        <h2 class="truncate text-base font-bold">
          {{ spec ? spec.archetype.label : 'نمای خانه' }}
        </h2>
        <p class="text-muted-foreground mt-0.5 truncate text-xs">
          <template v-if="spec">{{ spec.nodeName }} · {{ spec.neighborhoodName }}</template>
          <template v-else>یک خانه را روی نقشه انتخاب کنید</template>
        </p>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <Badge v-if="spec" variant="secondary">{{ spec.levelLabel }}</Badge>
        <Button
          variant="ghost"
          size="icon"
          :aria-label="expanded ? 'کوچک کردن نما' : 'بزرگ کردن نما'"
          :title="expanded ? 'کوچک کردن نما' : 'بزرگ کردن نما'"
          @click="expanded = !expanded"
        >
          <Minimize2Icon v-if="expanded" class="size-4" />
          <Maximize2Icon v-else class="size-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label="بستن نمای خانه"
          title="بستن"
          @click="collapsed = true"
        >
          <ChevronRightIcon class="size-4" />
        </Button>
      </div>
    </header>

    <div v-if="!spec" class="house-panel-empty">
      <HouseIcon class="text-muted-foreground/50 size-10" />
      <p class="text-muted-foreground text-sm">
        روی هر خانهٔ نقشه بزنید تا ساختمانش را ببینید.
      </p>
    </div>

    <template v-else>
      <div class="house-panel-stage">
        <HouseCanvas :spec="spec" />
      </div>

      <div class="house-panel-scroll">
        <ul class="house-panel-floors">
          <li v-for="slot in floorsTopFirst" :key="slot.floor" class="house-floor">
            <span class="house-floor-index tabular-nums">{{ formatBalance(slot.floor) }}</span>
            <span
              class="house-floor-swatch"
              :class="{ 'is-empty': slot.status === 'empty' }"
              :style="slot.color ? { backgroundColor: slot.color } : undefined"
              aria-hidden="true"
            />
            <span class="min-w-0 flex-1 truncate">
              {{ slot.teamName ?? '—' }}
              <Badge v-if="slot.isOwnTeam" variant="secondary" class="ms-1 font-normal">
                تیم شما
              </Badge>
            </span>
            <Badge
              variant="outline"
              class="shrink-0 font-normal"
              :class="slot.status === 'reserved' && 'text-amber-700 dark:text-amber-400'"
            >
              {{ STATUS_LABEL[slot.status] }}
            </Badge>
          </li>
        </ul>

        <!-- Only rendered where the server offers a duel: a full house next
             door that this team is not already sitting in. -->
        <section v-if="showDuelSection" class="house-duel" aria-label="دوئل برای این ساختمان">
          <h3 class="house-duel-title">
            <SwordsIcon class="size-3.5" />
            دوئل
          </h3>

          <div class="flex flex-col gap-1.5">
            <Label for="duel-floor">طبقه‌ای که می‌خواهید تصاحب کنید</Label>
            <select id="duel-floor" v-model="selectedDuelFloor" class="house-select">
              <option v-for="row in duelTargetsHere" :key="row.occupancy_id" :value="row.floor">
                طبقهٔ {{ row.floor }} — {{ row.team.name }} ({{ formatBalance(row.cost) }})
              </option>
            </select>
          </div>

          <p v-if="duelBlockedReason" class="text-muted-foreground text-xs">
            {{ duelBlockedReason }}
          </p>

          <Button
            class="w-full"
            :disabled="!selectedDuelTarget || !canDuel || duelSubmitting"
            :aria-busy="duelSubmitting"
            @click="requestDuel"
          >
            <Loader2Icon v-if="duelSubmitting" class="size-4 animate-spin" />
            <SwordsIcon v-else class="size-4" />
            درخواست دوئل
            <span v-if="selectedDuelTarget">({{ formatBalance(selectedDuelTarget.cost) }})</span>
          </Button>

          <p class="text-muted-foreground text-xs">
            ورودی دوئل هنگام درخواست کسر می‌شود؛ در صورت برد بازمی‌گردد و طبقه به شما می‌رسد.
          </p>
        </section>

        <!-- Only rendered where the server offers a purchase: an owned floor next
             door, in a house this team is not already sitting in. -->
        <section v-if="showBuyoutSection" class="house-buyout" aria-label="خرید واحد این ساختمان">
          <h3 class="house-buyout-title">
            <HandCoinsIcon class="size-3.5" />
            خرید واحد
          </h3>

          <div class="flex flex-col gap-1.5">
            <Label for="buyout-floor">واحدی که می‌خواهید بخرید</Label>
            <select id="buyout-floor" v-model="selectedBuyoutFloor" class="house-select">
              <option
                v-for="row in buyoutTargetsHere"
                :key="row.occupancy_id"
                :value="row.floor"
              >
                طبقهٔ {{ row.floor }} — {{ row.team.name }} ({{ formatBalance(row.cost) }})
              </option>
            </select>
          </div>

          <dl v-if="selectedBuyoutTarget" class="house-buyout-terms">
            <div>
              <dt>هزینهٔ خرید</dt>
              <dd>{{ formatBalance(selectedBuyoutTarget.cost) }}</dd>
            </div>
            <div>
              <dt>امتیاز طبقه</dt>
              <dd class="text-emerald-700 dark:text-emerald-400">
                +{{ formatBalance(selectedBuyoutTarget.points) }}
              </dd>
            </div>
          </dl>

          <p v-if="!canAffordBuyout" class="text-destructive text-xs">
            موجودی تیم برای این خرید کافی نیست.
          </p>

          <Button
            class="w-full"
            :variant="buyoutArmed ? 'destructive' : 'default'"
            :disabled="!selectedBuyoutTarget || !canAffordBuyout || buyoutSubmitting"
            :aria-busy="buyoutSubmitting"
            @click="requestBuyout"
          >
            <Loader2Icon v-if="buyoutSubmitting" class="size-4 animate-spin" />
            <HandCoinsIcon v-else class="size-4" />
            <template v-if="buyoutArmed">
              تأیید خرید — {{ selectedBuyoutTarget?.team.name }} بیرون می‌رود
            </template>
            <template v-else>
              خرید واحد
              <span v-if="selectedBuyoutTarget">({{ formatBalance(selectedBuyoutTarget.cost) }})</span>
            </template>
          </Button>

          <p class="text-muted-foreground text-xs">
            هزینه بلافاصله کسر می‌شود و طبقه بدون سؤال به شما می‌رسد؛ تیم فعلی بیرون می‌رود اما
            امتیازی از دست نمی‌دهد و امتیاز طبقه به شما پرداخت می‌شود.
          </p>
        </section>

        <section v-if="canDesign" class="house-design" aria-label="طراحی این خانه">
          <h3 class="house-design-title">
            <PaintbrushIcon class="size-3.5" />
            طراحی
          </h3>

          <div class="flex flex-col gap-1.5">
            <Label for="design-archetype">نوع ساختمان</Label>
            <select
              id="design-archetype"
              v-model="draftArchetype"
              class="house-select"
              :disabled="isSpecialPlot || savingNode"
            >
              <option value="">خودکار — {{ spec.archetype.label }}</option>
              <option v-for="item in ARCHETYPES" :key="item.key" :value="item.key">
                {{ item.label }}
              </option>
            </select>
            <p v-if="isSpecialPlot" class="text-muted-foreground text-xs">
              خانهٔ شروع و عوارضی شکل ثابت خودشان را دارند.
            </p>
          </div>

          <div class="flex flex-col gap-1.5">
            <Label for="design-level">سطح</Label>
            <select
              id="design-level"
              v-model="draftLevel"
              class="house-select"
              :disabled="isSpecialPlot || nodeOccupied || savingNode"
            >
              <option v-for="level in PLAYABLE_LEVELS" :key="level" :value="level">
                {{ LEVEL_LABEL[level] }}
              </option>
            </select>
            <p v-if="nodeOccupied && !isSpecialPlot" class="text-muted-foreground text-xs">
              تا وقتی تیمی روی این خانه است، سطح آن قفل است.
            </p>
          </div>

          <Button
            size="sm"
            class="w-full"
            :disabled="!designDirty || savingNode"
            :aria-busy="savingNode"
            @click="saveDesign"
          >
            <Loader2Icon v-if="savingNode" class="size-4 animate-spin" />
            ذخیرهٔ طراحی
          </Button>
        </section>
      </div>

      <footer class="house-panel-foot">
        <p class="text-muted-foreground text-xs">
          <template v-if="isGate && hasCrossed">از این عوارضی عبور کرده‌اید</template>
          <template v-else-if="isGate && hasOpenBoard">
            بازی این عوارضی در جریان است؛ هزینه‌اش پرداخت شده.
          </template>
          <template v-else-if="isGate">
            عوارضی؛ با بردن مین‌روب از آن عبور می‌کنید. ظرفیت ندارد.
          </template>
          <template v-else-if="spec.freeSlots > 0">
            {{ formatBalance(spec.freeSlots) }} واحد خالی از
            {{ formatBalance(spec.capacity) }}
          </template>
          <template v-else>ظرفیت این خانه پر است</template>
        </p>

        <Button
          v-if="actionLabel"
          class="w-full"
          :disabled="busy"
          :aria-busy="busy"
          @click="runAction"
        >
          <Loader2Icon v-if="busy" class="size-4 animate-spin" />
          {{ actionLabel }}
        </Button>

        <Button variant="ghost" size="sm" class="w-full" @click="inspector.clear()">
          <XIcon class="size-4" />
          بستن
        </Button>
      </footer>
    </template>
  </aside>
</template>

<style scoped>
.house-panel {
  display: flex;
  flex-direction: column;
  inline-size: 27rem;
  flex-shrink: 0;
  min-block-size: 0;
  border-inline-start: 1px solid var(--border);
  background: var(--card);
}

.house-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-block: 0.5rem;
  flex-shrink: 0;
  border-inline-start: 1px solid var(--border);
  background: var(--card);
}

.house-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.75rem 0.9rem;
  border-block-end: 1px solid var(--border);
}

.house-panel-empty {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 1.5rem;
  text-align: center;
}

/* The canvas gets the slack: the lists below are content-sized. */
.house-panel-stage {
  flex: 1 1 auto;
  min-block-size: 22rem;
  padding: 0.6rem;
}

/* Expanded: the building is the point; take a real share of the row. */
.house-panel.is-expanded {
  inline-size: min(46rem, 58vw);
}
.house-panel.is-expanded .house-panel-stage {
  min-block-size: 34rem;
}

.house-panel-scroll {
  flex: 0 1 auto;
  min-block-size: 0;
  overflow-y: auto;
}

.house-panel-floors {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding: 0 0.9rem;
  margin: 0;
  list-style: none;
}

.house-floor {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8rem;
  padding-block: 0.28rem;
}

.house-floor-index {
  inline-size: 1.35rem;
  text-align: center;
  font-weight: 700;
  color: var(--muted-foreground);
}

.house-floor-swatch {
  inline-size: 0.75rem;
  block-size: 0.75rem;
  flex-shrink: 0;
  border-radius: 0.25rem;
  border: 1px solid var(--border);
  background: #e2cfa6;
}
.house-floor-swatch.is-empty {
  background: repeating-linear-gradient(45deg, var(--muted) 0 3px, transparent 3px 6px);
}

.house-duel {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  margin: 0.7rem 0.9rem 0;
  padding: 0.75rem 0.8rem;
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  background: color-mix(in oklab, var(--muted) 35%, transparent);
}
.house-duel-title {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin: 0;
  font-size: 0.8125rem;
  font-weight: 700;
}

.house-buyout {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  margin: 0.6rem 0.9rem 0;
  padding: 0.75rem 0.8rem;
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  background: color-mix(in oklab, var(--muted) 35%, transparent);
}
.house-buyout-title {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin: 0;
  font-size: 0.8125rem;
  font-weight: 700;
}
.house-buyout-terms {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
  margin: 0;
}
.house-buyout-terms > div {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  padding: 0.45rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  background: var(--background);
}
.house-buyout-terms dt {
  font-size: 0.7rem;
  color: var(--muted-foreground);
}
.house-buyout-terms dd {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.house-design {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  margin: 0.6rem 0.9rem 0;
  padding: 0.7rem 0.8rem;
  border: 1px dashed var(--border);
  border-radius: 0.6rem;
  background: color-mix(in oklab, var(--muted) 45%, transparent);
}
.house-design-title {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin: 0;
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--muted-foreground);
}

.house-select {
  block-size: 2.25rem;
  inline-size: 100%;
  border: 1px solid var(--input);
  border-radius: 0.5rem;
  background: transparent;
  padding-inline: 0.6rem;
  font-size: 0.85rem;
  color: var(--foreground);
}
.house-select:disabled {
  opacity: 0.55;
}

.house-panel-foot {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem 0.9rem 0.9rem;
}

/* Under a laptop width the column becomes a bottom sheet: the map needs the
   horizontal room more than the house does. */
@media (max-width: 1023px) {
  .house-panel {
    position: fixed;
    inset-inline: 0;
    inset-block-end: 0;
    z-index: 30;
    inline-size: auto;
    max-block-size: 70svh;
    overflow-y: auto;
    border-inline-start: none;
    border-start-start-radius: 1rem;
    border-start-end-radius: 1rem;
    box-shadow: 0 -8px 30px rgb(0 0 0 / 0.14);
  }
  .house-panel-stage {
    min-block-size: 14rem;
  }
  .house-rail {
    position: fixed;
    inset-block-end: 0.75rem;
    inset-inline-start: 0.75rem;
    z-index: 30;
    border: 1px solid var(--border);
    border-radius: 999px;
    box-shadow: 0 4px 16px rgb(0 0 0 / 0.12);
  }
}
</style>
