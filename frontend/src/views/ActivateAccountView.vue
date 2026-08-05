<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import SilverLakeLogo from '../components/SilverLakeLogo.vue'
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
  <div class="bg-page">
    <div class="mx-auto max-w-md px-4 py-16 text-center sm:px-6">
      <RouterLink to="/" class="flex items-center justify-center gap-2">
        <SilverLakeLogo :size="48" />
        <span class="flex flex-col items-start leading-none">
          <span class="font-[Georgia] text-xl font-bold uppercase tracking-wide text-foreground">SilverLake</span>
          <span
            class="mt-1 border-b-2 border-accent-border-strong pb-0.5 text-[11px] font-bold uppercase tracking-[0.2em] text-foreground-muted"
          >
            Car Rentals
          </span>
        </span>
      </RouterLink>
      <div class="mt-4 rounded-xl border border-border-subtle bg-surface p-6">
        <h1 class="font-[Georgia] text-2xl font-bold text-foreground">
          {{
            status === 'activating'
              ? 'Activating your account...'
              : status === 'success'
                ? "You're all set!"
                : 'Activation failed'
          }}
        </h1>
        <p class="mt-3 text-sm" :class="status === 'error' ? 'text-danger' : 'text-foreground-muted'">{{ message }}</p>
        <RouterLink
          v-if="status !== 'activating'"
          to="/login"
          class="mt-6 inline-block rounded-md bg-accent-bg px-4 py-2 font-semibold text-on-accent transition hover:bg-accent-bg-hover"
        >
          Go to Log In
        </RouterLink>
      </div>
    </div>
  </div>
</template>
