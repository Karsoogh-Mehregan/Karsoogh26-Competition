<script setup lang="ts">
/**
 * The Designer's page: the map-wide knobs.
 *
 * Neighbourhood names, themes and colours; road style; and how strongly the
 * sectors and node halos are painted. Per-node pins live in the house panel
 * on the map, where the model doubles as a live preview.
 */
import { Loader2Icon, PaintbrushIcon } from '@lucide/vue'
import { computed, reactive, ref, watch } from 'vue'
import { toast } from 'vue-sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { useMapDesign } from '@/composables/useMapDesign'
import { THEME_LIST } from '@/lib/house/themes'
import { ApiError } from '@/lib/http'
import { useUpdateMapDesignMutation } from '@/queries/design'
import type { Neighborhood, RoadStyle } from '@/types/api'

const { me } = useActing()
const { design, loading, neighborhoods } = useMapDesign()
const { mutateAsync: save, isPending: saving } = useUpdateMapDesignMutation()

const isDesigner = computed(() => me.value?.is_designer ?? false)

const ROAD_STYLES: { value: RoadStyle; label: string; hint: string }[] = [
  { value: 'straight', label: 'مستقیم', hint: 'خط راست بین دو خانه.' },
  { value: 'curved', label: 'منحنی', hint: 'کمی قوس، مثل یک کوچهٔ پیچ‌دار.' },
  { value: 'dashed', label: 'خط‌چین', hint: 'مسیرهای نیمه‌ساخته.' },
]

// Local drafts, seeded from the query and re-seeded when it changes.
const roadStyle = ref<RoadStyle>('straight')
const tint = ref(8)
const halo = ref(45)
const rows = reactive<Neighborhood[]>([])

watch(
  [design, neighborhoods],
  ([current, list]) => {
    if (!current) return
    roadStyle.value = current.road_style
    tint.value = current.tint_strength
    halo.value = current.halo_strength
    rows.splice(0, rows.length, ...list.map((row) => ({ ...row })))
  },
  { immediate: true },
)

const themeLabel = (key: string) => THEME_LIST.find((theme) => theme.key === key)?.label ?? key

async function saveSettings() {
  try {
    await save({ road_style: roadStyle.value, tint_strength: tint.value, halo_strength: halo.value })
    toast.success('تنظیمات نقشه ذخیره شد')
  } catch (error) {
    toast.error(error instanceof ApiError ? error.detail : 'ذخیره ناموفق بود.')
  }
}

async function saveNeighborhoods() {
  try {
    await save({
      neighborhoods: rows.map((row) => ({
        index: row.index,
        name: row.name,
        theme: row.theme,
        color: row.color.toLowerCase(),
      })),
    })
    toast.success('محله‌ها ذخیره شدند')
  } catch (error) {
    toast.error(error instanceof ApiError ? error.detail : 'ذخیره ناموفق بود.')
  }
}
</script>

