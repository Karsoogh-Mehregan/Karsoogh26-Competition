import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import { ApiError } from '@/lib/http'
import {
  useDuelBoardQuery,
  useDuelTargetsQuery,
  useRequestDuelMutation,
  useResolveDuelMutation,
} from '@/queries/duels'
import type { Duel, DuelTarget } from '@/types/api'
import { useActing } from './useActing'

/**
 * The duel page's facade.
 *
 * Persian copy lives here rather than in the transport, as everywhere else in
 * this layer. The server already answers a refusal with the sentence a player
 * should read — «فقط به ساختمان‌های مجاور خودتان می‌توانید دوئل بزنید» and so on —
 * so a 409's detail is passed through verbatim and only the shapeless failures
 * get a generic line.
 */
function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409 || error.status === 422) {
      return error.detail || 'این کار در وضعیت فعلی ممکن نیست.'
    }
    if (error.status === 403) {
      return error.detail || 'اجازهٔ این کار را ندارید.'
    }
    if (error.status === 404) {
      return error.detail || 'پیدا نشد.'
    }
    return error.detail || 'خطا در ارتباط با سرور.'
  }
  if (error instanceof Error) return error.message
  return 'خطا در ارتباط با سرور.'
}

export function useDuels() {
  const { me, isPlayer } = useActing()

  const isDuelMentor = computed(() => me.value?.is_duel_mentor ?? false)
  const canSeeDuels = () => isPlayer.value || isDuelMentor.value

  const board = useDuelBoardQuery(canSeeDuels)
  // Only a team has anyone to challenge, and only when it is not already busy:
  // asking for the table while a duel is open would list rows the API would
  // refuse anyway.
  const targets = useDuelTargetsQuery(() => isPlayer.value && !board.data.value?.active)

  const requestMutation = useRequestDuelMutation()
  const resolveMutation = useResolveDuelMutation()
  const actionError = ref('')

  const error = computed(() => {
    if (actionError.value) return actionError.value
    const queryError = board.error.value ?? targets.error.value
    return queryError ? messageOf(queryError) : ''
  })

  async function challenge(target: DuelTarget): Promise<boolean> {
    actionError.value = ''
    try {
      await requestMutation.mutateAsync(target.occupancy_id)
      toast.success(`درخواست دوئل به تیم «${target.team.name}» ثبت شد.`)
      return true
    } catch (err) {
      actionError.value = messageOf(err)
      toast.error(actionError.value)
      return false
    }
  }

  async function callWinner(duel: Duel, winnerCode: string): Promise<boolean> {
    actionError.value = ''
    try {
      await resolveMutation.mutateAsync({ duelId: duel.id, winnerCode })
      toast.success('نتیجهٔ دوئل ثبت شد.')
      return true
    } catch (err) {
      actionError.value = messageOf(err)
      toast.error(actionError.value)
      return false
    }
  }

  return {
    isDuelMentor,
    isPlayer,
    active: computed<Duel | null>(() => board.data.value?.active ?? null),
    history: computed<Duel[]>(() => board.data.value?.history ?? []),
    judging: computed<Duel | null>(() => board.data.value?.judging ?? null),
    judged: computed<Duel[]>(() => board.data.value?.judged ?? []),
    canRequest: computed(() => board.data.value?.can_request ?? false),
    blockedReason: computed(() => board.data.value?.blocked_reason ?? ''),
    targets: computed<DuelTarget[]>(() => targets.data.value ?? []),
    loading: computed(() => board.isPending.value),
    targetsLoading: computed(() => targets.isPending.value && targets.isFetching.value),
    submitting: computed(
      () => requestMutation.isPending.value || resolveMutation.isPending.value,
    ),
    error,
    refetch: () => Promise.all([board.refetch(), targets.refetch()]),
    challenge,
    callWinner,
  }
}
