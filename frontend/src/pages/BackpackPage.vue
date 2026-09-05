<script setup lang="ts">
import { Loader2Icon } from '@lucide/vue'
import { computed, ref } from 'vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogClose,
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
import { useGraph } from '@/composables/useGraph.js'
import { useItems } from '@/composables/useItems'
import { useMapDesign } from '@/composables/useMapDesign'
import { formatBalance } from '@/lib/format'
import type { TeamItem } from '@/types/api'

interface GraphNode {
  id: string
  type: string
}

interface FloorRow {
  floor: number
  teamName: string | null
  isOwnTeam: boolean
}

const { items, loading, using, error, needsNode, useItem } = useItems()
const { nodes } = useGraph() as { nodes: GraphNode[] }
const { levelOf, isGelled, hasMinesweeper, metaByCode } = useMapDesign()
const { teams, actingTeam } = useActing()

const hasItems = computed(() => items.value.length > 0)
const pickingGel = computed(() => pickerItem.value?.item_type === 'gel')
const pickingFakeDocument = computed(() => pickerItem.value?.item_type === 'fake_document')

const pickerOpen = ref(false)
const pickerItem = ref<TeamItem | null>(null)
const selectedCode = ref('')
const nodeQuery = ref('')
const floorsOpen = ref(false)
const selectedFloor = ref<number | null>(null)

// A gate is the only road onto the ring past it, so neither item ever offers
// one: the `toll` tier, the connector glyphs and a minesweeper board all name
// the same nodes, and the server refuses all three either way.
function isGate(node: GraphNode): boolean {
  return (
    levelOf(node.id, node.type) === 'toll' ||
    node.type === 'c34' ||
    node.type === 'c45' ||
    hasMinesweeper(node.id)
  )
}

// One list for both items: every house, by code alone. A spawn is left out of
// the fake-document list because it has no floors to forge a deed to.
const pickerNodes = computed(() => {
  const rows = nodes as GraphNode[]
  return rows.filter((node) => {
    const level = levelOf(node.id, node.type)
    if (node.id === 'CENTER' || level === 'center') return false
    if (isGate(node) || isGelled(node.id)) return false
    if (pickingFakeDocument.value && level === 'spawn') return false
    return true
  })
})

/**
 * The chosen house's storeys, and who owns each.
 *
 * Ownership is read strictly off `Holding.floor`, unlike the map's house panel:
 * a team that has only *reserved* a slot owns no floor yet and is not evicted
 * by a forged deed, so showing its name here would promise something the
 * server would not do.
 */
const floorRows = computed<FloorRow[]>(() => {
  const code = selectedCode.value
  const meta = code ? metaByCode(code) : null
  if (!code || !meta) return []

  const owners = new Map<number, { name: string; isOwnTeam: boolean }>()
  for (const team of teams.value) {
    for (const holding of team.holdings) {
      if (holding.node_code !== code || holding.floor == null) continue
      owners.set(holding.floor, {
        name: team.name,
        isOwnTeam: team.code === actingTeam.value?.code,
      })
    }
  }

  return Array.from({ length: meta.capacity }, (_, index) => {
    const floor = index + 1
    const owner = owners.get(floor)
    return { floor, teamName: owner?.name ?? null, isOwnTeam: owner?.isOwnTeam ?? false }
  })
})

function normalize(value: string): string {
  return value
    .trim()
    .toUpperCase()
    .replace(/[۰-۹]/g, (digit) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(digit)))
}

const visibleNodes = computed(() => {
  const needle = normalize(nodeQuery.value)
  const rows = pickerNodes.value
  if (!needle) return rows
  return rows.filter((node) => node.id.toUpperCase().includes(needle))
})

function closePicker() {
  pickerOpen.value = false
  floorsOpen.value = false
  pickerItem.value = null
  selectedCode.value = ''
  selectedFloor.value = null
  nodeQuery.value = ''
}

