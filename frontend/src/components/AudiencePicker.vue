<script setup lang="ts">
/**
 * Who gets the message.
 *
 * Three additive selections, unioned by the server: whole categories by name,
 * plus any teams picked out, plus any people picked out. That is what lets
 * "these four teams and every mentor" be one message.
 *
 * Checkboxes rather than a multi-select `<select>`: a native multi-select needs
 * ctrl-click to add a second item, which is a discoverability trap, and it
 * cannot show a search box. The lists are short enough to scroll — 48 teams at
 * most — and the filter handles the rest.
 */
import { CheckIcon, SearchIcon, UsersIcon, XIcon } from '@lucide/vue'
import { computed, ref } from 'vue'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { AudienceChoice, AudienceScope, AudienceUser } from '@/types/api'

const props = defineProps<{
  choices: AudienceChoice[]
  teams: { code: string; name: string }[]
  users: AudienceUser[]
  scopes: AudienceScope[]
  selectedTeams: string[]
  selectedUsers: number[]
  reach?: number | null
  reachLabel?: string
  reachLoading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:scopes', value: AudienceScope[]): void
  (e: 'update:selectedTeams', value: string[]): void
  (e: 'update:selectedUsers', value: number[]): void
}>()

const teamQuery = ref('')
const userQuery = ref('')

/** "همه" makes every other choice moot, so it collapses the rest of the form. */
const isEveryone = computed(() => props.scopes.includes('all'))

const teamMatches = computed(() => {
  const needle = teamQuery.value.trim().toLowerCase()
  if (!needle) return props.teams
  return props.teams.filter(
    (team) =>
      team.name.toLowerCase().includes(needle) || team.code.toLowerCase().includes(needle),
  )
})

const userMatches = computed(() => {
  const needle = userQuery.value.trim().toLowerCase()
  if (!needle) return props.users
  return props.users.filter((user) => user.label.toLowerCase().includes(needle))
})

function toggleScope(scope: AudienceScope) {
  // Picking "همه" clears everything else; picking anything else clears "همه".
  if (scope === 'all') {
    emit('update:scopes', isEveryone.value ? [] : ['all'])
    return
  }
  const next = new Set(props.scopes.filter((item) => item !== 'all'))
  if (next.has(scope)) next.delete(scope)
  else next.add(scope)
  emit('update:scopes', [...next])
}

/**
 * Bound with `v-model` on the array rather than `:checked` + `@change`.
 *
 * With the manual pair, a checkbox the browser has ticked stays ticked if the
 * prop it is bound to never *changed* value between renders — Vue patches only
 * on a diff, so the input keeps the state the browser gave it and quietly
 * disagrees with the source of truth. `v-model` owns both sides and cannot
 * drift.
 */
const teamModel = computed({
  get: () => props.selectedTeams,
  set: (value: string[]) => emit('update:selectedTeams', value),
})

const userModel = computed({
  get: () => props.selectedUsers,
  set: (value: number[]) => emit('update:selectedUsers', value),
})

function allShownTeams() {
  emit('update:selectedTeams', [
    ...new Set([...props.selectedTeams, ...teamMatches.value.map((team) => team.code)]),
  ])
}

function clearTeams() {
  emit('update:selectedTeams', [])
}

function clearUsers() {
  emit('update:selectedUsers', [])
}

function clearAll() {
  emit('update:scopes', [])
  clearTeams()
  clearUsers()
}

const hasSelection = computed(
  () => props.scopes.length > 0 || props.selectedTeams.length > 0 || props.selectedUsers.length > 0,
)
</script>