<template>
  <div class="h-full overflow-y-auto p-6">
    <div class="mx-auto flex w-full max-w-3xl flex-col gap-5">
      <header class="flex items-center gap-2">
        <PaintbrushIcon class="text-muted-foreground size-5" />
        <h1 class="text-lg font-bold">طراحی نقشه</h1>
      </header>

      <p v-if="!isDesigner" class="text-muted-foreground text-sm">این صفحه فقط برای طراحان است.</p>

      <div v-else-if="loading" class="flex flex-col gap-3">
        <Skeleton class="h-40 w-full" />
        <Skeleton class="h-72 w-full" />
      </div>

      <template v-else>
        <Card>
          <CardHeader>
            <CardTitle>جاده‌ها و شدت رنگ</CardTitle>
            <CardDescription>
              رنگ محله پشت نقشه می‌نشیند و دور هر خانه یک حلقه می‌کشد. هر دو را ملایم نگه دارید.
            </CardDescription>
          </CardHeader>
          <CardContent class="flex flex-col gap-5">
            <fieldset class="flex flex-col gap-2">
              <legend class="mb-1 text-sm font-medium">طرح جاده</legend>
              <div class="flex flex-wrap gap-2">
                <Button
                  v-for="style in ROAD_STYLES"
                  :key="style.value"
                  type="button"
                  size="sm"
                  :variant="roadStyle === style.value ? 'default' : 'outline'"
                  :title="style.hint"
                  @click="roadStyle = style.value"
                >
                  {{ style.label }}
                </Button>
              </div>
            </fieldset>

            <div class="grid gap-4 sm:grid-cols-2">
              <div class="flex flex-col gap-1.5">
                <Label for="tint">رنگ پس‌زمینهٔ محله — {{ tint }}٪</Label>
                <input id="tint" v-model.number="tint" type="range" min="0" max="60" class="w-full" />
              </div>
              <div class="flex flex-col gap-1.5">
                <Label for="halo">حلقهٔ دور خانه‌ها — {{ halo }}٪</Label>
                <input id="halo" v-model.number="halo" type="range" min="0" max="100" class="w-full" />
              </div>
            </div>

            <Button class="self-start" :disabled="saving" :aria-busy="saving" @click="saveSettings">
              <Loader2Icon v-if="saving" class="size-4 animate-spin" />
              ذخیرهٔ تنظیمات
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>محله‌ها</CardTitle>
            <CardDescription>
              نقشه هشت برش دارد. نه تم در دسترس است؛ هر برش یکی می‌گیرد. تم شکل و پالت
              ساختمان‌های آن برش را تعیین می‌کند، و رنگ فقط روی نقشهٔ دوبعدی می‌نشیند.
            </CardDescription>
          </CardHeader>
          <CardContent class="flex flex-col gap-3">
            <div
              v-for="row in rows"
              :key="row.index"
              class="grid items-end gap-3 rounded-lg border p-3 sm:grid-cols-[auto_1fr_1fr_auto]"
            >
              <Badge variant="secondary" class="tabular-nums">برش {{ row.index + 1 }}</Badge>
              <div class="flex flex-col gap-1.5">
                <Label :for="`name-${row.index}`">نام</Label>
                <Input :id="`name-${row.index}`" v-model="row.name" />
              </div>
              <div class="flex flex-col gap-1.5">
                <Label :for="`theme-${row.index}`">تم</Label>
                <select :id="`theme-${row.index}`" v-model="row.theme" class="design-select">
                  <option v-for="theme in THEME_LIST" :key="theme.key" :value="theme.key">
                    {{ theme.label }} — {{ theme.symbol }}
                  </option>
                </select>
              </div>
              <div class="flex flex-col gap-1.5">
                <Label :for="`color-${row.index}`">رنگ</Label>
                <input
                  :id="`color-${row.index}`"
                  v-model="row.color"
                  type="color"
                  class="design-color"
                  :title="themeLabel(row.theme)"
                />
              </div>
            </div>

            <Button class="self-start" :disabled="saving" :aria-busy="saving" @click="saveNeighborhoods">
              <Loader2Icon v-if="saving" class="size-4 animate-spin" />
              ذخیرهٔ محله‌ها
            </Button>
          </CardContent>
        </Card>

        <p class="text-muted-foreground text-xs">
          نوع و سطح هر خانه را از روی نقشه تنظیم کنید: روی خانه بزنید و در پنل کناری بخش «طراحی» را ببینید.
        </p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.design-select {
  block-size: 2.25rem;
  inline-size: 100%;
  border: 1px solid var(--input);
  border-radius: 0.5rem;
  background: transparent;
  padding-inline: 0.6rem;
  font-size: 0.85rem;
  color: var(--foreground);
}
.design-color {
  block-size: 2.25rem;
  inline-size: 3.2rem;
  border: 1px solid var(--input);
  border-radius: 0.5rem;
  background: transparent;
  padding: 0.15rem;
  cursor: pointer;
}
</style>
