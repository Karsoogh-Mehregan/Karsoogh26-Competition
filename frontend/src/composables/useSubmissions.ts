import { computed } from 'vue'
import { ApiError } from '@/lib/http'
import { useMeQuery } from '@/queries/auth'
import { useSubmissionsQuery } from '@/queries/game'
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

  const submissions = computed<SubmissionRow[]>(() => submissionsQuery.data.value ?? [])
  const loading = computed(() => submissionsQuery.isPending.value)
  const error = computed(() =>
    submissionsQuery.error.value ? messageOf(submissionsQuery.error.value) : '',
  )

  return {
    submissions,
    loading,
    error,
  }
}
