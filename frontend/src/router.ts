import { createRouter, createWebHistory } from 'vue-router'
import { queryClient } from '@/lib/queryClient'
import { meQueryOptions } from '@/queries/auth'
import GradingPage from '@/pages/GradingPage.vue'
import LeaderboardPage from '@/pages/LeaderboardPage.vue'
import MessagesPage from '@/pages/MessagesPage.vue'
import MapPage from '@/pages/MapPage.vue'
import SolvePage from '@/pages/SolvePage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'map', component: MapPage },
    { path: '/grading', name: 'grading', component: GradingPage, meta: { requiresMentor: true } },
    { path: '/solve', name: 'solve', component: SolvePage, meta: { requiresPlayer: true } },
    { path: '/leaderboard', name: 'leaderboard', component: LeaderboardPage, meta: { requiresAuth: true } },
    { path: '/messages', name: 'messages', component: MessagesPage, meta: { requiresAnnouncer: true } },
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
  // Composing is gated on the same right the API checks; the guard only keeps
  // the page from rendering a form that would 403 on submit.
  if (to.meta.requiresAnnouncer && !me?.is_announcer) {
    return { name: 'map' }
  }
  if (to.meta.requiresAuth && !me) {
    return { name: 'map' }
  }
  return true
})
