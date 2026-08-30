<script setup>
import { CheckIcon, SearchIcon } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '../composables/useActing.js'

const { me, teams, actingTeam, loading, error, submitting, bootstrap, login, actAs, logout } =
  useActing()

const username = ref('')
const password = ref('')
const query = ref('')

onMounted(bootstrap)

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

const filteredTeams = computed(() => {
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

function isNoneSelected() {
  return !actingTeam.value
}
</script>

<template>
  <aside class="flex h-full w-80 shrink-0 flex-col overflow-hidden border-e bg-card">
    <header class="border-b px-5 py-4">
      <h1 class="text-lg font-bold">تیم‌ها</h1>
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
        یک تیم را انتخاب کنید
      </p>
      <p v-else class="text-muted-foreground mt-1 text-sm">
        برای دیدن تیم‌ها وارد شوید
      </p>
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

      <template v-else>
        <div class="relative mb-3 shrink-0">
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
        <ul class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
          <li>
            <Button
              class="h-auto w-full items-start justify-between py-3 whitespace-normal"
              :variant="isNoneSelected() ? 'default' : 'outline'"
              @click="actAs(null)"
            >
              <span class="flex min-w-0 flex-col items-start gap-0.5 text-start">
                <span class="font-semibold">بدون تیم</span>
                <span class="text-xs opacity-80">هیچ تیمی انتخاب نشده</span>
              </span>
              <Badge v-if="isNoneSelected()" variant="secondary" class="gap-1">
                <CheckIcon class="size-3" />
                انتخاب‌شده
              </Badge>
            </Button>
          </li>
          <li v-for="team in filteredTeams" :key="team.code">
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
        <p
          v-if="teams.length === 0"
          class="text-muted-foreground mt-3 shrink-0 text-sm"
        >
          تیمی ثبت نشده است.
        </p>
        <p
          v-else-if="filteredTeams.length === 0"
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
