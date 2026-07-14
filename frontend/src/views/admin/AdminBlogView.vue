<script setup>
import { onMounted, reactive, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import RichTextEditor from '../../components/admin/RichTextEditor.vue'

const { items: posts, loading, error, load } = useAdminList('/admin/blog/')
const busyId = ref(null)

const showModal = ref(false)
const saving = ref(false)
const formError = ref('')
const editingId = ref(null)
const imageFile = ref(null)
const imagePreviewUrl = ref(null)

const categoryOptions = [
  { value: 'travel_tips', label: 'Travel Tips' },
  { value: 'destination_guides', label: 'Destination Guides' },
  { value: 'fleet_spotlights', label: 'Fleet & Driver Spotlights' },
  { value: 'company_news', label: 'Company News' },
]

const form = reactive({
  title: '',
  category: 'travel_tips',
  excerpt: '',
  body: '',
  is_published: false,
})

function resetForm() {
  editingId.value = null
  Object.assign(form, { title: '', category: 'travel_tips', excerpt: '', body: '', is_published: false })
  imageFile.value = null
  imagePreviewUrl.value = null
  formError.value = ''
}

function openAddModal() {
  resetForm()
  showModal.value = true
}

function openEditModal(post) {
  editingId.value = post.id
  Object.assign(form, {
    title: post.title, category: post.category, excerpt: post.excerpt, body: post.body, is_published: post.is_published,
  })
  imageFile.value = null
  imagePreviewUrl.value = post.cover_image || null
  formError.value = ''
  showModal.value = true
}

function onImageSelected(event) {
  const file = event.target.files[0]
  imageFile.value = file || null
  imagePreviewUrl.value = file ? URL.createObjectURL(file) : imagePreviewUrl.value
}

function buildPayload() {
  const payload = new FormData()
  payload.append('title', form.title)
  payload.append('category', form.category)
  payload.append('excerpt', form.excerpt)
  payload.append('body', form.body)
  payload.append('is_published', form.is_published)
  if (imageFile.value) payload.append('cover_image', imageFile.value)
  return payload
}

async function savePost() {
  formError.value = ''
  if (!form.title.trim() || !form.excerpt.trim() || !form.body.trim()) {
    formError.value = 'Title, excerpt, and body are all required.'
    return
  }
  saving.value = true
  try {
    const payload = buildPayload()
    if (editingId.value) {
      const { data } = await apiClient.patch(`/admin/blog/${editingId.value}/`, payload)
      const idx = posts.value.findIndex((p) => p.id === editingId.value)
      if (idx !== -1) posts.value[idx] = data
    } else {
      const { data } = await apiClient.post('/admin/blog/', payload)
      posts.value.unshift(data)
    }
    showModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    formError.value = typeof detail === 'object'
      ? Object.values(detail).flat().join(' ')
      : 'Could not save this post. Please try again.'
  } finally {
    saving.value = false
  }
}

async function togglePublished(post) {
  busyId.value = post.id
  try {
    const { data } = await apiClient.patch(`/admin/blog/${post.id}/`, { is_published: !post.is_published })
    Object.assign(post, data)
  } catch {
    error.value = 'Could not update this post.'
  } finally {
    busyId.value = null
  }
}

async function deletePost(post) {
  if (!confirm(`Delete "${post.title}"? This cannot be undone.`)) return
  busyId.value = post.id
  try {
    await apiClient.delete(`/admin/blog/${post.id}/`)
    posts.value = posts.value.filter((p) => p.id !== post.id)
  } catch {
    error.value = 'Could not delete this post.'
  } finally {
    busyId.value = null
  }
}

onMounted(() => {
  load()
})
</script>

<template>
  <div>
    <div class="flex items-center justify-between">
      <div>
        <h1 class="font-[Georgia] text-2xl font-bold text-white">Blog</h1>
        <p class="mt-1 text-sm text-slate-400">
          Marketing & SEO content - travel tips, destination guides, fleet and driver spotlights.
        </p>
      </div>
      <button
        class="flex items-center gap-2 rounded-lg bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400"
        @click="openAddModal"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        New Post
      </button>
    </div>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <div v-else class="mt-6 space-y-3">
      <div
        v-for="post in posts"
        :key="post.id"
        class="flex items-start gap-4 rounded-xl border border-navy-800 bg-navy-900 p-4"
      >
        <div class="h-16 w-24 shrink-0 overflow-hidden rounded-lg border border-navy-700 bg-navy-800">
          <img v-if="post.cover_image" :src="post.cover_image" :alt="post.title" class="h-full w-full object-cover" />
          <div v-else class="flex h-full items-center justify-center text-xs text-slate-600">No cover</div>
        </div>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <p class="truncate font-semibold text-white">{{ post.title }}</p>
            <span
              class="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
              :class="post.is_published ? 'bg-green-500/10 text-green-400' : 'bg-navy-800 text-slate-500'"
            >
              {{ post.is_published ? 'Published' : 'Draft' }}
            </span>
            <span class="shrink-0 rounded-full bg-navy-800 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              {{ post.category_display }}
            </span>
          </div>
          <p class="mt-1 line-clamp-2 text-sm text-slate-400">{{ post.excerpt }}</p>
          <p class="mt-2 text-xs text-slate-500">
            {{ post.created_by_name || 'Unknown' }} &middot;
            {{ post.published_at ? `Published ${new Date(post.published_at).toLocaleDateString()}` : 'Not yet published' }}
          </p>
        </div>
        <div class="flex shrink-0 flex-col items-end gap-2">
          <div class="flex gap-2">
            <a
              :href="`/blog/${post.slug}`" target="_blank" rel="noopener"
              class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400"
            >
              Preview
            </a>
            <button
              :disabled="busyId === post.id"
              class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
              @click="openEditModal(post)"
            >
              Edit
            </button>
            <button
              :disabled="busyId === post.id"
              class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
              @click="togglePublished(post)"
            >
              {{ post.is_published ? 'Unpublish' : 'Publish' }}
            </button>
            <button
              :disabled="busyId === post.id"
              class="rounded-md border border-red-400 px-2 py-1 text-xs font-semibold text-red-400 hover:bg-red-400 hover:text-navy-950 disabled:opacity-50"
              @click="deletePost(post)"
            >
              Delete
            </button>
          </div>
        </div>
      </div>
      <p v-if="!posts.length" class="p-6 text-center text-slate-400">No posts yet.</p>
    </div>

    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showModal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showModal = false"
        >
          <div class="w-full max-w-2xl rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-white">
                {{ editingId ? 'Edit Post' : 'New Post' }}
              </h2>
              <button class="text-slate-400 transition-colors hover:text-white" @click="showModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ formError }}</p>

            <form class="space-y-4" @submit.prevent="savePost">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Title *</label>
                <input
                  v-model="form.title" type="text" placeholder="e.g. A Weekend Guide to Kisumu" required
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Category</label>
                <select v-model="form.category"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none">
                  <option v-for="opt in categoryOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Excerpt *</label>
                <textarea
                  v-model="form.excerpt" rows="2" maxlength="300" required
                  placeholder="Shown on the blog list page and used as the SEO description."
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                ></textarea>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Cover Image</label>
                <div class="flex items-center gap-3">
                  <div class="h-16 w-24 shrink-0 overflow-hidden rounded-lg border border-navy-700 bg-navy-800">
                    <img v-if="imagePreviewUrl" :src="imagePreviewUrl" alt="Preview" class="h-full w-full object-cover" />
                    <div v-else class="flex h-full items-center justify-center text-xs text-slate-500">No cover</div>
                  </div>
                  <input type="file" accept="image/*"
                    class="w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950"
                    @change="onImageSelected"
                  />
                </div>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Body *</label>
                <RichTextEditor v-model="form.body" />
              </div>
              <label class="flex items-center gap-2 text-sm text-slate-300">
                <input v-model="form.is_published" type="checkbox" class="rounded border-navy-700 bg-navy-800 text-gold-500 focus:ring-gold-500" />
                Published (visible on the public blog)
              </label>

              <div class="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  class="rounded-lg border border-navy-700 px-4 py-2 text-sm font-medium text-slate-300 hover:text-white"
                  @click="showModal = false"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  :disabled="saving"
                  class="rounded-lg bg-gold-500 px-5 py-2 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400 disabled:opacity-50"
                >
                  {{ saving ? 'Saving…' : (editingId ? 'Save Changes' : 'Create Post') }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
