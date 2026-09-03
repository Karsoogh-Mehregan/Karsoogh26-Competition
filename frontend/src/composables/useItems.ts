import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import { ApiError } from '@/lib/http'
import { useItemMutation, useItemsQuery } from '@/queries/items'
import type { ItemType, TeamItem } from '@/types/api'
import { useActing } from './useActing'

const NODE_ITEMS = new Set<ItemType>(['fake_document', 'gel'])

const SUCCESS: Record<ItemType, string> = {
  fake_document: 'سند جعلی استفاده شد.',
  gel: 'گل استفاده شد.',
  gilari_100: '۱۰۰ گیلاری مصرف شد!',
}

function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) {
      return error.detail || 'این کار در وضعیت فعلی ممکن نیست.'
    }
    if (error.status === 404) {
      return error.detail || 'این خانه پیدا نشد.'
    }
    if (error.status === 400) {
      return error.detail || 'درخواست نامعتبر است.'
    }
    return error.detail || 'خطا در ارتباط با سرور.'
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'خطا در ارتباط با سرور.'
}

export function useItems() {
  const { isPlayer } = useActing()
  const query = useItemsQuery(() => isPlayer.value)
  const mutation = useItemMutation()
  const actionError = ref('')

  const error = computed(() => {
    if (actionError.value) return actionError.value
    return query.error.value ? messageOf(query.error.value) : ''
  })

  function needsNode(itemType: ItemType): boolean {
    return NODE_ITEMS.has(itemType)
  }

  async function useItem(itemType: ItemType, nodeCode?: string): Promise<boolean> {
    actionError.value = ''
    try {
      await mutation.mutateAsync(
        needsNode(itemType) ? { item_type: itemType, node_code: nodeCode } : { item_type: itemType },
      )
      toast.success(SUCCESS[itemType])
      return true
    } catch (err) {
      actionError.value = messageOf(err)
      toast.error(actionError.value)
      return false
    }
  }

  return {
    items: computed<TeamItem[]>(() => query.data.value ?? []),
    loading: computed(() => query.isPending.value),
    using: computed(() => mutation.isPending.value),
    error,
    needsNode,
    useItem,
  }
}
