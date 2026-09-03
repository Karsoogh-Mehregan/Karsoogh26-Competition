<script setup lang="ts">
import { computed } from 'vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useItems } from '@/composables/useItems'
import { formatBalance } from '@/lib/format'

const { items, loading, error } = useItems()

const hasItems = computed(() => items.value.length > 0)
</script>

<template>
  <div class="h-full overflow-y-auto p-6">
    <div class="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <header>
        <h1 class="text-lg font-bold">کوله پشتی</h1>
        <p class="text-muted-foreground mt-1 text-sm">اقلام تیم شما.</p>
      </header>

      <p v-if="error" class="text-destructive text-sm">{{ error }}</p>

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
        </Card>
      </div>
    </div>
  </div>
</template>
