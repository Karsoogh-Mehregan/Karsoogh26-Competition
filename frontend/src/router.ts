import { createRouter, createWebHistory } from 'vue-router'
import { queryClient } from '@/lib/queryClient'
import { meQueryOptions } from '@/queries/auth'
import DesignPage from '@/pages/DesignPage.vue'
import GradingPage from '@/pages/GradingPage.vue'
import LeaderboardPage from '@/pages/LeaderboardPage.vue'
import MapPage from '@/pages/MapPage.vue'
import SolvePage from '@/pages/SolvePage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'map', component: MapPage },
    { path: '/grading/:id?', name: 'grading', component: GradingPage, meta: { requiresMentor: true } },
    { path: '/solve', name: 'solve', component: SolvePage, meta: { requiresPlayer: true } },
    { path: '/leaderboard', name: 'leaderboard', component: LeaderboardPage, meta: { requiresAuth: true } },
    { path: '/design', name: 'design', component: DesignPage, meta: { requiresDesigner: true } },
  ],
})

router.beforeEach(async (to) => {
  let me
  try {
    me = await queryClient.ensureQueryData(meQueryOptions)
  } catch {
    me = null
  }

  if (to.meta.requiresMentor && !me?.is_mentor) {
    return { name: 'map' }
  }
  if (to.meta.requiresPlayer && !me?.team) {
    return { name: 'map' }
  }
  if (to.meta.requiresDesigner && !me?.is_designer) {
    return { name: 'map' }
  }
  if (to.meta.requiresAuth && !me) {
    return { name: 'map' }
  }
  return true
})
