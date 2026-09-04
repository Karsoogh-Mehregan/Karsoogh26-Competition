import { createRouter, createWebHistory } from 'vue-router'
import { queryClient } from '@/lib/queryClient'
import { meQueryOptions } from '@/queries/auth'
import { eventCatalogQueryOptions } from '@/queries/events'
import DesignPage from '@/pages/DesignPage.vue'
import DuelsPage from '@/pages/DuelsPage.vue'
import GradingPage from '@/pages/GradingPage.vue'
import InboxPage from '@/pages/InboxPage.vue'
import LeaderboardPage from '@/pages/LeaderboardPage.vue'
import MessagePage from '@/pages/MessagePage.vue'
import MessagesPage from '@/pages/MessagesPage.vue'
import SentMessagePage from '@/pages/SentMessagePage.vue'
import BackpackPage from '@/pages/BackpackPage.vue'
import MapPage from '@/pages/MapPage.vue'
import TerritoryEventPage from '@/pages/TerritoryEventPage.vue'
import CharityBagPage from '@/pages/CharityBagPage.vue'
import CentipedeGamePage from '@/pages/CentipedeGamePage.vue'
import OlympicsPage from '@/pages/OlympicsPage.vue'
import SpecialGamesPage from '@/pages/SpecialGamesPage.vue'
import EventHubPage from '@/pages/EventHubPage.vue'
import MinesweeperPage from '@/pages/MinesweeperPage.vue'
import SolvePage from '@/pages/SolvePage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'map', component: MapPage },
    {
      path: '/events',
      name: 'events',
      component: EventHubPage,
      meta: { requiresAuth: true },
    },
    {
      path: '/events/territory-control',
      name: 'territory-event',
      component: TerritoryEventPage,
      meta: { requiresAuth: true, eventCode: 'territory_control' },
    },
    {
      path: '/events/charity-bag',
      name: 'charity-bag',
      component: CharityBagPage,
      meta: { requiresAuth: true, eventCode: 'charity_bag' },
    },
    {
      path: '/events/centipede-game',
      name: 'centipede-game',
      component: CentipedeGamePage,
      meta: { requiresAuth: true, eventCode: 'centipede' },
    },
    {
      path: '/events/coin-near-wall',
      name: 'coin-near-wall',
      component: OlympicsPage,
      meta: { requiresAuth: true, eventCode: 'olympics_coin' },
    },
    { path: '/events/marble-target', name: 'marble-target', component: OlympicsPage, meta: { requiresAuth: true, eventCode: 'olympics_marble' } },
    {
      path: '/events/auction',
      name: 'auction',
      component: SpecialGamesPage,
      meta: { requiresAuth: true, eventCode: 'limited_auction' },
    },
    { path: '/events/prize-wheel', name: 'prize-wheel', component: SpecialGamesPage, meta: { requiresAuth: true, eventCode: 'prize_wheel' } },
    { path: '/events/pig', name: 'pig', component: SpecialGamesPage, meta: { requiresAuth: true, eventCode: 'pig' } },
    { path: '/grading/:id?', name: 'grading', component: GradingPage, meta: { requiresMentor: true } },
    { path: '/solve', name: 'solve', component: SolvePage, meta: { requiresPlayer: true } },
    { path: '/backpack', name: 'backpack', component: BackpackPage, meta: { requiresPlayer: true } },
    {
      path: '/minesweeper/node/:id',
      name: 'minesweeper-node',
      component: MinesweeperPage,
      meta: { requiresPlayer: true },
    },
    // Open to teams and to duel judges alike; the page shows each their half,
    // and the API refuses whatever the viewer is not entitled to anyway.
    { path: '/duels', name: 'duels', component: DuelsPage, meta: { requiresAuth: true } },
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
  if (to.meta.eventCode && !me?.is_mentor) {
    try {
      const catalog = await queryClient.fetchQuery(eventCatalogQueryOptions)
      if (!catalog.some((event) => event.code === to.meta.eventCode && event.enabled)) return { name: 'events' }
    } catch {
      return { name: 'events' }
    }
  }
  return true
})
