import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'


// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    tailwindcss()
  ],
  resolve : {
    alias : {
      '@' : '/src'
    }
  },
  server: {
    // Windows-side edits on a WSL-mounted drive do not emit native watcher events.
    watch: process.env.WSL_DISTRO_NAME ? { usePolling: true, interval: 1000 } : undefined,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
