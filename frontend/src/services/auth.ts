import { ensureCsrf, get, post } from '@/lib/http'
import type { LoginCredentials, Me } from '@/types/api'

export { ensureCsrf }

export function getMe(signal?: AbortSignal): Promise<Me> {
  return get<Me>('/auth/me/', signal)
}

export function login(credentials: LoginCredentials): Promise<Me> {
  return post<Me>('/auth/login/', credentials)
}

export function logout(): Promise<void> {
  return post<void>('/auth/logout/')
}