<template>
  <section class="picker" aria-label="گیرندگان">
    <header class="picker-head">
      <Label class="picker-legend">گیرندگان</Label>
      <span v-if="hasSelection" class="picker-reach">
        <UsersIcon class="size-3.5" aria-hidden="true" />
        <template v-if="props.reachLoading">در حال محاسبه…</template>
        <template v-else-if="props.reach != null">
          {{ props.reachLabel }} — {{ props.reach }} نفر
        </template>
      </span>
      <button v-if="hasSelection" type="button" class="picker-clear" @click="clearAll">
        پاک کردن
      </button>
    </header>

    <!-- Categories -->
    <div class="picker-chips">
      <button
        v-for="choice in props.choices"
        :key="choice.value"
        type="button"
        class="chip"
        :class="{ 'is-on': props.scopes.includes(choice.value) }"
        :aria-pressed="props.scopes.includes(choice.value)"
        @click="toggleScope(choice.value)"
      >
        <CheckIcon v-if="props.scopes.includes(choice.value)" class="size-3" />
        {{ choice.label }}
      </button>
    </div>

    <p v-if="isEveryone" class="picker-note">
      «همه» همهٔ حساب‌ها را در بر می‌گیرد؛ انتخاب‌های دیگر لازم نیست.
    </p>

    <div v-else class="picker-lists">
      <!-- Teams -->
      <div class="picker-column">
        <div class="picker-column-head">
          <Label for="pick-team-search" class="picker-column-title">
            تیم‌ها
            <span v-if="props.selectedTeams.length" class="picker-badge">
              {{ props.selectedTeams.length }}
            </span>
          </Label>
          <div class="picker-column-actions">
            <button type="button" @click="allShownTeams">انتخاب همه</button>
            <button v-if="props.selectedTeams.length" type="button" @click="clearTeams">
              هیچ‌کدام
            </button>
          </div>
        </div>

        <div class="picker-search">
          <SearchIcon class="picker-search-icon" aria-hidden="true" />
          <Input
            id="pick-team-search"
            v-model="teamQuery"
            type="search"
            class="picker-search-input"
            placeholder="جستجوی تیم"
          />
          <button
            v-if="teamQuery"
            type="button"
            class="picker-search-clear"
            aria-label="پاک کردن جستجو"
            @click="teamQuery = ''"
          >
            <XIcon class="size-3" />
          </button>
        </div>

        <ul class="picker-options">
          <li v-for="team in teamMatches" :key="team.code">
            <label class="option">
              <input v-model="teamModel" type="checkbox" :value="team.code" />
              <span class="option-name">{{ team.name }}</span>
              <span class="option-hint">{{ team.code }}</span>
            </label>
          </li>
          <li v-if="teamMatches.length === 0" class="picker-none">تیمی پیدا نشد.</li>
        </ul>
      </div>

      <!-- People -->
      <div class="picker-column">
        <div class="picker-column-head">
          <Label for="pick-user-search" class="picker-column-title">
            افراد
            <span v-if="props.selectedUsers.length" class="picker-badge">
              {{ props.selectedUsers.length }}
            </span>
          </Label>
          <div class="picker-column-actions">
            <button v-if="props.selectedUsers.length" type="button" @click="clearUsers">
              هیچ‌کدام
            </button>
          </div>
        </div>

        <div class="picker-search">
          <SearchIcon class="picker-search-icon" aria-hidden="true" />
          <Input
            id="pick-user-search"
            v-model="userQuery"
            type="search"
            class="picker-search-input"
            placeholder="جستجوی نام کاربری"
          />
          <button
            v-if="userQuery"
            type="button"
            class="picker-search-clear"
            aria-label="پاک کردن جستجو"
            @click="userQuery = ''"
          >
            <XIcon class="size-3" />
          </button>
        </div>

        <ul class="picker-options">
          <li v-for="user in userMatches" :key="user.id">
            <label class="option">
              <input v-model="userModel" type="checkbox" :value="user.id" />
              <span class="option-name">{{ user.label }}</span>
              <span v-if="user.team_code" class="option-hint">{{ user.team_code }}</span>
            </label>
          </li>
          <li v-if="userMatches.length === 0" class="picker-none">کسی پیدا نشد.</li>
        </ul>
      </div>
    </div>
  </section>
</template>

<style scoped>
.picker {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.7rem 0.8rem;
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  background: color-mix(in oklab, var(--muted) 32%, transparent);
}

.picker-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.picker-legend {
  font-weight: 700;
}
.picker-reach {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin-inline-start: auto;
  color: var(--muted-foreground);
  font-size: 0.72rem;
}
.picker-clear {
  color: var(--muted-foreground);
  font-size: 0.72rem;
  text-decoration: underline;
  cursor: pointer;
}
.picker-clear:hover {
  color: var(--foreground);
}

.picker-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.28rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 9999px;
  background: var(--background);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
}
.chip:hover {
  border-color: var(--ring);
}
.chip.is-on {
  border-color: transparent;
  background: var(--primary);
  color: var(--primary-foreground);
}

.picker-note {
  margin: 0;
  color: var(--muted-foreground);
  font-size: 0.72rem;
}

.picker-lists {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.6rem;
}
@media (max-width: 720px) {
  .picker-lists {
    grid-template-columns: 1fr;
  }
}

.picker-column {
  display: flex;
  min-inline-size: 0;
  flex-direction: column;
  gap: 0.35rem;
}
.picker-column-head {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.picker-column-title {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.75rem;
  font-weight: 700;
}
.picker-badge {
  display: inline-grid;
  place-items: center;
  min-inline-size: 1.05rem;
  padding-inline: 0.25rem;
  border-radius: 9999px;
  background: var(--primary);
  color: var(--primary-foreground);
  font-size: 0.625rem;
}
.picker-column-actions {
  display: flex;
  gap: 0.4rem;
  margin-inline-start: auto;
}
.picker-column-actions button {
  color: var(--muted-foreground);
  font-size: 0.68rem;
  text-decoration: underline;
  cursor: pointer;
}
.picker-column-actions button:hover {
  color: var(--foreground);
}

.picker-search {
  position: relative;
  display: flex;
  align-items: center;
}
.picker-search-icon {
  position: absolute;
  inset-inline-start: 0.5rem;
  inline-size: 0.85rem;
  block-size: 0.85rem;
  color: var(--muted-foreground);
  pointer-events: none;
}
.picker-search-input {
  block-size: 2rem;
  padding-inline-start: 1.75rem;
  font-size: 0.78rem;
}
.picker-search-clear {
  position: absolute;
  inset-inline-end: 0.45rem;
  display: grid;
  place-items: center;
  color: var(--muted-foreground);
  cursor: pointer;
}

.picker-options {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0.25rem;
  list-style: none;
  max-block-size: 11rem;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 0.45rem;
  background: var(--background);
}

.option {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.25rem 0.35rem;
  border-radius: 0.35rem;
  font-size: 0.78rem;
  cursor: pointer;
}
.option:hover {
  background: var(--muted);
}
.option input {
  flex-shrink: 0;
  accent-color: var(--primary);
}
.option-name {
  min-inline-size: 0;
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.option-hint {
  flex-shrink: 0;
  color: var(--muted-foreground);
  font-size: 0.68rem;
}

.picker-none {
  padding: 0.6rem;
  color: var(--muted-foreground);
  font-size: 0.72rem;
  text-align: center;
}
</style>
