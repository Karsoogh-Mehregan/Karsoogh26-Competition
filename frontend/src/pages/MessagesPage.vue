<script setup lang="ts">
/**
 * The composer: write, keep as a draft, send.
 *
 * Laid out like a mail client because that is the mental model the brief asked
 * for — three boxes across the top, one editor beneath. The audience is the
 * only unusual part and it lives in `AudiencePicker`, because "who gets this"
 * is a set of three overlapping selections rather than one dropdown.
 */
import { Loader2Icon, PencilIcon, SendIcon, TrashIcon } from '@lucide/vue'
import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'

import AudiencePicker from '@/components/AudiencePicker.vue'
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
  useAudiencePreviewQuery,
  useCreateMessageMutation,
  useDeleteMessageMutation,
  useMessagesQuery,
  useSendMessageMutation,
  useUpdateMessageMutation,
} from '@/queries/notifications'
import type { AudienceScope, Message, MessageDraft } from '@/types/api'

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
const scopes = ref<AudienceScope[]>([])
const pickedTeams = ref<string[]>([])
const pickedUsers = ref<number[]>([])
const title = ref('')
const body = ref('')

const choices = computed(() => optionsQuery.data.value?.choices ?? [])
const teams = computed(() => optionsQuery.data.value?.teams ?? [])
const users = computed(() => optionsQuery.data.value?.users ?? [])
const drafts = computed<Message[]>(() => draftsQuery.data.value ?? [])
const sent = computed<Message[]>(() => sentQuery.data.value ?? [])

const selection = () => ({
  scopes: scopes.value,
  teams: pickedTeams.value,
  users: pickedUsers.value,
})

const hasAudience = computed(
  () => scopes.value.length > 0 || pickedTeams.value.length > 0 || pickedUsers.value.length > 0,
)

// Live reach, so an announcer sees "4 teams — 4 people" before committing.
const previewQuery = useAudiencePreviewQuery(selection, () => hasAudience.value)

const busy = computed(
  () =>
    createMutation.isPending.value ||
    updateMutation.isPending.value ||
    sendMutation.isPending.value,
)

// Sending needs a subject and somebody to send it to; a draft needs neither.
const canSubmit = computed(() => !!title.value.trim() && hasAudience.value && !busy.value)

function reset() {
  editingId.value = null
  scopes.value = []
  pickedTeams.value = []
  pickedUsers.value = []
  title.value = ''
  body.value = ''
}

function payload(): MessageDraft {
  return {
    title: title.value.trim(),
    body: body.value,
    scopes: scopes.value,
    teams: pickedTeams.value,
    users: pickedUsers.value,
  }
}

function failed(error: unknown, fallback: string) {
  toast.error(error instanceof ApiError ? error.detail : fallback)
}

function edit(message: Message) {
  editingId.value = message.id
  scopes.value = [...message.scopes]
  pickedTeams.value = [...message.teams]
  pickedUsers.value = [...message.users]
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

      <AudiencePicker
        :choices="choices"
        :teams="teams"
        :users="users"
        :scopes="scopes"
        :selected-teams="pickedTeams"
        :selected-users="pickedUsers"
        :reach="previewQuery.data.value?.count ?? null"
        :reach-label="previewQuery.data.value?.label ?? ''"
        :reach-loading="previewQuery.isFetching.value"
        @update:scopes="scopes = $event"
        @update:selected-teams="pickedTeams = $event"
        @update:selected-users="pickedUsers = $event"
      />

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
