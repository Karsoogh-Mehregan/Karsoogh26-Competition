import { createRouter, createWebHistory } from 'vue-router'
import { queryClient } from '@/lib/queryClient'
import { meQueryOptions } from '@/queries/auth'
import DesignPage from '@/pages/DesignPage.vue'
import GradingPage from '@/pages/GradingPage.vue'
import InboxPage from '@/pages/InboxPage.vue'
import LeaderboardPage from '@/pages/LeaderboardPage.vue'
import MessagePage from '@/pages/MessagePage.vue'
import MessagesPage from '@/pages/MessagesPage.vue'
import SentMessagePage from '@/pages/SentMessagePage.vue'
import MapPage from '@/pages/MapPage.vue'
import MinesweeperPage from '@/pages/MinesweeperPage.vue'
import SolvePage from '@/pages/SolvePage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'map', component: MapPage },
    { path: '/grading', name: 'grading', component: GradingPage, meta: { requiresMentor: true } },
    { path: '/solve', name: 'solve', component: SolvePage, meta: { requiresPlayer: true } },
    {
      path: '/minesweeper/node/:id',
      name: 'minesweeper-node',
      component: MinesweeperPage,
      meta: { requiresPlayer: true },
    },
    { path: '/leaderboard', name: 'leaderboard', component: LeaderboardPage, meta: { requiresAuth: true } },
    { path: '/inbox', name: 'inbox', component: InboxPage, meta: { requiresAuth: true } },
    { path: '/inbox/:id', name: 'message', component: MessagePage, meta: { requiresAuth: true } },
    { path: '/messages', name: 'messages', component: MessagesPage, meta: { requiresAnnouncer: true } },
    {
      path: '/messages/:id',
      name: 'sent-message',
      component: SentMessagePage,
      meta: { requiresAnnouncer: true },
    },
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
  // Each of these is gated on the same right the API checks; the guard only
  // keeps a page from rendering a form that would 403 on submit.
  if (to.meta.requiresAnnouncer && !me?.is_announcer) {
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
