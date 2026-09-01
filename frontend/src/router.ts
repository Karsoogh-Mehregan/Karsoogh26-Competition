import { createRouter, createWebHistory } from 'vue-router'
import GradingPage from '@/pages/GradingPage.vue'
import MapPage from '@/pages/MapPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'map', component: MapPage },
    { path: '/grading', name: 'grading', component: GradingPage },
  ],
})
