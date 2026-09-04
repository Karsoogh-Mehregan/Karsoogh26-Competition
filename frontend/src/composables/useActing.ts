import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { ApiError } from '@/lib/http'
import { useLoginMutation, useLogoutMutation, useMeQuery } from '@/queries/auth'
import { useAssignQuestionMutation } from '@/queries/game'
import { useClaimStartMutation, useTeamsQuery } from '@/queries/teams'
import { router } from '@/router'
import { useActingStore } from '@/stores/acting'
import { useAttemptStore } from '@/stores/attempt'
import type { AssignQuestionResult, Team } from '@/types/api'
import { useGraph } from './useGraph.js'

function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'خطا در ارتباط با سرور.'
}

export function useActing() {
  const store = useActingStore()

  const meQuery = useMeQuery()
  const isAuthenticated = () => meQuery.data.value != null
  const teamsQuery = useTeamsQuery(isAuthenticated)

  const loginMutation = useLoginMutation()
  const logoutMutation = useLogoutMutation()
  const claimStartMutation = useClaimStartMutation()
  const assignQuestionMutation = useAssignQuestionMutation()

  const actionError = ref('')

  const me = computed(() => meQuery.data.value ?? null)
  const teams = computed<Team[]>(() => teamsQuery.data.value ?? [])
  const isMentor = computed(() => me.value?.is_mentor ?? false)
  // Running the event is a narrower right than grading for it.
  const isGameGod = computed(() => me.value?.is_game_god ?? false)
  // Backed by its own permission, so it is not the same set as isGameGod.
  const isAnnouncer = computed(() => me.value?.is_announcer ?? false)
  const isPlayer = computed(() => me.value != null && me.value.team != null)
  const ownTeamCode = computed(() => me.value?.team?.code ?? null)

  const actingTeam = computed<Team | null>(() => {
    if (isPlayer.value && ownTeamCode.value) {
      return teams.value.find((team) => team.code === ownTeamCode.value) ?? null
    }
    if (!isMentor.value) {
      return null
    }
    return teams.value.find((team) => team.code === store.actingCode) ?? null
  })

  watch(
    [isPlayer, ownTeamCode],
    ([player, code]) => {
      if (player && code) {
        store.setActingCode(code)
      }
    },
    { immediate: true },
  )

  const loading = computed(
    () => meQuery.isPending.value || (isAuthenticated() && teamsQuery.isPending.value),
  )
  const submitting = computed(() => loginMutation.isPending.value || logoutMutation.isPending.value)
  const error = computed(() => {
    if (actionError.value) {
      return actionError.value
    }
    const queryError = meQuery.error.value ?? teamsQuery.error.value
    return queryError ? messageOf(queryError) : ''
  })

  async function login(username: string, password: string): Promise<void> {
    actionError.value = ''
    try {
      await loginMutation.mutateAsync({ username, password })
      const code = meQuery.data.value?.team?.code
      if (code) {
        store.setActingCode(code)
      }
    } catch (err) {
      actionError.value =
        err instanceof ApiError && err.status === 400
          ? 'نام کاربری یا رمز عبور نادرست است.'
          : messageOf(err)
    }
  }

  async function logout(): Promise<void> {
    actionError.value = ''
    try {
      await logoutMutation.mutateAsync()
      store.setActingCode(null)
      useAttemptStore().select(null)
      useGraph().reset()
      await router.replace({ name: 'map' })
    } catch (err) {
      actionError.value = messageOf(err)
    }
  }

  function actAs(team: Team | null): void {
    if (isPlayer.value || !isMentor.value || team == null) {
      return
    }
    if (!store.setActingCode(team.code)) {
      return
    }
    actionError.value = ''
    useGraph().reset()
    toast.success(`تیم «${team.name}» انتخاب شد`)
  }

  async function claimStart(nodeId: string): Promise<Team> {
    const teamCode = actingTeam.value?.code
    if (!teamCode) {
      throw new Error('ابتدا یک تیم انتخاب کنید.')
    }
    return claimStartMutation.mutateAsync({ teamCode, node: nodeId })
  }

  async function assignQuestion(nodeCode: string): Promise<AssignQuestionResult> {
    const teamCode = actingTeam.value?.code
    if (!teamCode) {
      throw new Error('ابتدا یک تیم انتخاب کنید.')
    }
    return assignQuestionMutation.mutateAsync({ teamCode, nodeCode })
  }

  return {
    me,
    teams,
    actingTeam,
    isMentor,
    isGameGod,
    isAnnouncer,
    isPlayer,
    loading,
    error,
    submitting,
    login,
    logout,
    actAs,
    claimStart,
    assignQuestion,
  }
}
