<script setup lang="ts">
/**
 * The composer: write, keep as a draft, send.
 *
 * Laid out like a mail client because that is the mental model the brief asked
 * for — three boxes down the side, one editor in the middle. Only the audience
 * picker is unusual, and only because "everyone" here means six different
 * things.
 *
 * Native `<select>`s: the shadcn-vue registry is unreachable from this machine
 * (see docs/house-view.md), and a hand-written copy of their Select gets the
 * Reka primitives wrong.
 */
import { Loader2Icon, PencilIcon, SendIcon, TrashIcon } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { useActing } from '@/composables/useActing'
import { formatRelativeTime } from '@/lib/format'
import { ApiError } from '@/lib/http'
import {
  useAudienceOptionsQuery,
  useCreateMessageMutation,
  useDeleteMessageMutation,
  useMessagesQuery,
  useSendMessageMutation,
  useUpdateMessageMutation,
} from '@/queries/notifications'
import type { Audience, Message, MessageDraft } from '@/types/api'

type Box = 'compose' | 'draft' | 'sent'

const { isAnnouncer } = useActing()
// Gate the queries on the right itself: /messages/audiences/ 403s otherwise,
// and a rejected request on mount reads as a broken page.
const enabled = () => isAnnouncer.value

const optionsQuery = useAudienceOptionsQuery(enabled)
const draftsQuery = useMessagesQuery('draft', enabled)
const sentQuery = useMessagesQuery('sent', enabled)

const createMutation = useCreateMessageMutation()
const updateMutation = useUpdateMessageMutation()
const deleteMutation = useDeleteMessageMutation()
const sendMutation = useSendMessageMutation()

const box = ref<Box>('compose')

// The message being edited, or null for a fresh one. Only drafts are editable,
// so this is always either null or a draft.
const editingId = ref<number | null>(null)
const audience = ref<Audience>('all')
const teamCode = ref<string>('')
const userId = ref<number | null>(null)
const title = ref('')
const body = ref('')

const choices = computed(() => optionsQuery.data.value?.choices ?? [])
const teams = computed(() => optionsQuery.data.value?.teams ?? [])
const users = computed(() => optionsQuery.data.value?.users ?? [])
const drafts = computed<Message[]>(() => draftsQuery.data.value ?? [])
const sent = computed<Message[]>(() => sentQuery.data.value ?? [])

const needsTeam = computed(() => audience.value === 'team')
const needsUser = computed(() => audience.value === 'user')

const busy = computed(
  () =>
    createMutation.isPending.value ||
    updateMutation.isPending.value ||
    sendMutation.isPending.value,
)

const canSubmit = computed(() => {
  if (!title.value.trim()) return false
  if (needsTeam.value && !teamCode.value) return false
  if (needsUser.value && userId.value == null) return false
  return !busy.value
})

// Switching away from a targeted audience must not leave a stale target behind:
// the server would reject it, and the picker would look like it still applies.
watch(audience, (value) => {
  if (value !== 'team') teamCode.value = ''
  if (value !== 'user') userId.value = null
})

function reset() {
  editingId.value = null
  audience.value = 'all'
  teamCode.value = ''
  userId.value = null
  title.value = ''
  body.value = ''
}

function payload(): MessageDraft {
  return {
    title: title.value.trim(),
    body: body.value,
    audience: audience.value,
    audience_team: needsTeam.value ? teamCode.value : null,
    audience_user: needsUser.value ? userId.value : null,
  }
}

function failed(error: unknown, fallback: string) {
  toast.error(error instanceof ApiError ? error.detail : fallback)
}

function edit(message: Message) {
  editingId.value = message.id
  audience.value = message.audience
  teamCode.value = message.audience_team ?? ''
  userId.value = message.audience_user
  title.value = message.title
  body.value = message.body
  box.value = 'compose'
}

async function saveDraft() {
  try {
    if (editingId.value != null) {
      await updateMutation.mutateAsync({ id: editingId.value, draft: payload() })
      toast.success('پیش‌نویس ذخیره شد')
    } else {
      const created = await createMutation.mutateAsync(payload())
      editingId.value = (created as Message).id
      toast.success('پیش‌نویس ساخته شد')
    }
  } catch (error) {
    failed(error, 'ذخیرهٔ پیش‌نویس ناموفق بود.')
  }
}

async function send() {
  try {
    // Save first, so what goes out is exactly what is on screen — an edited
    // draft sent without saving would deliver the version before the edit.
    let id = editingId.value
    if (id != null) {
      await updateMutation.mutateAsync({ id, draft: payload() })
    } else {
      const created = (await createMutation.mutateAsync(payload())) as Message
      id = created.id
    }
    const result = await sendMutation.mutateAsync(id)
    toast.success(`پیام برای ${result.delivered} نفر ارسال شد`)
    reset()
    box.value = 'sent'
  } catch (error) {
    failed(error, 'ارسال پیام ناموفق بود.')
  }
}

