import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import { formatBalance } from '@/lib/format'
import { ApiError } from '@/lib/http'
import { useBuyOutMutation, useBuyoutTargetsQuery } from '@/queries/buyouts'
import type { BuyoutTarget } from '@/types/api'
import { useActing } from './useActing'

/**
 * The house panel's buyout facade.
 *
 * As with duels, the server answers a refusal with the sentence a player should
 * read — «فقط واحدهای ساختمان‌های مجاور خودتان را می‌توانید بخرید» and so on — so a
 * 409's detail is passed through verbatim and only shapeless failures get a
 * generic line.
 */
function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409 || error.status === 422) {
      return error.detail || 'این کار در وضعیت فعلی ممکن نیست.'
    }
    if (error.status === 403) {
      return error.detail || 'اجازهٔ این کار را ندارید.'
    }
    return error.detail || 'خطا در ارتباط با سرور.'
  }
  if (error instanceof Error) return error.message
  return 'خطا در ارتباط با سرور.'
}

export function useBuyouts() {
  const { isPlayer } = useActing()

  // Only a team has anything to buy; organisers browsing the map see no table.
  const targets = useBuyoutTargetsQuery(() => isPlayer.value)
  const mutation = useBuyOutMutation()
  const actionError = ref('')

  const error = computed(() => {
    if (actionError.value) return actionError.value
    return targets.error.value ? messageOf(targets.error.value) : ''
  })

  async function buy(target: BuyoutTarget): Promise<boolean> {
    actionError.value = ''
    try {
      const result = await mutation.mutateAsync(target.occupancy_id)
      const house = target.node_name || target.node_code
      toast.success(
        `طبقهٔ ${target.floor} «${house}» خریداری شد؛ موجودی: ${formatBalance(result.balance)}`,
      )
      return true
    } catch (err) {
      actionError.value = messageOf(err)
      toast.error(actionError.value)
      return false
    }
  }

  return {
    isPlayer,
    targets: computed<BuyoutTarget[]>(() => targets.data.value ?? []),
    loading: computed(() => targets.isPending.value && targets.isFetching.value),
    submitting: computed(() => mutation.isPending.value),
    error,
    refetch: () => targets.refetch(),
    buy,
  }
}
