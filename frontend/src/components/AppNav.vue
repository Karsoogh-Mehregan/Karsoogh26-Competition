<script setup>
import { Gamepad2Icon, SwordsIcon } from '@lucide/vue'
import { RouterLink, useRoute } from 'vue-router'
import { Button } from '@/components/ui/button'
import { useActing } from '@/composables/useActing'
import { useMapDesign } from '@/composables/useMapDesign'

const { me, isMentor, isAnnouncer, isPlayer } = useActing()
const { canDesign } = useMapDesign()
const route = useRoute()
</script>

<template>
  <nav v-if="me" class="app-nav" aria-label="صفحات بازی">
    <Button as-child size="sm" :variant="route.path === '/' ? 'default' : 'outline'">
      <RouterLink to="/" :aria-current="route.path === '/' ? 'page' : undefined">
        نقشه
      </RouterLink>
    </Button>
    <Button
      v-if="isMentor"
      as-child
      size="sm"
      :variant="route.path === '/grading' ? 'default' : 'outline'"
    >
      <RouterLink
        to="/grading"
        :aria-current="route.path === '/grading' ? 'page' : undefined"
      >
        نمره‌دهی
      </RouterLink>
    </Button>
    <Button
      v-if="isPlayer"
      as-child
      size="sm"
      :variant="route.path === '/solve' ? 'default' : 'outline'"
    >
      <RouterLink
        to="/solve"
        :aria-current="route.path === '/solve' ? 'page' : undefined"
      >
        حل سؤال
      </RouterLink>
    </Button>
    <Button
      v-if="isPlayer"
      as-child
      size="sm"
      :variant="route.path === '/backpack' ? 'default' : 'outline'"
    >
      <RouterLink
        to="/backpack"
        :aria-current="route.path === '/backpack' ? 'page' : undefined"
      >
        کوله پشتی
      </RouterLink>
    </Button>
    <Button as-child size="sm" :variant="route.path === '/leaderboard' ? 'default' : 'outline'">
      <RouterLink
        to="/leaderboard"
        :aria-current="route.path === '/leaderboard' ? 'page' : undefined"
      >
        جدول امتیازات
      </RouterLink>
    </Button>
    <Button as-child size="sm" :variant="route.path === '/events' ? 'default' : 'outline'">
      <RouterLink to="/events" :aria-current="route.path === '/events' ? 'page' : undefined">
        <Gamepad2Icon class="size-3.5" />
        همه رویدادها
      </RouterLink>
    </Button>
    <Button
      v-if="isPlayer || me.is_duel_mentor"
      as-child
      size="sm"
      :variant="route.path === '/duels' ? 'default' : 'outline'"
    >
      <RouterLink to="/duels" :aria-current="route.path === '/duels' ? 'page' : undefined">
        <SwordsIcon class="size-3.5" />
        دوئل‌ها
      </RouterLink>
    </Button>
    <Button as-child size="sm" :variant="route.path === '/inbox' ? 'default' : 'outline'">
      <RouterLink to="/inbox" :aria-current="route.path === '/inbox' ? 'page' : undefined">
        پیام‌ها
      </RouterLink>
    </Button>
    <Button
      v-if="isAnnouncer"
      as-child
      size="sm"
      :variant="route.path === '/messages' ? 'default' : 'outline'"
    >
      <RouterLink
        to="/messages"
        :aria-current="route.path === '/messages' ? 'page' : undefined"
      >
        نوشتن پیام
      </RouterLink>
    </Button>
    <Button
      v-if="canDesign"
      as-child
      size="sm"
      :variant="route.path === '/design' ? 'default' : 'outline'"
    >
      <RouterLink to="/design" :aria-current="route.path === '/design' ? 'page' : undefined">
        طراحی
      </RouterLink>
    </Button>
  </nav>
</template>

<style scoped>
.app-nav {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}
</style>