async function sendExisting(message: Message) {
  try {
    const result = await sendMutation.mutateAsync(message.id)
    toast.success(`پیام برای ${result.delivered} نفر ارسال شد`)
    if (editingId.value === message.id) reset()
  } catch (error) {
    failed(error, 'ارسال پیام ناموفق بود.')
  }
}

async function discard(message: Message) {
  try {
    await deleteMutation.mutateAsync(message.id)
    if (editingId.value === message.id) reset()
    toast.success('پیش‌نویس حذف شد')
  } catch (error) {
    failed(error, 'حذف پیش‌نویس ناموفق بود.')
  }
}
</script>

<template>
  <div class="messages" dir="rtl">
    <nav class="messages-tabs" aria-label="بخش‌های پیام">
      <button
        type="button"
        class="messages-tab"
        :class="{ 'is-active': box === 'compose' }"
        @click="box = 'compose'"
      >
        <PencilIcon class="size-3.5" />
        نوشتن
      </button>
      <button
        type="button"
        class="messages-tab"
        :class="{ 'is-active': box === 'draft' }"
        @click="box = 'draft'"
      >
        پیش‌نویس‌ها
        <span v-if="drafts.length" class="messages-tab-count">{{ drafts.length }}</span>
      </button>
      <button
        type="button"
        class="messages-tab"
        :class="{ 'is-active': box === 'sent' }"
        @click="box = 'sent'"
      >
        ارسال‌شده
      </button>
      <Button
        v-if="box === 'compose' && (editingId !== null || title)"
        variant="ghost"
        size="sm"
        class="ms-auto"
        @click="reset"
      >
        پیام تازه
      </Button>
    </nav>

    <!-- ---- compose ---- -->
    <form v-if="box === 'compose'" class="composer" @submit.prevent="send">
      <p v-if="editingId !== null" class="composer-editing">
        در حال ویرایش یک پیش‌نویس.
      </p>

      <div class="composer-row">
        <div class="composer-field">
          <Label for="msg-audience">گیرنده</Label>
          <select id="msg-audience" v-model="audience" class="composer-select">
            <option v-for="choice in choices" :key="choice.value" :value="choice.value">
              {{ choice.label }}
            </option>
          </select>
        </div>

        <div v-if="needsTeam" class="composer-field">
          <Label for="msg-team">تیم</Label>
          <select id="msg-team" v-model="teamCode" class="composer-select">
            <option value="" disabled>یک تیم را انتخاب کنید</option>
            <option v-for="team in teams" :key="team.code" :value="team.code">
              {{ team.name }}
            </option>
          </select>
        </div>

        <div v-if="needsUser" class="composer-field">
          <Label for="msg-user">شخص</Label>
          <select id="msg-user" v-model="userId" class="composer-select">
            <option :value="null" disabled>یک نفر را انتخاب کنید</option>
            <option v-for="user in users" :key="user.id" :value="user.id">
              {{ user.label }}
            </option>
          </select>
        </div>
      </div>

      <div class="composer-field">
        <Label for="msg-title">موضوع</Label>
        <Input id="msg-title" v-model="title" maxlength="120" placeholder="موضوع پیام" />
      </div>

      <div class="composer-field composer-body">
        <Label for="msg-body">متن</Label>
        <Textarea id="msg-body" v-model="body" rows="10" placeholder="متن پیام…" />
      </div>

      <footer class="composer-foot">
        <Button type="submit" :disabled="!canSubmit">
          <Loader2Icon v-if="busy" class="size-4 animate-spin" />
          <SendIcon v-else class="size-4" />
          ارسال
        </Button>
        <Button type="button" variant="outline" :disabled="!title.trim() || busy" @click="saveDraft">
          ذخیرهٔ پیش‌نویس
        </Button>
      </footer>
    </form>

    <!-- ---- drafts ---- -->
    <div v-else-if="box === 'draft'" class="messages-list">
      <template v-if="draftsQuery.isPending.value">
        <Skeleton v-for="n in 3" :key="n" class="h-20 w-full rounded-lg" />
      </template>
      <p v-else-if="drafts.length === 0" class="messages-empty">پیش‌نویسی ندارید.</p>
      <article v-for="message in drafts" v-else :key="message.id" class="message-row">
        <div class="message-row-text">
          <span class="message-row-meta">
            <span>{{ message.audience_label }}</span>
            <span>·</span>
            <span>{{ message.recipient_count }} گیرنده</span>
            <span class="message-row-time">{{ formatRelativeTime(message.updated_at) }}</span>
          </span>
          <span class="message-row-title">{{ message.title }}</span>
          <span class="message-row-excerpt">{{ message.excerpt || '—' }}</span>
        </div>
        <div class="message-row-actions">
          <Button variant="ghost" size="sm" @click="edit(message)">
            <PencilIcon class="size-3.5" />
            ویرایش
          </Button>
          <Button variant="outline" size="sm" @click="sendExisting(message)">
            <SendIcon class="size-3.5" />
            ارسال
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="حذف پیش‌نویس"
            @click="discard(message)"
          >
            <TrashIcon class="size-3.5" />
          </Button>
        </div>
      </article>
    </div>

    <!-- ---- sent ---- -->
    <div v-else class="messages-list">
      <template v-if="sentQuery.isPending.value">
        <Skeleton v-for="n in 3" :key="n" class="h-20 w-full rounded-lg" />
      </template>
      <p v-else-if="sent.length === 0" class="messages-empty">هنوز پیامی ارسال نشده است.</p>
      <article v-for="message in sent" v-else :key="message.id" class="message-row">
        <div class="message-row-text">
          <span class="message-row-meta">
            <span>{{ message.sender }}</span>
            <span>·</span>
            <span>{{ message.audience_label }}</span>
            <span class="message-row-time">{{ formatRelativeTime(message.sent_at) }}</span>
          </span>
          <span class="message-row-title">{{ message.title }}</span>
          <span class="message-row-excerpt">{{ message.excerpt || '—' }}</span>
        </div>
        <!-- The one number worth showing after the fact: did it land. -->
        <div class="message-row-stat" :title="'خوانده‌شده از کل گیرندگان'">
          <span class="message-row-stat-value">
            {{ message.read_count }}<span class="opacity-50">/{{ message.recipient_count }}</span>
          </span>
          <span class="message-row-stat-label">خوانده‌شده</span>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.messages {
  display: flex;
  block-size: 100%;
  min-block-size: 0;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
  overflow: hidden;
}

