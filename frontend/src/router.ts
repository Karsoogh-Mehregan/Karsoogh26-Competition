import { createRouter, createWebHistory } from 'vue-router'
import { queryClient } from '@/lib/queryClient'
import { meQueryOptions } from '@/queries/auth'
import { eventCatalogQueryOptions } from '@/queries/events'
import GradingPage from '@/pages/GradingPage.vue'
import LeaderboardPage from '@/pages/LeaderboardPage.vue'
import MapPage from '@/pages/MapPage.vue'
import TerritoryEventPage from '@/pages/TerritoryEventPage.vue'
import CharityBagPage from '@/pages/CharityBagPage.vue'
import CentipedeGamePage from '@/pages/CentipedeGamePage.vue'
import OlympicsPage from '@/pages/OlympicsPage.vue'
import SpecialGamesPage from '@/pages/SpecialGamesPage.vue'
import EventHubPage from '@/pages/EventHubPage.vue'

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
