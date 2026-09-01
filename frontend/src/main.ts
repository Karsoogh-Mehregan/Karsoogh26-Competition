import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import { queryClient } from './lib/queryClient'
import { router } from './router'

const app = createApp(App)
  .use(createPinia())
  .use(router)
  .use(VueQueryPlugin, { queryClient })

// Wait for the first navigation (and its beforeEach guard, which warms `me`)
// so the app never mounts to a flash of the wrong logged-in state.
router.isReady().then(() => app.mount('#app'))