function onPickerOpen(open: boolean) {
  if (!open) closePicker()
}

/** Backing out of the floors returns to the house list rather than closing. */
function onFloorsOpen(open: boolean) {
  if (open) return
  floorsOpen.value = false
  selectedFloor.value = null
  pickerOpen.value = true
}

function pickNode(code: string) {
  selectedCode.value = code
  if (!pickingFakeDocument.value) return
  selectedFloor.value = null
  pickerOpen.value = false
  floorsOpen.value = true
}

async function onUse(item: TeamItem) {
  if (needsNode(item.item_type)) {
    pickerItem.value = item
    selectedCode.value = ''
    selectedFloor.value = null
    nodeQuery.value = ''
    floorsOpen.value = false
    pickerOpen.value = true
    return
  }
  await useItem(item.item_type)
}

async function confirmUse() {
  if (!pickerItem.value || !selectedCode.value) return
  const ok = await useItem(pickerItem.value.item_type, selectedCode.value)
  if (ok) closePicker()
}

async function confirmFloor() {
  if (!pickerItem.value || !selectedCode.value || selectedFloor.value == null) return
  const ok = await useItem(pickerItem.value.item_type, selectedCode.value, selectedFloor.value)
  if (ok) closePicker()
}
</script>

<template>
  <div class="h-full overflow-y-auto p-6">
    <div class="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <header>
        <h1 class="text-lg font-bold">کوله پشتی</h1>
        <p class="text-muted-foreground mt-1 text-sm">اقلام تیم شما.</p>
      </header>

      <p v-if="error && !pickerOpen" class="text-destructive text-sm">{{ error }}</p>

      <div v-if="loading" class="flex flex-col gap-3">
        <Skeleton class="h-24 w-full" />
        <Skeleton class="h-24 w-full" />
      </div>

      <p v-else-if="!hasItems" class="text-muted-foreground text-sm">کوله‌پشتی خالی است.</p>

      <div v-else class="flex flex-col gap-3">
        <Card v-for="item in items" :key="item.item_type" class="gap-3 py-4">
          <CardHeader>
            <CardTitle>{{ item.display_name }}</CardTitle>
          </CardHeader>
          <CardContent>
            <p class="text-muted-foreground text-sm">
              تعداد:
              <span class="text-foreground font-semibold tabular-nums">
                {{ formatBalance(item.quantity) }}
              </span>
            </p>
          </CardContent>
          <CardFooter>
            <Button :disabled="using" :aria-busy="using" @click="onUse(item)">
              <Loader2Icon v-if="using" class="size-4 animate-spin" />
              استفاده
            </Button>
          </CardFooter>
        </Card>
      </div>
    </div>

    <Dialog :open="pickerOpen" @update:open="onPickerOpen">
      <DialogContent class="flex max-h-[85dvh] flex-col gap-4 sm:max-w-md" dir="rtl">
        <DialogHeader class="text-start sm:text-start">
          <DialogTitle class="pe-6">انتخاب نود</DialogTitle>
          <DialogDescription>
            <template v-if="pickingGel">
              خانه‌ای را که می‌خواهید گِل بگیرید انتخاب کنید. مرکز شهر و عوارضی‌ها قابل انتخاب
              نیستند.
            </template>
            <template v-else-if="pickingFakeDocument">
              خانه را انتخاب کنید تا طبقه‌هایش را ببینید. مرکز شهر، خانه‌های شروع و عوارضی‌ها قابل
              انتخاب نیستند.
            </template>
            <template v-else>
              خانه‌ای را که می‌خواهید با
              {{ pickerItem?.display_name }}
              بگیرید انتخاب کنید.
            </template>
          </DialogDescription>
        </DialogHeader>

        <div class="flex min-h-0 flex-1 flex-col gap-3">
          <div class="flex flex-col gap-1.5">
            <Label for="item-node-search">جستجوی خانه</Label>
            <Input
              id="item-node-search"
              v-model="nodeQuery"
              type="search"
              autocomplete="off"
              placeholder="مثلاً L1_36"
            />
          </div>

          <p v-if="error" class="text-destructive text-sm" role="alert">{{ error }}</p>

          <ul
            class="max-h-64 min-h-0 flex-1 overflow-y-auto rounded-md border"
            role="listbox"
            aria-label="خانه‌های قابل انتخاب"
          >
            <li v-if="visibleNodes.length === 0" class="text-muted-foreground p-3 text-sm">
              خانه‌ای با این شناسه پیدا نشد.
            </li>
            <li v-for="node in visibleNodes" :key="node.id">
              <button
                type="button"
                role="option"
                class="hover:bg-accent flex w-full items-center justify-between gap-3 px-3 py-2 text-start text-sm"
                :class="selectedCode === node.id ? 'bg-accent' : ''"
                :aria-selected="selectedCode === node.id"
                @click="pickNode(node.id)"
              >
                <span class="font-semibold tabular-nums">{{ node.id }}</span>
              </button>
            </li>
          </ul>
        </div>

        <DialogFooter v-if="!pickingFakeDocument" class="flex-row gap-2 sm:justify-start">
          <Button :disabled="using || !selectedCode" :aria-busy="using" @click="confirmUse">
            <Loader2Icon v-if="using" class="size-4 animate-spin" />
            تأیید
          </Button>
          <DialogClose as-child>
            <Button variant="outline" :disabled="using">انصراف</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog :open="floorsOpen" @update:open="onFloorsOpen">
      <DialogContent class="flex max-h-[85dvh] flex-col gap-4 sm:max-w-md" dir="rtl">
        <DialogHeader class="text-start sm:text-start">
          <DialogTitle class="pe-6">طبقه‌های خانهٔ {{ selectedCode }}</DialogTitle>
          <DialogDescription>
            طبقه‌ای را که می‌خواهید با سند جعلی بگیرید انتخاب کنید. اگر تیمی در آن طبقه باشد، از
            آن بیرون می‌رود.
          </DialogDescription>
        </DialogHeader>

        <div class="flex min-h-0 flex-1 flex-col gap-3">
          <p v-if="error" class="text-destructive text-sm" role="alert">{{ error }}</p>

          <ul
            class="max-h-64 min-h-0 flex-1 overflow-y-auto rounded-md border"
            role="listbox"
            aria-label="طبقه‌های این خانه"
          >
            <li v-if="floorRows.length === 0" class="text-muted-foreground p-3 text-sm">
              این خانه طبقه‌ای برای گرفتن ندارد.
            </li>
            <li v-for="row in floorRows" :key="row.floor">
              <button
                type="button"
                role="option"
                class="hover:bg-accent flex w-full items-center justify-between gap-3 px-3 py-2 text-start text-sm"
                :class="selectedFloor === row.floor ? 'bg-accent' : ''"
                :aria-selected="selectedFloor === row.floor"
                @click="selectedFloor = row.floor"
              >
                <span class="font-semibold">طبقهٔ {{ formatBalance(row.floor) }}</span>
                <span v-if="row.teamName" class="text-xs" :class="row.isOwnTeam ? '' : 'text-muted-foreground'">
                  {{ row.teamName }}
                  <template v-if="row.isOwnTeam">(تیم شما)</template>
                </span>
                <span v-else class="text-muted-foreground text-xs">خالی است</span>
              </button>
            </li>
          </ul>
        </div>

        <DialogFooter class="flex-row gap-2 sm:justify-start">
          <Button
            :disabled="using || selectedFloor === null"
            :aria-busy="using"
            @click="confirmFloor"
          >
            <Loader2Icon v-if="using" class="size-4 animate-spin" />
            تأیید
          </Button>
          <DialogClose as-child>
            <Button variant="outline" :disabled="using">بازگشت</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
