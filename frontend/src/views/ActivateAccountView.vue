<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const route = useRoute()
const auth = useAuthStore()

const status = ref('activating') // activating -> success -> error
const message = ref('')

onMounted(async () => {
  try {
    const data = await auth.activateAccount(route.params.uid, route.params.token)
    message.value = data.detail
    status.value = 'success'
  } catch (err) {
    message.value = err.response?.data?.detail || 'This activation link is invalid or has expired.'
    status.value = 'error'
  }
})
</script>

<template>
  <div class="bg-white">
    <div class="mx-auto max-w-md px-4 py-16 text-center sm:px-6">
      <div class="rounded-xl border border-slate-200 bg-slate-50 p-6">
        <h1 class="font-[Georgia] text-2xl font-bold text-navy-900">
          {{ status === 'activating' ? 'Activating your account...' : status === 'success' ? 'You\'re all set!' : 'Activation failed' }}
        </h1>
        <p class="mt-3 text-sm" :class="status === 'error' ? 'text-red-600' : 'text-slate-600'">{{ message }}</p>
        <RouterLink
          v-if="status !== 'activating'"
          to="/login"
          class="mt-6 inline-block rounded-md bg-gold-500 px-4 py-2 font-semibold text-navy-950 transition hover:bg-gold-400"
        >
          Go to Log In
        </RouterLink>
      </div>
    </div>
  </div>
</template>
