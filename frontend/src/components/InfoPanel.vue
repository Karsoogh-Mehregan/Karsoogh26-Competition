<script setup>
import {
  CheckIcon,

  CoinsIcon,

  SearchIcon,
  Gamepad2Icon,
} from '@lucide/vue'
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { formatBalance, formatSignedBalance } from '@/lib/format'
import { useActing } from '../composables/useActing'
import { useBalanceEvents } from '../composables/useBalanceEvents'

const {
  me,
  teams,
  actingTeam,
  isMentor,
  isAnnouncer,
  isPlayer,
  loading,
  error,
  submitting,
  login,
  actAs,
  logout,
} = useActing()
const { balanceEvents, ledgerLoading, ledgerError } = useBalanceEvents()
const route = useRoute()

const username = ref('')
const password = ref('')
const query = ref('')

async function onLogin() {
  await login(username.value, password.value)
}

function normalize(value) {
  return value
    .trim()
    .toLowerCase()
    .replace(/ي/g, 'ی')
    .replace(/ك/g, 'ک')
    .replace(/\u200c/g, '')
}

const listedTeams = computed(() => {
  const q = normalize(query.value)
  if (!q) {
    return teams.value
  }
  return teams.value.filter(
    (team) => normalize(team.name).includes(q) || normalize(team.code).includes(q),
  )
})

function isSelected(team) {
  return actingTeam.value?.code === team.code
}

const showTeamPicker = computed(() => isMentor.value || isPlayer.value)
</script>

