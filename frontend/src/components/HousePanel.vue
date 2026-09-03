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
import { ChevronRightIcon, HouseIcon, Loader2Icon, PaintbrushIcon, XIcon } from '@lucide/vue'
import { useLocalStorage } from '@vueuse/core'
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { useEntry } from '@/composables/useEntry'
import { useHouseSpec } from '@/composables/useHouseSpec'
import { useMapDesign } from '@/composables/useMapDesign'
import { formatBalance } from '@/lib/format'
import { ARCHETYPES } from '@/lib/house/archetypes'
import type { FloorState } from '@/lib/house/spec'
import { ApiError } from '@/lib/http'
import { LEVEL_LABEL } from '@/lib/mapLevels'
import { useUpdateNodeDesignMutation } from '@/queries/design'
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
const { me, claimStart, assignQuestion } = useActing()
const { open: openEntrySheet } = useEntry()
const { pinOf } = useMapDesign()
const attemptStore = useAttemptStore()
const router = useRouter()

const collapsed = useLocalStorage('karsoogh.house-panel-collapsed', false)
const busy = ref(false)

const isDesigner = computed(() => me.value?.is_designer ?? false)

/** Penthouse first: floor N is the best unit, so it reads top-down. */
const floorsTopFirst = computed<FloorState[]>(() => [...(spec.value?.floors ?? [])].reverse())

const STATUS_LABEL: Record<FloorState['status'], string> = {
  empty: 'خالی',
  reserved: 'در حال حل',
  owned: 'در تصرف',
}

const ACTION_LABEL: Record<string, string> = {
  reserve: 'رزرو این خانه',
  claim_start: 'ورود به خانهٔ شروع',
  solve: 'رفتن به سؤال',
  entry_gate: 'پاسخ به سؤال‌های ورودی',
}

const actionLabel = computed(() => {
  const intent = inspection.value?.intent
  return intent ? (ACTION_LABEL[intent] ?? '') : ''
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
    if (current.intent === 'claim_start') {
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

const isSpecialPlot = computed(() => spec.value?.level === 'spawn' || spec.value?.level === 'toll')
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

  <aside v-else class="house-panel" dir="rtl" aria-label="نمای خانه">
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

        <section v-if="isDesigner" class="house-design" aria-label="طراحی این خانه">
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
          <template v-if="spec.freeSlots > 0">
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
  inline-size: 20rem;
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
  min-block-size: 12rem;
  padding: 0.6rem;
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
