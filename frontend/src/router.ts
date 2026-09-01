import { createRouter, createWebHistory } from 'vue-router'
import { queryClient } from '@/lib/queryClient'
import { meQueryOptions } from '@/queries/auth'
import GradingPage from '@/pages/GradingPage.vue'
import LeaderboardPage from '@/pages/LeaderboardPage.vue'
import MapPage from '@/pages/MapPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'map', component: MapPage },
    { path: '/grading', name: 'grading', component: GradingPage, meta: { requiresMentor: true } },
    { path: '/leaderboard', name: 'leaderboard', component: LeaderboardPage, meta: { requiresAuth: true } },
  ],
})

router.beforeEach(async (to) => {
  // Warmed here so the first render of any page already has `me` cached —
  // components then read it instantly via useMeQuery() with no loading flash.
  let me
  try {
    me = await queryClient.ensureQueryData(meQueryOptions)
  } catch {
    me = null
  }

  if (to.meta.requiresMentor && !me?.is_mentor) {
    return { name: 'map' }
  }
  if (to.meta.requiresAuth && !me) {
    return { name: 'map' }
  }
  return true
})