<template>
  <aside class="flex h-full w-full shrink-0 flex-col overflow-hidden border-e bg-card">
    <header class="border-b px-5 py-4">
      <h1 class="text-lg font-bold">{{ isPlayer && !isMentor ? 'تیم شما' : 'تیم‌ها' }}</h1>
      <p v-if="actingTeam" class="text-muted-foreground mt-1 text-sm">
        در حال بازی به‌عنوان
        <span class="text-foreground inline-flex items-center gap-1.5 font-semibold">
          <span
            v-if="actingTeam.color"
            class="size-3 shrink-0 rounded-full border"
            :style="{ backgroundColor: actingTeam.color }"
          />
          {{ actingTeam.name }}
        </span>
      </p>
      <p v-else-if="me" class="text-muted-foreground mt-1 text-sm">
        {{ isMentor ? 'یک تیم را انتخاب کنید' : 'تیم شما روی نقشه مشخص است' }}
      </p>
      <p v-else class="text-muted-foreground mt-1 text-sm">
        برای دیدن تیم‌ها وارد شوید
      </p>
      <nav v-if="me" class="mt-3 flex flex-wrap gap-2">
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
          v-if="me.is_designer"
          as-child
          size="sm"
          :variant="route.path === '/design' ? 'default' : 'outline'"
        >
          <RouterLink to="/design" :aria-current="route.path === '/design' ? 'page' : undefined">
            طراحی
          </RouterLink>
        </Button>
      </nav>
    </header>

    <div class="flex min-h-0 flex-1 flex-col overflow-hidden px-5 py-4">
      <p v-if="error" class="text-destructive mb-3 text-sm">{{ error }}</p>

      <div v-if="loading" class="flex flex-col gap-2">
        <Skeleton class="h-12 w-full" />
        <Skeleton class="h-12 w-full" />
        <Skeleton class="h-12 w-full" />
      </div>

      <form v-else-if="!me" class="flex flex-col gap-3 overflow-y-auto" @submit.prevent="onLogin">
        <div class="flex flex-col gap-1.5">
          <Label for="username">نام کاربری</Label>
          <Input
            id="username"
            v-model="username"
            autocomplete="username"
            :disabled="submitting"
          />
        </div>
        <div class="flex flex-col gap-1.5">
          <Label for="password">رمز عبور</Label>
          <Input
            id="password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            :disabled="submitting"
          />
        </div>
        <Button type="submit" :disabled="submitting || !username || !password">
          ورود
        </Button>
      </form>

      <template v-else-if="showTeamPicker">
        <div v-if="isMentor" class="relative mb-3 shrink-0">
          <Label for="team-search" class="sr-only">جستجوی تیم</Label>
          <SearchIcon
            class="text-muted-foreground pointer-events-none absolute top-1/2 start-3 size-4 -translate-y-1/2"
          />
          <Input
            id="team-search"
            v-model="query"
            type="search"
            autocomplete="off"
            class="ps-9"
            placeholder="جستجو با نام یا کد تیم"
          />
        </div>
        <ul v-if="isMentor" class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
          <li v-for="team in listedTeams" :key="team.code">
            <Button
              class="h-auto w-full items-start justify-between py-3 whitespace-normal"
              :variant="isSelected(team) ? 'default' : 'outline'"
              @click="actAs(team)"
            >
              <span class="flex min-w-0 flex-col items-start gap-0.5 text-start">
                <span class="flex items-center gap-2 font-semibold">
                  <span
                    v-if="team.color"
                    class="size-3 shrink-0 rounded-full border"
                    :style="{ backgroundColor: team.color }"
                  />
                  {{ team.name }}
                </span>
                <span class="text-xs opacity-80">{{ team.code }}</span>
              </span>
              <Badge v-if="isSelected(team)" variant="secondary" class="gap-1">
                <CheckIcon class="size-3" />
                انتخاب‌شده
              </Badge>
            </Button>
          </li>
        </ul>

        <div v-else-if="isPlayer" class="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
          <div class="rounded-xl border px-4 py-3">
            <div class="flex items-center gap-2">
              <CoinsIcon class="text-muted-foreground size-4 shrink-0" />
              <span class="font-semibold">گیلریوم</span>
              <span class="ms-auto text-xl leading-none font-bold tabular-nums">
                {{ formatBalance(actingTeam?.balance) }}
              </span>
            </div>
          </div>

          <div class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border">
            <p v-if="ledgerError" class="text-destructive px-3 py-2 text-sm">{{ ledgerError }}</p>
            <div v-else-if="ledgerLoading" class="flex flex-col gap-2 p-3">
              <Skeleton class="h-12 w-full" />
              <Skeleton class="h-12 w-full" />
            </div>
            <p
              v-else-if="balanceEvents.length === 0"
              class="text-muted-foreground px-3 py-3 text-sm"
            >
              هنوز تغییری در امتیاز ثبت نشده است.
            </p>
            <ul v-else class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-2">
              <li
                v-for="event in balanceEvents"
                :key="event.id"
                class="bg-muted/40 rounded-md border px-3 py-2 text-sm"
              >
                <div class="flex items-baseline justify-between gap-2">
                  <span class="font-medium">{{ event.reason_label }}</span>
                  <span
                    class="shrink-0 font-bold tabular-nums"
                    :class="event.delta < 0 ? 'text-destructive' : 'text-green-600'"
                  >
                    {{ formatSignedBalance(event.delta) }}
                  </span>
                </div>
                <p v-if="event.detail" class="text-muted-foreground mt-0.5 text-xs">
                  {{ event.detail }}
                </p>
              </li>
            </ul>
          </div>
        </div>
        <p
          v-if="isMentor && teams.length === 0"
          class="text-muted-foreground mt-3 shrink-0 text-sm"
        >
          تیمی ثبت نشده است.
        </p>
        <p
          v-else-if="isMentor && listedTeams.length === 0"
          class="text-muted-foreground mt-3 shrink-0 text-sm"
        >
          تیمی پیدا نشد.
        </p>
      </template>
    </div>

    <footer v-if="me && !loading" class="border-t px-5 py-3">
      <Button class="w-full" variant="ghost" :disabled="submitting" @click="logout">
        خروج از حساب {{ me.username }}
      </Button>
    </footer>
  </aside>
</template>
