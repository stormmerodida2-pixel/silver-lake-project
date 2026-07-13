<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Link from '@tiptap/extension-link'

import apiClient from '../../api/client'

const props = defineProps({ modelValue: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue'])

const editor = useEditor({
  content: props.modelValue,
  extensions: [StarterKit, Image, Link.configure({ openOnClick: false })],
  editorProps: {
    attributes: { class: 'prose prose-invert max-w-none p-4 text-sm focus:outline-none min-h-[240px]' },
  },
  onUpdate: ({ editor: instance }) => emit('update:modelValue', instance.getHTML()),
})

// Keep in sync if the parent resets modelValue (e.g. opening the edit modal for a different
// post) without fighting the user's own typing mid-edit.
watch(() => props.modelValue, (value) => {
  if (editor.value && value !== editor.value.getHTML()) {
    editor.value.commands.setContent(value || '', false)
  }
})

onBeforeUnmount(() => {
  editor.value?.destroy()
})

const uploading = ref(false)
async function insertImage(event) {
  const file = event.target.files[0]
  if (!file) return
  uploading.value = true
  try {
    const payload = new FormData()
    payload.append('image', file)
    const { data } = await apiClient.post('/admin/blog/upload-image/', payload)
    editor.value.chain().focus().setImage({ src: data.image }).run()
  } finally {
    uploading.value = false
    event.target.value = ''
  }
}

function setLink() {
  const previousUrl = editor.value.getAttributes('link').href
  const url = window.prompt('Link URL', previousUrl || 'https://')
  if (url === null) return
  if (url === '') {
    editor.value.chain().focus().unsetLink().run()
    return
  }
  editor.value.chain().focus().setLink({ href: url }).run()
}
</script>

<template>
  <div class="overflow-hidden rounded-lg border border-navy-700 bg-navy-800">
    <div v-if="editor" class="flex flex-wrap gap-1 border-b border-navy-700 bg-navy-900 p-2">
      <button
        type="button" title="Bold"
        class="rounded px-2 py-1 text-xs font-semibold"
        :class="editor.isActive('bold') ? 'bg-gold-500 text-navy-950' : 'text-slate-300 hover:bg-navy-800'"
        @mousedown.prevent @click="editor.chain().focus().toggleBold().run()"
      >B</button>
      <button
        type="button" title="Italic"
        class="rounded px-2 py-1 text-xs italic"
        :class="editor.isActive('italic') ? 'bg-gold-500 text-navy-950' : 'text-slate-300 hover:bg-navy-800'"
        @mousedown.prevent @click="editor.chain().focus().toggleItalic().run()"
      >I</button>
      <button
        type="button" title="Heading 2"
        class="rounded px-2 py-1 text-xs font-semibold"
        :class="editor.isActive('heading', { level: 2 }) ? 'bg-gold-500 text-navy-950' : 'text-slate-300 hover:bg-navy-800'"
        @mousedown.prevent @click="editor.chain().focus().toggleHeading({ level: 2 }).run()"
      >H2</button>
      <button
        type="button" title="Heading 3"
        class="rounded px-2 py-1 text-xs font-semibold"
        :class="editor.isActive('heading', { level: 3 }) ? 'bg-gold-500 text-navy-950' : 'text-slate-300 hover:bg-navy-800'"
        @mousedown.prevent @click="editor.chain().focus().toggleHeading({ level: 3 }).run()"
      >H3</button>
      <button
        type="button" title="Bullet list"
        class="rounded px-2 py-1 text-xs"
        :class="editor.isActive('bulletList') ? 'bg-gold-500 text-navy-950' : 'text-slate-300 hover:bg-navy-800'"
        @mousedown.prevent @click="editor.chain().focus().toggleBulletList().run()"
      >• List</button>
      <button
        type="button" title="Numbered list"
        class="rounded px-2 py-1 text-xs"
        :class="editor.isActive('orderedList') ? 'bg-gold-500 text-navy-950' : 'text-slate-300 hover:bg-navy-800'"
        @mousedown.prevent @click="editor.chain().focus().toggleOrderedList().run()"
      >1. List</button>
      <button
        type="button" title="Quote"
        class="rounded px-2 py-1 text-xs"
        :class="editor.isActive('blockquote') ? 'bg-gold-500 text-navy-950' : 'text-slate-300 hover:bg-navy-800'"
        @mousedown.prevent @click="editor.chain().focus().toggleBlockquote().run()"
      >Quote</button>
      <button
        type="button" title="Link"
        class="rounded px-2 py-1 text-xs text-slate-300 hover:bg-navy-800"
        :class="{ 'bg-gold-500 text-navy-950': editor.isActive('link') }"
        @mousedown.prevent @click="setLink"
      >Link</button>
      <label
        class="cursor-pointer rounded px-2 py-1 text-xs text-slate-300 hover:bg-navy-800"
        :class="{ 'pointer-events-none opacity-50': uploading }"
      >
        {{ uploading ? 'Uploading…' : 'Image' }}
        <input type="file" accept="image/*" class="hidden" @change="insertImage" />
      </label>
      <button
        type="button" title="Undo"
        class="rounded px-2 py-1 text-xs text-slate-300 hover:bg-navy-800"
        @mousedown.prevent @click="editor.chain().focus().undo().run()"
      >Undo</button>
      <button
        type="button" title="Redo"
        class="rounded px-2 py-1 text-xs text-slate-300 hover:bg-navy-800"
        @mousedown.prevent @click="editor.chain().focus().redo().run()"
      >Redo</button>
    </div>
    <EditorContent :editor="editor" class="bg-navy-800" />
  </div>
</template>