.messages-tabs {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  flex-shrink: 0;
  padding-block-end: 0.5rem;
  border-block-end: 1px solid var(--border);
}

.messages-tab {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.7rem;
  border-radius: 0.5rem;
  color: var(--muted-foreground);
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
}
.messages-tab:hover {
  background: var(--muted);
  color: var(--foreground);
}
.messages-tab.is-active {
  background: var(--primary);
  color: var(--primary-foreground);
}

.messages-tab-count {
  display: inline-grid;
  place-items: center;
  min-inline-size: 1.1rem;
  padding-inline: 0.25rem;
  border-radius: 9999px;
  background: color-mix(in oklab, currentColor 20%, transparent);
  font-size: 0.65rem;
}

/* ---- composer ---- */
.composer {
  display: flex;
  min-block-size: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 0.75rem;
  max-inline-size: 46rem;
}

.composer-editing {
  margin: 0;
  padding: 0.4rem 0.6rem;
  border: 1px dashed var(--border);
  border-radius: 0.5rem;
  color: var(--muted-foreground);
  font-size: 0.72rem;
}

.composer-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}
.composer-row .composer-field {
  min-inline-size: 12rem;
  flex: 1 1 12rem;
}

.composer-field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.composer-body {
  min-block-size: 0;
  flex: 1 1 auto;
}
.composer-body :deep(textarea) {
  block-size: 100%;
  min-block-size: 9rem;
  resize: none;
}

.composer-select {
  block-size: 2.25rem;
  inline-size: 100%;
  border: 1px solid var(--input);
  border-radius: 0.5rem;
  background: transparent;
  padding-inline: 0.6rem;
  color: var(--foreground);
  font-size: 0.85rem;
}

.composer-foot {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

/* ---- lists ---- */
.messages-list {
  display: flex;
  min-block-size: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 0.5rem;
  overflow-y: auto;
  max-inline-size: 60rem;
}

.messages-empty {
  margin: 3rem 0;
  color: var(--muted-foreground);
  font-size: 0.85rem;
  text-align: center;
}

.message-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.7rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  background: var(--card);
}

.message-row-text {
  display: flex;
  min-inline-size: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 0.12rem;
}

.message-row-meta {
  display: flex;
  align-items: baseline;
  gap: 0.35rem;
  color: var(--muted-foreground);
  font-size: 0.6875rem;
}
.message-row-time {
  margin-inline-start: auto;
}

.message-row-title {
  font-size: 0.85rem;
  font-weight: 700;
}

.message-row-excerpt {
  color: var(--muted-foreground);
  font-size: 0.72rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.message-row-actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex-shrink: 0;
}

.message-row-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  line-height: 1.2;
}
.message-row-stat-value {
  font-size: 0.9rem;
  font-weight: 700;
}
.message-row-stat-label {
  color: var(--muted-foreground);
  font-size: 0.625rem;
}

@media (max-width: 640px) {
  .message-row {
    align-items: flex-start;
    flex-direction: column;
  }
  .message-row-excerpt {
    white-space: normal;
  }
}
</style>
