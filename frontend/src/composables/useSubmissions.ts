import { computed, ref } from 'vue'
import { ApiError } from '@/lib/http'
import { useMeQuery } from '@/queries/auth'
import { useGradeSubmissionMutation, useSubmissionsQuery } from '@/queries/game'
import type { SubmissionRow } from '@/types/api'

function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'خطا در ارتباط با سرور.'
}

export function useSubmissions() {
  const meQuery = useMeQuery()
  const isAuthenticated = () => meQuery.data.value != null
  const submissionsQuery = useSubmissionsQuery(isAuthenticated)
  const gradeMutation = useGradeSubmissionMutation()
  const actionError = ref('')

  const submissions = computed<SubmissionRow[]>(() => submissionsQuery.data.value ?? [])
  const loading = computed(() => submissionsQuery.isPending.value)
  const error = computed(() => {
    if (actionError.value) return actionError.value
    return submissionsQuery.error.value ? messageOf(submissionsQuery.error.value) : ''
  })
  const submitting = computed(() => gradeMutation.isPending.value)

  async function grade(submissionId: number, value: number): Promise<boolean> {
    actionError.value = ''
    try {
      await gradeMutation.mutateAsync({ submissionId, grade: value })
      return true
    } catch (err) {
      actionError.value = messageOf(err)
      return false
    }
  }

  return {
    submissions,
    loading,
    error,
    submitting,
    grade,
  }
}
