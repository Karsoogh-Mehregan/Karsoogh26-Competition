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
import { useGraph } from '@/composables/useGraph.js'
import { useItems } from '@/composables/useItems'
import { useMapDesign } from '@/composables/useMapDesign'
import { formatBalance } from '@/lib/format'
import { LEVEL_LABEL, type Level } from '@/lib/mapLevels'
import type { TeamItem } from '@/types/api'

interface GraphNode {
  id: string
  type: string
}

const { items, loading, using, error, needsNode, useItem } = useItems()
const { nodes } = useGraph() as { nodes: GraphNode[] }
const { levelOf, isGelled } = useMapDesign()

const hasItems = computed(() => items.value.length > 0)
const pickingGel = computed(() => pickerItem.value?.item_type === 'gel')

const pickerOpen = ref(false)
const pickerItem = ref<TeamItem | null>(null)
const selectedCode = ref('')
const nodeQuery = ref('')

const pickerNodes = computed(() => {
  const rows = nodes as GraphNode[]
  if (pickingGel.value) {
    return rows.filter((node) => {
      const level = levelOf(node.id, node.type)
      return node.id !== 'CENTER' && level !== 'center' && !isGelled(node.id)
    })
  }
  return rows.filter((node) => {
    const level = levelOf(node.id, node.type)
    return level !== 'spawn' && level !== 'toll'
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

function levelLabel(node: GraphNode): string {
  const level: Level = levelOf(node.id, node.type)
  return LEVEL_LABEL[level]
}

function closePicker() {
  pickerOpen.value = false
  pickerItem.value = null
  selectedCode.value = ''
  nodeQuery.value = ''
}

function onPickerOpen(open: boolean) {
  if (!open) closePicker()
}

async function onUse(item: TeamItem) {
  if (needsNode(item.item_type)) {
    pickerItem.value = item
    selectedCode.value = ''
    nodeQuery.value = ''
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
              خانه‌ای را که می‌خواهید گل بگیرید انتخاب کنید. مرکز شهر قابل انتخاب نیست.
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
                @click="selectedCode = node.id"
              >
                <span class="font-semibold tabular-nums">{{ node.id }}</span>
                <span v-if="!pickingGel" class="text-muted-foreground text-xs">{{
                  levelLabel(node)
                }}</span>
              </button>
            </li>
          </ul>
        </div>

        <DialogFooter class="flex-row gap-2 sm:justify-start">
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
  </div>
</template>
