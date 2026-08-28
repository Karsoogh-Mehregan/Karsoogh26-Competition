<script setup>
import { CheckIcon } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '../composables/useActing.js'

const { me, teams, loading, error, selecting, submitting, bootstrap, login, actAs, logout } =
  useActing()

const username = ref('')
const password = ref('')

onMounted(bootstrap)

async function onLogin() {
  await login(username.value, password.value)
}

function isSelected(team) {
  return me.value?.acting_team?.code === team.code
}
</script>

<template>
  <aside class="flex h-full w-80 shrink-0 flex-col overflow-hidden border-e bg-card">
    <header class="border-b px-5 py-4">
      <h1 class="text-lg font-bold">تیم‌ها</h1>
      <p v-if="me?.acting_team" class="text-muted-foreground mt-1 text-sm">
        در حال بازی به‌عنوان
        <span class="text-foreground font-semibold">{{ me.acting_team.name }}</span>
      </p>
      <p v-else-if="me" class="text-muted-foreground mt-1 text-sm">
        یک تیم را انتخاب کنید
      </p>
      <p v-else class="text-muted-foreground mt-1 text-sm">
        برای دیدن تیم‌ها وارد شوید
      </p>
    </header>

    <div class="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-4">
      <p v-if="error" class="text-destructive mb-3 text-sm">{{ error }}</p>

      <div v-if="loading" class="flex flex-col gap-2">
        <Skeleton class="h-12 w-full" />
        <Skeleton class="h-12 w-full" />
        <Skeleton class="h-12 w-full" />
      </div>

      <form v-else-if="!me" class="flex flex-col gap-3" @submit.prevent="onLogin">
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
        <p v-if="teams.length === 0" class="text-muted-foreground text-sm">
          تیمی ثبت نشده است.
        </p>
        <ul v-else class="flex flex-col gap-2">
          <li v-for="team in teams" :key="team.code">
            <Button
              class="h-auto w-full items-start justify-between py-3 whitespace-normal"
              :variant="isSelected(team) ? 'default' : 'outline'"
              :disabled="selecting === team.code"
              @click="actAs(team)"
            >
              <span class="flex min-w-0 flex-col items-start gap-0.5 text-start">
                <span class="font-semibold">{{ team.name }}</span>
                <span class="text-xs opacity-80">{{ team.code }}</span>
              </span>
              <Badge v-if="isSelected(team)" variant="secondary" class="gap-1">
                <CheckIcon class="size-3" />
                انتخاب‌شده
              </Badge>
            </Button>
          </li>
        </ul>
      </template>
    </div>

    <footer v-if="me && !loading" class="border-t px-5 py-3">
      <Button class="w-full" variant="ghost" :disabled="submitting" @click="logout">
        خروج از حساب {{ me.username }}
      </Button>
    </footer>
  </aside>
</template>
